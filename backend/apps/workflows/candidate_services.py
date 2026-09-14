"""Candidate extraction, review state, and lineage services."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import WorkflowNode, WorkflowNodeRun, WorkflowResultCandidate
from .services import create_node_run_event


IMAGE_NODE_TYPES = {'image', 'image_generation', 'image_edit', 'multi_grid_image'}
VIDEO_NODE_TYPES = {'video', 'video_generation'}
IMAGE_TRACE_KEYS = {
    'image', 'images', 'image_url', 'image_urls', 'imageuri', 'imageuris',
    'source_image', 'source_images', 'source_image_url', 'reference_image',
    'reference_images', 'first_frame', 'last_frame', 'start_frame', 'end_frame',
}


def _artifact_from_item(item: Any, media_type: str) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ''
    keys = ('video_url', 'url') if media_type == 'video' else ('image_url', 'url')
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    if media_type == 'image' and item.get('b64_json'):
        return f"data:image/png;base64,{item['b64_json']}"
    return ''


def _media_type(node_type: str, normalized_output: Dict[str, Any]) -> str:
    if node_type in IMAGE_NODE_TYPES or normalized_output.get('image_url') or normalized_output.get('imageUrl'):
        return 'image'
    if node_type in VIDEO_NODE_TYPES or normalized_output.get('video_url') or normalized_output.get('videoUrl'):
        return 'video'
    if any(normalized_output.get(key) for key in ('text', 'rewritten_text', 'raw_text')):
        return 'text'
    return 'json'


def _candidate_items(node_run: WorkflowNodeRun) -> List[Tuple[str, Dict[str, Any]]]:
    normalized = node_run.normalized_output if isinstance(node_run.normalized_output, dict) else {}
    output = node_run.output_payload if isinstance(node_run.output_payload, dict) else {}
    media_type = _media_type(node_run.node_type, normalized)
    raw_items = output.get('data') if media_type in {'image', 'video'} else None
    if not isinstance(raw_items, list) or not raw_items:
        artifact = (
            normalized.get('video_url') or normalized.get('videoUrl')
            or normalized.get('image_url') or normalized.get('imageUrl') or ''
        )
        return [(artifact, deepcopy(normalized or output))]

    candidates = []
    for item in raw_items:
        artifact = _artifact_from_item(item, media_type)
        if not artifact:
            continue
        content = deepcopy(normalized)
        if media_type == 'image':
            content.update({'imageUrl': artifact, 'image_url': artifact})
        else:
            content.update({'videoUrl': artifact, 'video_url': artifact})
        if isinstance(item, dict):
            content['provider_result'] = deepcopy(item)
        candidates.append((artifact, content))
    return candidates or [('', deepcopy(normalized or output))]


def _integer_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None and value != '' else None
    except (TypeError, ValueError):
        return None


def _candidate_seed(
    content: Dict[str, Any],
    output_payload: Dict[str, Any],
    result_index: int,
    fallback: Optional[int],
) -> Optional[int]:
    provider_result = content.get('provider_result') if isinstance(content, dict) else {}
    for value in (
        provider_result.get('seed') if isinstance(provider_result, dict) else None,
        content.get('seed') if isinstance(content, dict) else None,
    ):
        parsed = _integer_or_none(value)
        if parsed is not None:
            return parsed
    metadata = output_payload.get('metadata') if isinstance(output_payload.get('metadata'), dict) else {}
    seeds = metadata.get('seeds')
    if isinstance(seeds, list) and result_index < len(seeds):
        parsed = _integer_or_none(seeds[result_index])
        if parsed is not None:
            return parsed
    metadata_seed = _integer_or_none(metadata.get('seed'))
    return metadata_seed if metadata_seed is not None else fallback


def _trace_references(value: Any, *, path: str = '', image_only: bool = False) -> List[Dict[str, str]]:
    """Return stable URL/id references with their source path for lineage inspection."""
    references: List[Dict[str, str]] = []
    seen = set()

    def visit(item: Any, item_path: str, parent_key: str = '') -> None:
        normalized_key = parent_key.lower().replace('-', '_')
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f'{item_path}.{key}' if item_path else str(key)
                visit(child, child_path, str(key))
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f'{item_path}.{index}', parent_key)
            return
        if not isinstance(item, str) or not item:
            return

        is_url = item.startswith(('http://', 'https://', 'data:', '/api/'))
        is_identifier = normalized_key.endswith(('_asset_id', '_material_id')) or normalized_key in {
            'asset_id', 'material_id',
        }
        is_image = (
            normalized_key in IMAGE_TRACE_KEYS
            or 'image' in normalized_key
            or 'frame' in normalized_key
            or any(part in item_path.lower() for part in ('image', 'frame'))
        )
        if (image_only and not (is_url and is_image)) or (not image_only and not (is_url or is_identifier)):
            return
        identity = ('url' if is_url else 'id', item)
        if identity in seen:
            return
        seen.add(identity)
        references.append({identity[0]: item, 'path': item_path})

    visit(value, path)
    return references


def _candidate_ancestry(parent_candidate: Optional[WorkflowResultCandidate]) -> List[str]:
    ancestry = []
    seen = set()
    current = parent_candidate
    while current and current.id not in seen:
        seen.add(current.id)
        ancestry.append(str(current.id))
        current = current.parent_candidate
    return ancestry


def _serialize_upstream_candidate(candidate: WorkflowResultCandidate, source_node_id: Any) -> Dict[str, Any]:
    return {
        'candidate_id': str(candidate.id),
        'node_id': str(source_node_id),
        'node_run_id': str(candidate.node_run_id),
        'media_type': candidate.media_type,
        'artifact_url': candidate.artifact_url,
        'prompt': candidate.prompt,
        'model': candidate.model_name,
        'model_version': candidate.model_version,
        'seed': candidate.seed,
        'workflow_version': candidate.workflow_version,
        'canvas_revision': candidate.canvas_revision,
    }


def snapshot_upstream_candidate_lineage(
    node_run: WorkflowNodeRun,
    effective_input: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Resolve the exact upstream candidates before execution, preferring artifact matches."""
    if not node_run.node_id or not node_run.canvas_id:
        return []
    source_node_ids = node_run.canvas.edges.filter(
        target_node_id=node_run.node_id,
        is_enabled=True,
    ).values_list('source_node_id', flat=True)
    effective_urls = {
        item.get('url')
        for item in _trace_references(effective_input or {}, path='parameters')
        if item.get('url')
    }
    upstream = []
    for source_node_id in source_node_ids:
        candidates = list(
            WorkflowResultCandidate.objects
            .filter(node_id=source_node_id)
            .select_related('node_run')
            .order_by('-created_at', 'result_index')
        )
        candidate = next(
            (item for item in candidates if item.artifact_url and item.artifact_url in effective_urls),
            None,
        )
        candidate = candidate or next((item for item in candidates if item.status == 'adopted'), None)
        candidate = candidate or (candidates[0] if candidates else None)
        if candidate:
            upstream.append(_serialize_upstream_candidate(candidate, source_node_id))
    return upstream


def _upstream_candidate_lineage(node_run: WorkflowNodeRun) -> List[Dict[str, Any]]:
    upstream_snapshot = node_run.upstream_snapshot if isinstance(node_run.upstream_snapshot, dict) else {}
    frozen = upstream_snapshot.get('upstream_candidates')
    if isinstance(frozen, list):
        return deepcopy([item for item in frozen if isinstance(item, dict)])
    effective_input = (
        node_run.resolved_input_payload
        if isinstance(node_run.resolved_input_payload, dict)
        else {}
    )
    return snapshot_upstream_candidate_lineage(node_run, effective_input)


def create_candidates_for_run(node_run: WorkflowNodeRun) -> List[WorkflowResultCandidate]:
    """Persist each provider result once without changing older candidates."""
    existing = list(node_run.candidates.all())
    if existing:
        return existing

    requested_input = node_run.input_payload if isinstance(node_run.input_payload, dict) else {}
    input_payload = (
        node_run.resolved_input_payload
        if isinstance(node_run.resolved_input_payload, dict) and node_run.resolved_input_payload
        else requested_input
    )
    normalized = node_run.normalized_output if isinstance(node_run.normalized_output, dict) else {}
    output = node_run.output_payload if isinstance(node_run.output_payload, dict) else {}
    model_snapshot = node_run.model_snapshot if isinstance(node_run.model_snapshot, dict) else {}
    workflow_run = node_run.workflow_run
    parent_candidate = None
    parent_candidate_id = input_payload.get('parent_candidate_id')
    if parent_candidate_id:
        ownership_filter = (
            Q(node__canvas_id=node_run.canvas_id)
            if node_run.canvas_id
            else Q(node_run__workflow_run_id=node_run.workflow_run_id)
        )
        parent_candidate = WorkflowResultCandidate.objects.filter(
            ownership_filter,
            id=parent_candidate_id,
        ).first()

    media_type = _media_type(node_run.node_type, normalized)
    model_name = str(
        normalized.get('model') or output.get('model') or model_snapshot.get('model_name')
        or input_payload.get('model') or ''
    )
    model_version = str(
        model_snapshot.get('version') or model_snapshot.get('model_version')
        or output.get('model_version') or model_name
    )
    canvas = node_run.canvas
    workflow_version = int(
        model_snapshot.get('workflow_version')
        or (getattr(workflow_run, 'workflow_version', 1) if workflow_run else 0)
        or (canvas.definition.version if canvas and canvas.definition_id else 1)
    )
    canvas_revision = str(
        model_snapshot.get('canvas_revision')
        or (getattr(workflow_run, 'canvas_revision', '') if workflow_run else '')
        or ((canvas.graph_metadata or {}).get('revision') if canvas else '')
        or (canvas.updated_at.isoformat() if canvas else '')
    )
    prompt = str(input_payload.get('prompt') or normalized.get('prompt') or '')
    seed = _integer_or_none(input_payload.get('seed'))
    upstream_snapshot = deepcopy(node_run.upstream_snapshot or {})
    upstream_candidates = _upstream_candidate_lineage(node_run)
    branch_root_candidate_id = ''
    if parent_candidate:
        branch_root_candidate_id = str(
            (parent_candidate.lineage or {}).get('branch_root_candidate_id') or parent_candidate.id
        )
    lineage_base = {
        'schema_version': 1,
        'workflow_run_id': str(node_run.workflow_run_id or ''),
        'node_run_id': str(node_run.id),
        'node_id': str(node_run.node_id or ''),
        'node_key': node_run.node_key,
        'node_type': node_run.node_type,
        'parent_candidate_id': str(parent_candidate.id) if parent_candidate else '',
        'branch_root_candidate_id': branch_root_candidate_id,
        'ancestry_candidate_ids': _candidate_ancestry(parent_candidate),
        'upstream': upstream_snapshot,
        'upstream_candidates': upstream_candidates,
        'prompt': prompt,
        'model': model_name,
        'model_version': model_version,
        'parameters': deepcopy(input_payload),
        'requested_parameters': deepcopy(requested_input),
        'seed': seed,
        'workflow_version': workflow_version,
        'canvas_revision': canvas_revision,
    }
    material_references = _trace_references(upstream_snapshot, path='upstream')
    for reference in _trace_references(input_payload, path='parameters'):
        if reference not in material_references:
            material_references.append(reference)
    intermediate_frames = (
        _trace_references(input_payload, path='parameters', image_only=True)
        if media_type == 'video'
        else []
    )
    rows = []
    for index, (artifact_url, content) in enumerate(_candidate_items(node_run)):
        result_seed = _candidate_seed(content, output, index, seed)
        result_parameters = deepcopy(input_payload)
        if result_seed is not None:
            result_parameters['seed'] = result_seed
        lineage = {
            **deepcopy(lineage_base),
            'seed': result_seed,
            'parameters': deepcopy(result_parameters),
            'stages': {
                'materials': deepcopy(material_references),
                'prompt': {'text': prompt},
                'model': {
                    'name': model_name,
                    'version': model_version,
                    'seed': result_seed,
                },
                'parameters': deepcopy(result_parameters),
                'intermediate_frames': deepcopy(intermediate_frames),
                'output': {
                    'media_type': media_type,
                    'artifact_url': artifact_url,
                    'result_index': index,
                },
            },
        }
        rows.append(WorkflowResultCandidate(
            node_run=node_run,
            node=node_run.node,
            parent_candidate=parent_candidate,
            result_index=index,
            media_type=media_type,
            origin='branched' if parent_candidate else 'generated',
            artifact_url=artifact_url,
            content=content,
            prompt=prompt,
            model_name=model_name,
            model_version=model_version,
            parameters=result_parameters,
            seed=result_seed,
            workflow_version=workflow_version,
            canvas_revision=canvas_revision,
            lineage=deepcopy(lineage),
        ))
    created = WorkflowResultCandidate.objects.bulk_create(rows)
    create_node_run_event(node_run, 'candidates_created', {
        'candidate_ids': [str(candidate.id) for candidate in created],
        'count': len(created),
        'parent_candidate_id': str(parent_candidate.id) if parent_candidate else '',
    })
    return created


@transaction.atomic
def set_candidate_status(candidate: WorkflowResultCandidate, status: str) -> WorkflowResultCandidate:
    """Review a candidate; adopting it also makes its content the node's active output."""
    candidate_id = candidate.id
    node_id = candidate.node_id
    if status == 'adopted' and node_id:
        WorkflowNode.objects.select_for_update().get(id=node_id)
    candidate = (
        WorkflowResultCandidate.objects.select_for_update()
        .select_related('node', 'node_run')
        .get(id=candidate_id)
    )
    if status == 'adopted' and candidate.node_id:
        WorkflowResultCandidate.objects.filter(node_id=candidate.node_id, status='adopted').exclude(
            id=candidate.id,
        ).update(status='alternate', adopted_at=None, updated_at=timezone.now())
    candidate.status = status
    candidate.adopted_at = timezone.now() if status == 'adopted' else None
    candidate.save(update_fields=['status', 'adopted_at', 'updated_at'])
    if status == 'adopted' and candidate.node_id:
        candidate.node.latest_output = candidate.content
        candidate.node.status = 'completed'
        candidate.node.save(update_fields=['latest_output', 'status', 'updated_at'])
    create_node_run_event(candidate.node_run, 'candidate_status_changed', {
        'candidate_id': str(candidate.id),
        'status': status,
    })
    return candidate


@transaction.atomic
def restore_candidate(candidate: WorkflowResultCandidate) -> WorkflowResultCandidate:
    """Create a new adopted revision from history, retaining the source candidate."""
    WorkflowNodeRun.objects.select_for_update().get(id=candidate.node_run_id)
    next_index = (
        WorkflowResultCandidate.objects.filter(node_run=candidate.node_run)
        .aggregate(value=Max('result_index'))['value'] or 0
    ) + 1
    restored_lineage = deepcopy(candidate.lineage)
    restored_lineage.update({
        'parent_candidate_id': str(candidate.id),
        'branch_root_candidate_id': str(
            restored_lineage.get('branch_root_candidate_id') or candidate.id
        ),
        'ancestry_candidate_ids': [
            str(candidate.id),
            *[str(item) for item in restored_lineage.get('ancestry_candidate_ids', [])],
        ],
        'restored_from_candidate_id': str(candidate.id),
    })
    if isinstance(restored_lineage.get('stages'), dict):
        restored_lineage['stages'] = deepcopy(restored_lineage['stages'])
        if isinstance(restored_lineage['stages'].get('output'), dict):
            restored_lineage['stages']['output']['result_index'] = next_index
    restored = WorkflowResultCandidate.objects.create(
        node_run=candidate.node_run,
        node=candidate.node,
        parent_candidate=candidate,
        result_index=next_index,
        media_type=candidate.media_type,
        origin='restored',
        artifact_url=candidate.artifact_url,
        content=deepcopy(candidate.content),
        prompt=candidate.prompt,
        model_name=candidate.model_name,
        model_version=candidate.model_version,
        parameters=deepcopy(candidate.parameters),
        seed=candidate.seed,
        workflow_version=candidate.workflow_version,
        canvas_revision=candidate.canvas_revision,
        lineage=restored_lineage,
    )
    restored = set_candidate_status(restored, 'adopted')
    create_node_run_event(candidate.node_run, 'candidate_restored', {
        'source_candidate_id': str(candidate.id),
        'candidate_id': str(restored.id),
    })
    return restored


@transaction.atomic
def reproduce_candidate(candidate: WorkflowResultCandidate) -> WorkflowNodeRun:
    """Run a new immutable attempt using the candidate's locked generation snapshot."""
    candidate = (
        WorkflowResultCandidate.objects.select_for_update()
        .select_related('node_run', 'node_run__workflow_run', 'node_run__canvas', 'node')
        .get(id=candidate.id)
    )
    source_run = candidate.node_run
    next_sequence = (
        WorkflowNodeRun.objects.filter(node=source_run.node)
        .aggregate(value=Max('sequence'))['value'] or 0
    ) + 1
    input_payload = deepcopy(candidate.parameters or {})
    input_payload.update({
        'prompt': candidate.prompt,
        'model': candidate.model_name,
        'model_version': candidate.model_version,
        'seed': candidate.seed,
        'parent_candidate_id': str(candidate.id),
    })
    run = WorkflowNodeRun.objects.create(
        workflow_run=source_run.workflow_run,
        canvas=source_run.canvas,
        node=source_run.node,
        node_key=source_run.node_key,
        node_type=source_run.node_type,
        status='pending',
        sequence=next_sequence,
        trigger_source='candidate_reproduce',
        input_payload=input_payload,
        resolved_input_payload=deepcopy(input_payload),
        upstream_snapshot=deepcopy(source_run.upstream_snapshot or {}),
        model_snapshot={
            **deepcopy(source_run.model_snapshot or {}),
            'model_name': candidate.model_name,
            'version': candidate.model_version,
            'locked': True,
            'workflow_version': candidate.workflow_version,
            'canvas_revision': candidate.canvas_revision,
            'source_candidate_id': str(candidate.id),
        },
        timeout_seconds=source_run.timeout_seconds,
        max_retries=source_run.max_retries,
    )
    create_node_run_event(run, 'candidate_reproduction_requested', {
        'source_candidate_id': str(candidate.id),
        'seed': candidate.seed,
        'model': candidate.model_name,
        'model_version': candidate.model_version,
        'workflow_version': candidate.workflow_version,
        'canvas_revision': candidate.canvas_revision,
    })
    from .services import enqueue_node_run
    enqueue_node_run(run)
    return run

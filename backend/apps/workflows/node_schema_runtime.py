"""Runtime helpers for workflow node schema definitions."""

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction
from jinja2 import Template, TemplateError

from .models import WorkflowEdge, WorkflowNode, WorkflowNodeRun, WorkflowNodeSchema


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if value is None or value == '':
        return []
    if isinstance(value, list):
        return [item for item in value if item]
    return [value]


def _append_unique(items: List[Any], value: Any) -> None:
    if not value or value in items:
        return
    items.append(value)


def _is_online_url(value: str) -> bool:
    return value.startswith(('http://', 'https://'))


def _extract_image_urls(payload: Any, *, prefer_online_url: bool = False) -> List[str]:
    """Extract image URLs from a workflow image node output payload."""
    if not isinstance(payload, dict):
        return []

    preferred_urls: List[str] = []
    fallback_urls: List[str] = []
    if prefer_online_url:
        for key in ('original_url', 'source_url'):
            value = payload.get(key)
            if isinstance(value, str) and _is_online_url(value.strip()):
                _append_unique(preferred_urls, value.strip())

    for key in ('image_url', 'imageUrl', 'source_image_url', 'url'):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            _append_unique(fallback_urls, value.strip())

    data = payload.get('data')
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                nested_values = _extract_image_urls(item, prefer_online_url=prefer_online_url)
                target_urls = preferred_urls if prefer_online_url and any(_is_online_url(value) for value in nested_values) else fallback_urls
                for value in nested_values:
                    _append_unique(target_urls, value)

    tiles = payload.get('tiles')
    if isinstance(tiles, list):
        for item in tiles:
            if isinstance(item, dict):
                nested_values = _extract_image_urls(item, prefer_online_url=prefer_online_url)
                target_urls = preferred_urls if prefer_online_url and any(_is_online_url(value) for value in nested_values) else fallback_urls
                for value in nested_values:
                    _append_unique(target_urls, value)

    storyboards = payload.get('storyboards')
    if isinstance(storyboards, list):
        for storyboard in storyboards:
            if not isinstance(storyboard, dict):
                continue
            images = storyboard.get('images')
            if isinstance(images, list):
                for image in images:
                    if isinstance(image, dict):
                        nested_values = _extract_image_urls(image, prefer_online_url=prefer_online_url)
                        target_urls = preferred_urls if prefer_online_url and any(_is_online_url(value) for value in nested_values) else fallback_urls
                        for value in nested_values:
                            _append_unique(target_urls, value)
    return preferred_urls if preferred_urls else fallback_urls


def _extract_text_prompt(payload: Any) -> str:
    """Extract the most useful text content from an upstream node payload."""
    if not isinstance(payload, dict):
        return ''

    for key in ('rewritten_text', 'source_text', 'raw_text', 'text', 'summary', 'prompt'):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _payload_from_upstream_run(
    node_run: WorkflowNodeRun,
    upstream_node: WorkflowNode,
    *,
    prefer_output_payload: bool = False,
) -> Dict[str, Any]:
    if not node_run.workflow_run_id:
        return {}

    upstream_run = (
        WorkflowNodeRun.objects
        .filter(
            workflow_run_id=node_run.workflow_run_id,
            node_id=upstream_node.id,
            status='completed',
        )
        .order_by('-sequence', '-created_at')
        .first()
    )
    if not upstream_run:
        return {}
    normalized_output = _as_dict(upstream_run.normalized_output)
    output_payload = _as_dict(upstream_run.output_payload)
    if prefer_output_payload:
        return {**normalized_output, **output_payload}
    return {**output_payload, **normalized_output}


def _merge_upstream_image_inputs(node_run: WorkflowNodeRun, input_payload: Dict[str, Any]) -> None:
    if node_run.node_type not in {'image_generation', 'video_generation'}:
        return
    if not node_run.node_id or not node_run.canvas_id:
        return

    upstream_nodes = list(
        WorkflowNode.objects
        .filter(
            outgoing_edges__canvas=node_run.canvas,
            outgoing_edges__target_node_id=node_run.node_id,
            outgoing_edges__is_enabled=True,
            node_type='image_generation',
            is_enabled=True,
        )
        .distinct()
    )
    if not upstream_nodes:
        return

    upstream_image_urls: List[str] = []
    prefer_online_url = node_run.node_type in {'image_generation', 'video_generation'}
    for upstream_node in upstream_nodes:
        payload = _payload_from_upstream_run(
            node_run,
            upstream_node,
            prefer_output_payload=prefer_online_url,
        ) or _as_dict(upstream_node.latest_output)
        for image_url in _extract_image_urls(payload, prefer_online_url=prefer_online_url):
            _append_unique(upstream_image_urls, image_url)

    if not upstream_image_urls:
        return

    if node_run.node_type == 'video_generation':
        image_urls = _as_list(input_payload.get('image_urls') or input_payload.get('images') or input_payload.get('source_images'))
        for image_url in upstream_image_urls:
            _append_unique(image_urls, image_url)
        if image_urls:
            input_payload['image_urls'] = image_urls
            input_payload.setdefault('source_images', image_urls)
            input_payload.setdefault('image_url', image_urls[0])
        return

    reference_images = _as_list(input_payload.get('source_images') or input_payload.get('images') or input_payload.get('image'))
    source_image_url = str(input_payload.get('source_image_url') or input_payload.get('image_url') or '').strip()
    if source_image_url:
        _append_unique(reference_images, source_image_url)
    for image_url in upstream_image_urls:
        _append_unique(reference_images, image_url)
    if reference_images:
        input_payload.setdefault('source_image_url', reference_images[0])
        input_payload['source_images'] = reference_images


def _merge_upstream_text_inputs(node_run: WorkflowNodeRun, input_payload: Dict[str, Any]) -> None:
    if node_run.node_type != 'video_generation':
        return
    if str(input_payload.get('prompt') or '').strip():
        return
    if not node_run.node_id or not node_run.canvas_id:
        return

    upstream_nodes = list(
        WorkflowNode.objects
        .filter(
            outgoing_edges__canvas=node_run.canvas,
            outgoing_edges__target_node_id=node_run.node_id,
            outgoing_edges__is_enabled=True,
            is_enabled=True,
        )
        .exclude(node_type='image_generation')
        .distinct()
    )
    if not upstream_nodes:
        return

    upstream_texts: List[str] = []
    for upstream_node in upstream_nodes:
        payload = _payload_from_upstream_run(node_run, upstream_node) or _as_dict(upstream_node.latest_output)
        text_prompt = _extract_text_prompt(payload)
        if text_prompt:
            _append_unique(upstream_texts, text_prompt)

    if not upstream_texts:
        return

    input_payload['prompt'] = '\n\n'.join(upstream_texts)
    input_payload.setdefault('text', upstream_texts[0])


def _get_path(data: Any, path: str, default: Any = None) -> Any:
    """Resolve a simple dot path with numeric list indexes."""
    if not path:
        return data
    current = data
    for part in str(path).split('.'):
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(part, default)
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else default
            continue
        return default
    return current


def _render_string(value: str, context: Dict[str, Any]) -> str:
    try:
        return Template(value).render(**context)
    except TemplateError:
        return value


def _render_value(value: Any, context: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_string(value, context)
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item, context) for key, item in value.items()}
    return value


def _schema_key_from_run(node_run: WorkflowNodeRun) -> str:
    input_payload = _as_dict(node_run.input_payload)
    node_config = _as_dict(getattr(node_run.node, 'config_data', None)) if node_run.node_id else {}
    output_schema = _as_dict(getattr(node_run.node, 'output_schema', None)) if node_run.node_id else {}
    return str(
        input_payload.get('node_schema_key')
        or input_payload.get('schema_key')
        or node_config.get('node_schema_key')
        or node_config.get('schema_key')
        or output_schema.get('node_schema_key')
        or output_schema.get('schema_key')
        or ''
    ).strip()


def resolve_node_schema(node_run: WorkflowNodeRun) -> Optional[WorkflowNodeSchema]:
    schema_key = _schema_key_from_run(node_run)
    if not schema_key:
        return None
    return WorkflowNodeSchema.objects.filter(key=schema_key, is_active=True).first()


def serialize_node_schema(schema: WorkflowNodeSchema) -> Dict[str, Any]:
    return {
        'key': schema.key,
        'name': schema.name,
        'description': schema.description,
        'system_prompt': schema.system_prompt,
        'schema_config': schema.schema_config or {},
        'ui_config': schema.ui_config or {},
    }


def prepare_node_run_input_payload(node_run: WorkflowNodeRun) -> Dict[str, Any]:
    input_payload = deepcopy(_as_dict(node_run.input_payload))
    _merge_upstream_image_inputs(node_run, input_payload)
    _merge_upstream_text_inputs(node_run, input_payload)
    schema = resolve_node_schema(node_run)
    if schema:
        input_payload['__node_schema'] = serialize_node_schema(schema)
        input_payload.setdefault('node_schema_key', schema.key)
    return input_payload


def render_schema_system_prompt(input_payload: Dict[str, Any], fallback: str) -> str:
    schema_payload = _as_dict(input_payload.get('__node_schema'))
    system_prompt = str(schema_payload.get('system_prompt') or '').strip()
    if not system_prompt:
        return fallback
    context = {
        **input_payload,
        'input': input_payload,
        'node_schema': schema_payload,
    }
    return _render_string(system_prompt, context).strip() or fallback


def apply_node_schema_output_normalization(
    node_run: WorkflowNodeRun,
    *,
    output_payload: Dict[str, Any],
    normalized_output: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach generic schema output metadata without breaking domain payloads."""
    schema = resolve_node_schema(node_run)
    if not schema:
        return normalized_output

    schema_config = _as_dict(schema.schema_config)
    output_schema = _as_dict(schema_config.get('output_schema'))
    normalized = deepcopy(_as_dict(normalized_output))
    raw_output = _as_dict(output_payload)

    def get_from_outputs(path: str) -> Any:
        value = _get_path(normalized, path)
        if value is None:
            value = _get_path(raw_output, path)
        return value

    items_path = str(output_schema.get('items_path') or '').strip()
    source_text_path = str(output_schema.get('source_text_path') or '').strip()
    summary_path = str(output_schema.get('summary_path') or '').strip()
    output_type = str(output_schema.get('output_type') or '').strip() or 'single'

    schema_output = {
        'output_type': output_type,
        'items_path': items_path,
        'source_text_path': source_text_path,
        'summary_path': summary_path,
    }
    if items_path:
        items = get_from_outputs(items_path)
        schema_output['items'] = items if isinstance(items, list) else []
    if source_text_path:
        schema_output['source_text'] = get_from_outputs(source_text_path) or ''
    if summary_path:
        schema_output['summary'] = get_from_outputs(summary_path) or ''

    normalized['schema_output'] = schema_output
    normalized['node_schema'] = {
        'key': schema.key,
        'name': schema.name,
    }
    return normalized


def _iter_schema_items(schema: WorkflowNodeSchema, normalized_output: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    schema_output = _as_dict(normalized_output.get('schema_output'))
    items = schema_output.get('items')
    if items is None:
        output_schema = _as_dict(_as_dict(schema.schema_config).get('output_schema'))
        items = _get_path(normalized_output, str(output_schema.get('items_path') or '').strip())
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _template_ref(value: Any, context: Dict[str, Any]) -> str:
    return str(_render_value(value, context) if value is not None else '').strip()


@transaction.atomic
def materialize_node_schema_subgraph(node_run: WorkflowNodeRun, normalized_output: Dict[str, Any]) -> Dict[str, int]:
    schema = resolve_node_schema(node_run)
    node = node_run.node
    if not schema or not node or not node.canvas_id:
        return {'nodes_created': 0, 'nodes_updated': 0, 'edges_created': 0, 'edges_updated': 0}

    schema_config = _as_dict(schema.schema_config)
    materialization = _as_dict(schema_config.get('materialization'))
    if materialization.get('mode') != 'per_item_subgraph':
        return {'nodes_created': 0, 'nodes_updated': 0, 'edges_created': 0, 'edges_updated': 0}

    graph = _as_dict(materialization.get('graph'))
    template_nodes = graph.get('nodes') if isinstance(graph.get('nodes'), list) else []
    template_edges = graph.get('edges') if isinstance(graph.get('edges'), list) else []
    if not template_nodes:
        return {'nodes_created': 0, 'nodes_updated': 0, 'edges_created': 0, 'edges_updated': 0}

    counts = {'nodes_created': 0, 'nodes_updated': 0, 'edges_created': 0, 'edges_updated': 0}
    items = list(_iter_schema_items(schema, _as_dict(normalized_output)))

    for item_index, item in enumerate(items, start=1):
        context = {
            'item': item,
            'index': item_index,
            'zero_index': item_index - 1,
            'parent': {
                'id': str(node.id),
                'node_key': node.node_key,
                'node_type': node.node_type,
                'title': node.title,
            },
            'node_run': {
                'id': str(node_run.id),
                'node_key': node_run.node_key,
                'node_type': node_run.node_type,
            },
            'output': normalized_output,
            'schema': serialize_node_schema(schema),
        }
        created_nodes_by_ref: Dict[str, WorkflowNode] = {
            '$parent': node,
            'parent': node,
            node.node_key: node,
        }

        for template_node in template_nodes:
            if not isinstance(template_node, dict):
                continue
            rendered_node = _render_value(template_node, context)
            template_key = str(template_node.get('node_key') or template_node.get('key') or '').strip()
            rendered_key = str(rendered_node.get('node_key') or rendered_node.get('key') or '').strip()
            if not rendered_key:
                rendered_key = f'{node.node_key}:{schema.key}:{item_index}:{template_key or len(created_nodes_by_ref)}'
            node_type = str(rendered_node.get('node_type') or '').strip()
            if not node_type:
                continue

            child_defaults = {
                'node_type': node_type,
                'title': str(rendered_node.get('title') or rendered_key),
                'status': str(rendered_node.get('status') or 'dirty'),
                'position_x': float(rendered_node.get('position_x') or (node.position_x + 360)),
                'position_y': float(rendered_node.get('position_y') or (node.position_y + (item_index - 1) * 180)),
                'width': int(rendered_node.get('width') or 320),
                'height': int(rendered_node.get('height') or 180),
                'config_data': _as_dict(rendered_node.get('config_data')),
                'input_mapping': _as_dict(rendered_node.get('input_mapping')),
                'output_schema': _as_dict(rendered_node.get('output_schema')),
                'is_enabled': bool(rendered_node.get('is_enabled', True)),
            }
            if 'latest_output' in rendered_node:
                child_defaults['latest_output'] = _as_dict(rendered_node.get('latest_output'))

            child_node, created = WorkflowNode.objects.update_or_create(
                canvas=node.canvas,
                node_key=rendered_key,
                defaults=child_defaults,
            )
            counts['nodes_created' if created else 'nodes_updated'] += 1
            if template_key:
                created_nodes_by_ref[template_key] = child_node
            created_nodes_by_ref[rendered_key] = child_node

        for template_edge in template_edges:
            if not isinstance(template_edge, dict):
                continue
            source_ref = _template_ref(template_edge.get('source_node') or template_edge.get('source'), context)
            target_ref = _template_ref(template_edge.get('target_node') or template_edge.get('target'), context)
            source_node = created_nodes_by_ref.get(source_ref)
            target_node = created_nodes_by_ref.get(target_ref)
            if not source_node or not target_node:
                continue
            edge_key = _template_ref(template_edge.get('edge_key') or template_edge.get('key'), context)
            if not edge_key:
                edge_key = f'{node.node_key}:{schema.key}:{item_index}:{source_node.node_key}->{target_node.node_key}'
            _, created = WorkflowEdge.objects.update_or_create(
                canvas=node.canvas,
                edge_key=edge_key,
                defaults={
                    'source_node': source_node,
                    'target_node': target_node,
                    'source_handle': _template_ref(template_edge.get('source_handle'), context),
                    'target_handle': _template_ref(template_edge.get('target_handle'), context),
                    'metadata': _as_dict(_render_value(template_edge.get('metadata') or {}, context)),
                    'is_enabled': bool(template_edge.get('is_enabled', True)),
                },
            )
            counts['edges_created' if created else 'edges_updated'] += 1

    return counts

"""Shot-list, canvas synchronization and continuity services."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import ContinuityIssue, ProductionScene, Shot, WorkflowNode


SHOT_CONFIG_FIELDS = (
    'title', 'description', 'prompt', 'shot_size', 'camera_angle',
    'focal_length_mm', 'camera_movement', 'duration_seconds', 'frame_rate',
    'aspect_ratio', 'pacing', 'continuity_data',
)
CONTINUITY_CATEGORIES = ('character', 'costume', 'prop', 'lighting', 'spatial', 'action')


def shot_snapshot(shot):
    return {
        field: float(getattr(shot, field))
        if field in {'duration_seconds', 'frame_rate'} else getattr(shot, field)
        for field in SHOT_CONFIG_FIELDS
    }


def shot_node_config(shot):
    final_take = shot.takes.filter(is_final=True).first()
    references = list(shot.references.values('reference_type', 'url', 'frame_time', 'sort_order'))
    return {
        'type': 'shot',
        'shot_id': str(shot.id),
        'scene_id': str(shot.scene_id),
        'scene_number': shot.scene.number,
        'shot_number': shot.number,
        **shot_snapshot(shot),
        'is_locked': shot.is_locked,
        'final_take': {
            'id': str(final_take.id),
            'number': final_take.number,
            'media_url': final_take.media_url,
            'thumbnail_url': final_take.thumbnail_url,
        } if final_take else None,
        'references': [
            {**item, 'frame_time': float(item['frame_time']) if item['frame_time'] is not None else None}
            for item in references
        ],
    }


@transaction.atomic
def sync_shots_to_canvas(canvas):
    """Materialize the ordered shot list into stable semantic canvas nodes."""
    shots = list(
        Shot.objects.select_for_update()
        .filter(scene__project=canvas.project)
        .select_related('scene')
        .prefetch_related('takes', 'references')
        .order_by('scene__number', 'number')
    )
    created = updated = locked = 0
    for index, shot in enumerate(shots):
        node_key = shot.canvas_node_key or f'shot:{shot.id}'
        node = WorkflowNode.objects.filter(canvas=canvas, node_key=node_key).first()
        config = shot_node_config(shot)
        defaults = {
            'node_type': 'shot',
            'title': shot.title or f'镜头 {shot.scene.number}-{shot.number}',
            'status': 'completed' if shot.status == 'approved' else 'idle',
            'position_x': 80 + (index % 4) * 380,
            'position_y': 80 + (index // 4) * 300,
            'width': 344,
            'height': 236,
            'config_data': config,
            'is_enabled': True,
        }
        if node is None:
            node = WorkflowNode.objects.create(canvas=canvas, node_key=node_key, **defaults)
            created += 1
        elif shot.is_locked:
            preserved = dict(node.config_data or {})
            preserved.update({
                'shot_id': str(shot.id), 'scene_id': str(shot.scene_id),
                'scene_number': shot.scene.number, 'shot_number': shot.number,
                'is_locked': True,
            })
            node.config_data = preserved
            node.title = defaults['title']
            node.save(update_fields=['config_data', 'title', 'updated_at'])
            locked += 1
        else:
            for field, value in defaults.items():
                setattr(node, field, value)
            node.save()
            updated += 1
        if shot.canvas_id != canvas.id or shot.canvas_node_key != node_key:
            shot.canvas = canvas
            shot.canvas_node_key = node_key
            shot.save(update_fields=['canvas', 'canvas_node_key', 'updated_at'])
    return {'created': created, 'updated': updated, 'locked': locked, 'total': len(shots)}


def _coerce_value(field, value):
    if field in {'duration_seconds', 'frame_rate'}:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
    if field == 'focal_length_mm':
        try:
            return int(value) if value not in ('', None) else None
        except (TypeError, ValueError):
            return None
    return value


@transaction.atomic
def sync_canvas_to_shots(canvas):
    """Apply semantic shot-node edits to the shot list without touching locks."""
    default_scene = None
    created = updated = locked = 0
    nodes = canvas.nodes.filter(node_type__in=['shot', 'shot_semantic']).order_by('position_y', 'position_x')
    for node in nodes:
        config = dict(node.config_data or {})
        shot = Shot.objects.select_for_update().filter(id=config.get('shot_id'), scene__project=canvas.project).first()
        if shot and shot.is_locked:
            locked += 1
            continue
        scene = ProductionScene.objects.filter(id=config.get('scene_id'), project=canvas.project).first()
        if scene is None:
            if default_scene is None:
                default_scene, _ = ProductionScene.objects.get_or_create(
                    project=canvas.project,
                    number=1,
                    defaults={'name': '未分场镜头', 'canvas': canvas},
                )
            scene = default_scene
        is_new = shot is None
        if is_new:
            requested_number = config.get('shot_number')
            number = int(requested_number) if str(requested_number or '').isdigit() else 0
            if not number or Shot.objects.filter(scene=scene, number=number).exists():
                number = (Shot.objects.filter(scene=scene).aggregate(value=Max('number'))['value'] or 0) + 1
            shot = Shot(scene=scene, canvas=canvas, canvas_node_key=node.node_key, number=number)
            created += 1
        else:
            updated += 1
        shot.scene = scene
        shot.canvas = canvas
        shot.canvas_node_key = node.node_key
        for field in SHOT_CONFIG_FIELDS:
            if field in config:
                value = _coerce_value(field, config[field])
                if value is not None or field == 'focal_length_mm':
                    setattr(shot, field, value)
        if not shot.title:
            shot.title = node.title
        if not is_new:
            shot.version = (shot.version or 0) + 1
        shot.save()
        config.update({'shot_id': str(shot.id), 'scene_id': str(scene.id), 'is_locked': False})
        node.config_data = config
        node.save(update_fields=['config_data', 'updated_at'])
    return {'created': created, 'updated': updated, 'locked': locked, 'total': nodes.count()}


@transaction.atomic
def check_project_continuity(project):
    """Compare each shot's outgoing state with the following shot's incoming state."""
    shots = list(Shot.objects.filter(scene__project=project).select_related('scene').order_by('scene__number', 'number'))
    active_keys = set()
    issues = []
    for previous, current in zip(shots, shots[1:]):
        previous_data = previous.continuity_data or {}
        current_data = current.continuity_data or {}
        for category in CONTINUITY_CATEGORIES:
            expected = previous_data.get(f'{category}_end', previous_data.get(category))
            actual = current_data.get(f'{category}_start', current_data.get(category))
            if expected is None or actual is None or expected == actual:
                continue
            issue, _ = ContinuityIssue.objects.update_or_create(
                from_shot=previous,
                to_shot=current,
                category=category,
                defaults={
                    'project': project,
                    'severity': 'error' if category in {'character', 'spatial', 'action'} else 'warning',
                    'message': f'{category} 在镜头 {previous.number} 与 {current.number} 之间不连续',
                    'expected_value': expected,
                    'actual_value': actual,
                    'status': 'open',
                },
            )
            active_keys.add((previous.id, current.id, category))
            issues.append(issue)
    stale = ContinuityIssue.objects.filter(project=project, status='open')
    for issue in stale:
        if (issue.from_shot_id, issue.to_shot_id, issue.category) not in active_keys:
            issue.status = 'resolved'
            issue.save(update_fields=['status', 'updated_at'])
    return issues


@transaction.atomic
def prepare_bulk_rerender(canvas, model_key='', shot_ids=None):
    """Mark unlocked shot nodes dirty and return an executable selection."""
    shots = Shot.objects.select_for_update().filter(scene__project=canvas.project, canvas=canvas)
    if shot_ids:
        shots = shots.filter(id__in=shot_ids)
    eligible = []
    skipped = []
    for shot in shots.select_related('scene'):
        if shot.is_locked:
            skipped.append({'shot_id': str(shot.id), 'reason': 'locked'})
            continue
        node = canvas.nodes.filter(node_key=shot.canvas_node_key).first()
        if node is None:
            skipped.append({'shot_id': str(shot.id), 'reason': 'missing_canvas_node'})
            continue
        config = dict(node.config_data or {})
        if model_key:
            config['model'] = model_key
        config['rerender_requested_at'] = timezone.now().isoformat()
        node.config_data = config
        node.status = 'dirty'
        node.save(update_fields=['config_data', 'status', 'updated_at'])
        eligible.append({'shot_id': str(shot.id), 'node_id': str(node.id), 'node_key': node.node_key})
    return {'eligible': eligible, 'skipped': skipped}

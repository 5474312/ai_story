"""工作流节点异步任务。"""

import logging
from celery.exceptions import MaxRetriesExceededError
from typing import Any, Dict

from celery import shared_task

from .models import WorkflowNodeRun
from .node_schema_runtime import prepare_node_run_input_payload
from .node_executors import (
    execute_asset_extraction,
    execute_audio,
    execute_dynamic_schema,
    execute_image_generation,
    execute_rewrite,
    execute_storyboard,
    execute_video_generation,
    finalize_failure,
    finalize_success,
    mark_run_running,
)

logger = logging.getLogger(__name__)


def _dispatch_node_execution(node_run: WorkflowNodeRun) -> Dict[str, Any]:
    """根据节点类型分发到对应的执行函数。"""
    input_payload = prepare_node_run_input_payload(node_run)
    update_fields = []
    if node_run.resolved_input_payload != input_payload:
        node_run.resolved_input_payload = input_payload
        update_fields.append('resolved_input_payload')
    model_snapshot = node_run.model_snapshot if isinstance(node_run.model_snapshot, dict) else {}
    if not model_snapshot.get('locked'):
        from .candidate_services import snapshot_upstream_candidate_lineage
        upstream_snapshot = dict(node_run.upstream_snapshot or {})
        upstream_snapshot['upstream_candidates'] = snapshot_upstream_candidate_lineage(
            node_run,
            input_payload,
        )
        if node_run.upstream_snapshot != upstream_snapshot:
            node_run.upstream_snapshot = upstream_snapshot
            update_fields.append('upstream_snapshot')
    if update_fields:
        node_run.save(update_fields=[*update_fields, 'updated_at'])
    project = getattr(getattr(node_run, 'canvas', None), 'project', None)
    user_id = getattr(project, 'user_id', None)
    if node_run.node_type == 'rewrite':
        return execute_rewrite(input_payload, user_id=user_id)
    if node_run.node_type == 'asset_extraction':
        return execute_asset_extraction(node_run, input_payload)
    if node_run.node_type == 'storyboard':
        return execute_storyboard(node_run, input_payload)
    if node_run.node_type == 'image_generation':
        return execute_image_generation(input_payload, user_id=user_id)
    if node_run.node_type == 'video_generation':
        return execute_video_generation(input_payload, user_id=user_id)
    if node_run.node_type == 'audio':
        return execute_audio(input_payload)
    if node_run.node_type == 'dynamic_schema':
        return execute_dynamic_schema(node_run, input_payload)
    raise RuntimeError(f'暂不支持节点类型 {node_run.node_type} 的异步执行')


@shared_task(bind=True, autoretry_for=(), retry_backoff=False, retry_kwargs=None)
def execute_workflow_node_task(self, node_run_id: str) -> Dict[str, Any]:
    """异步执行单个工作流节点。"""
    node_run = mark_run_running(node_run_id, self.request.id or '')
    try:
        result = _dispatch_node_execution(node_run)
        finalize_success(
            node_run_id,
            output_payload=result['output_payload'],
            normalized_output=result['normalized_output'],
        )
        return {
            'success': True,
            'node_run_id': node_run_id,
            'task_id': self.request.id,
        }
    except Exception as exc:
        logger.exception('工作流节点执行失败: node_run_id=%s node_type=%s', node_run_id, node_run.node_type)
        # Keep the same node-run id across retries so the UI and audit trail
        # remain stable. Only terminal exhaustion becomes a failed run.
        latest = WorkflowNodeRun.objects.get(id=node_run_id)
        if latest.retry_count < latest.max_retries:
            latest.retry_count += 1
            latest.status = 'queued'
            latest.error_message = str(exc)
            latest.save(update_fields=['retry_count', 'status', 'error_message', 'updated_at'])
            try:
                raise self.retry(exc=exc, countdown=min(60, 2 ** latest.retry_count))
            except MaxRetriesExceededError:
                pass
        finalize_failure(node_run_id, str(exc))
        raise

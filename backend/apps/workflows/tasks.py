"""工作流节点异步任务。"""

import logging
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
        finalize_failure(node_run_id, str(exc))
        raise

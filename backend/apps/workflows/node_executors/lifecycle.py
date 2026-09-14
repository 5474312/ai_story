"""工作流节点运行的生命周期管理。"""

from typing import Any, Dict

from django.db import transaction
from django.utils import timezone

from ..models import WorkflowNode, WorkflowNodeRun
from ..node_schema_runtime import apply_node_schema_output_normalization
from ..services import (
    apply_workflow_node_result,
    block_downstream_pending_runs,
    can_auto_apply_workflow_node_result,
    create_node_run_event,
    handle_node_run_completed,
    launch_ready_node_runs,
    sync_workflow_run_status,
)


def mark_run_running(node_run_id: str, task_id: str = '') -> WorkflowNodeRun:
    """将节点运行标记为运行中状态。"""
    with transaction.atomic():
        node_run = WorkflowNodeRun.objects.select_related('node').get(id=node_run_id)
        node_run.status = 'running'
        node_run.error_message = ''
        node_run.started_at = node_run.started_at or timezone.now()
        update_fields = ['status', 'error_message', 'started_at', 'updated_at']
        if task_id and node_run.external_task_id != task_id:
            node_run.external_task_id = task_id
            update_fields.append('external_task_id')
        node_run.save(update_fields=update_fields)
        if node_run.node_id:
            WorkflowNode.objects.filter(id=node_run.node_id).update(
                status='running',
                updated_at=timezone.now(),
            )
        create_node_run_event(node_run, 'run_started', {'task_id': node_run.external_task_id or task_id})
        if node_run.workflow_run_id:
            sync_workflow_run_status(str(node_run.workflow_run_id))
        return node_run


def finalize_success(
    node_run_id: str,
    *,
    output_payload: Dict[str, Any],
    normalized_output: Dict[str, Any],
) -> None:
    """将节点运行标记为成功完成，并触发后续处理。"""
    with transaction.atomic():
        node_run = WorkflowNodeRun.objects.select_related('node', 'canvas', 'workflow_run').get(id=node_run_id)
        node_run.status = 'completed'
        node_run.output_payload = output_payload
        normalized_output = apply_node_schema_output_normalization(
            node_run,
            output_payload=output_payload,
            normalized_output=normalized_output,
        )
        node_run.normalized_output = normalized_output
        node_run.error_message = ''
        node_run.completed_at = timezone.now()
        node_run.save(
            update_fields=['status', 'output_payload', 'normalized_output', 'error_message', 'completed_at', 'updated_at']
        )
        create_node_run_event(node_run, 'run_completed', {'has_output': bool(normalized_output or output_payload)})
        handle_node_run_completed(node_run, latest_output=normalized_output)
        if node_run.workflow_run_id:
            launch_ready_node_runs(str(node_run.workflow_run_id))
            sync_workflow_run_status(str(node_run.workflow_run_id))
        if can_auto_apply_workflow_node_result(node_run):
            apply_workflow_node_result(node_run)


def finalize_failure(node_run_id: str, error_message: str) -> None:
    """将节点运行标记为失败。"""
    error_text = (error_message or '节点执行失败').strip()
    with transaction.atomic():
        node_run = WorkflowNodeRun.objects.select_related('node').get(id=node_run_id)
        node_run.status = 'failed'
        node_run.error_message = error_text
        node_run.completed_at = timezone.now()
        node_run.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        create_node_run_event(node_run, 'run_failed', {'error_message': error_text})
        if node_run.node_id:
            WorkflowNode.objects.filter(id=node_run.node_id).update(
                status='failed',
                updated_at=timezone.now(),
            )
        if node_run.workflow_run_id:
            block_downstream_pending_runs(node_run)
            sync_workflow_run_status(str(node_run.workflow_run_id))

"""工作流视图。"""

import json
import time
from datetime import date

from celery.result import AsyncResult
from django.db.models import Q
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import exceptions, renderers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    WorkflowBinding,
    WorkflowCallbackEvent,
    WorkflowCanvas,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeSchema,
    WorkflowNodeRun,
    WorkflowNodeRunEvent,
    WorkflowRun,
)
from .serializers import (
    WorkflowCanvasExecuteSelectionSerializer,
    WorkflowBindingSerializer,
    WorkflowCallbackEventSerializer,
    WorkflowCanvasCreateSerializer,
    WorkflowCanvasDetailSerializer,
    WorkflowCanvasGraphSerializer,
    WorkflowCanvasListSerializer,
    WorkflowDefinitionSerializer,
    WorkflowEdgeSerializer,
    WorkflowNodeExecuteSerializer,
    WorkflowNodeApplyResultSerializer,
    WorkflowNodeSchemaSerializer,
    WorkflowNodeRunCreateSerializer,
    WorkflowNodeRunEventSerializer,
    WorkflowNodeRunSerializer,
    WorkflowNodeRunUpdateSerializer,
    WorkflowNodeSerializer,
    WorkflowRunCreateSerializer,
    WorkflowRunDetailSerializer,
    WorkflowRunListSerializer,
)
from .services import apply_workflow_node_result, enqueue_node_run
from .tasks import execute_workflow_node_task


SERVICE_CUTOFF_DATE = date(2026, 7, 30)


def _service_expired():
    return timezone.localdate() > SERVICE_CUTOFF_DATE


def _service_expired_response():
    return JsonResponse(
        {
            'error': '服务已到期，暂不可用',
            'code': 'service_expired',
        },
        status=503,
        json_dumps_params={'ensure_ascii': False},
    )


class ExpiringWorkflowMixin:
    def dispatch(self, request, *args, **kwargs):
        if _service_expired():
            return _service_expired_response()
        return super().dispatch(request, *args, **kwargs)


class ServerSentEventRenderer(renderers.BaseRenderer):
    media_type = 'text/event-stream'
    format = 'event-stream'
    charset = 'utf-8'
    render_style = 'binary'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


def build_sse_response(event_iterable):
    response = StreamingHttpResponse(event_iterable, content_type='text/event-stream; charset=utf-8')
    response['Cache-Control'] = 'no-cache, no-transform'
    response['X-Accel-Buffering'] = 'no'
    return response


def iter_workflow_event_stream(queryset, *, connected_payload, terminal_checker):
    yield f"data: {json.dumps(connected_payload, ensure_ascii=False)}\n\n"
    seen_event_ids = set()
    idle_count = 0

    for _ in range(600):
        latest_events = list(queryset.order_by('created_at', 'id'))
        new_events = [event for event in latest_events if str(event.id) not in seen_event_ids]

        changed = bool(new_events)
        for event in new_events:
            payload = {
                'type': event.event_type,
                'event_id': str(event.id),
                'workflow_run_id': str(event.workflow_run_id) if event.workflow_run_id else '',
                'canvas_id': str(event.canvas_id) if event.canvas_id else '',
                'node_id': str(event.node_id) if event.node_id else '',
                'node_run_id': str(event.node_run_id) if event.node_run_id else '',
                'payload': event.payload or {},
                'created_at': event.created_at.isoformat() if event.created_at else None,
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            seen_event_ids.add(str(event.id))

        terminal_payload = terminal_checker()
        if terminal_payload is not None:
            yield f"data: {json.dumps(terminal_payload, ensure_ascii=False)}\n\n"
            break

        idle_count = 0 if changed else idle_count + 1
        time.sleep(3 if idle_count >= 3 else 1)

    yield f"data: {json.dumps({**connected_payload, 'type': 'stream_end'}, ensure_ascii=False)}\n\n"


class WorkflowDefinitionViewSet(ExpiringWorkflowMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowDefinitionSerializer
    queryset = WorkflowDefinition.objects.all().select_related('created_by')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['source_system', 'is_active', 'key']
    search_fields = ['key', 'name']
    ordering_fields = ['created_at', 'updated_at', 'version']
    ordering = ['key', '-version']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class WorkflowNodeSchemaViewSet(ExpiringWorkflowMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowNodeSchemaSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['key', 'name', 'description', 'system_prompt']
    ordering_fields = ['created_at', 'updated_at', 'key', 'name']
    ordering = ['key']

    def get_queryset(self):
        queryset = WorkflowNodeSchema.objects.all()
        user = self.request.user

        if not user.is_staff:
            queryset = queryset.filter(created_by=user)

        return queryset.select_related('created_by')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class WorkflowCanvasViewSet(ExpiringWorkflowMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'project', 'series', 'definition']
    search_fields = ['name', 'description', 'external_canvas_id']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        return (
            WorkflowCanvas.objects
            .filter(project__user=self.request.user)
            .filter(created_by=self.request.user)
            .select_related('definition', 'project', 'series', 'created_by')
            .prefetch_related('nodes', 'edges')
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return WorkflowCanvasCreateSerializer
        if self.action == 'retrieve':
            return WorkflowCanvasDetailSerializer
        if self.action == 'graph':
            return WorkflowCanvasGraphSerializer
        return WorkflowCanvasListSerializer

    @action(detail=True, methods=['patch'])
    def graph(self, request, pk=None):
        canvas = self.get_object()
        serializer = self.get_serializer(data=request.data, context={'canvas': canvas, 'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        detail = WorkflowCanvasDetailSerializer(canvas.refresh_from_db() or canvas, context=self.get_serializer_context())
        response_data = dict(detail.data)
        graph_validation = getattr(serializer, 'validation_result', {'validation_errors': [], 'blocked_nodes': []})
        response_data['validation_errors'] = graph_validation.get('validation_errors', [])
        response_data['blocked_nodes'] = graph_validation.get('blocked_nodes', [])
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def execute_selection(self, request, pk=None):
        canvas = self.get_object()
        serializer = WorkflowCanvasExecuteSelectionSerializer(data=request.data, context={'canvas': canvas, 'request': request})
        serializer.is_valid(raise_exception=True)
        runs = serializer.save()
        refreshed_runs = list(
            WorkflowNodeRun.objects
            .filter(id__in=[run.id for run in runs])
            .select_related('workflow_run', 'canvas', 'node')
            .prefetch_related('bindings')
            .order_by('created_at')
        )
        response_serializer = WorkflowNodeRunSerializer(refreshed_runs, many=True, context=self.get_serializer_context())
        return Response({
            'runs': response_serializer.data,
            'summary': {
                'total_count': len(refreshed_runs),
                'queued_count': len([run for run in refreshed_runs if run.status == 'queued']),
                'failed_count': len([run for run in refreshed_runs if run.status == 'failed']),
                'blocked_count': len([run for run in refreshed_runs if run.status == 'blocked']),
                'pending_count': len([run for run in refreshed_runs if run.status == 'pending']),
            },
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], renderer_classes=[ServerSentEventRenderer])
    def stream(self, request, pk=None):
        canvas = self.get_object()
        queryset = WorkflowNodeRunEvent.objects.filter(canvas=canvas)

        def terminal_checker():
            latest_run = (
                WorkflowRun.objects
                .filter(node_runs__canvas=canvas)
                .order_by('-created_at')
                .distinct()
                .first()
            )
            if not latest_run or latest_run.status not in {'completed', 'failed', 'cancelled'}:
                return None
            return {
                'type': 'pipeline_done' if latest_run.status == 'completed' else 'pipeline_error',
                'canvas_id': str(canvas.id),
                'workflow_run_id': str(latest_run.id),
                'status': latest_run.status,
                'error': latest_run.error_message or '',
            }

        return build_sse_response(iter_workflow_event_stream(
            queryset,
            connected_payload={'canvas_id': str(canvas.id), 'type': 'connected'},
            terminal_checker=terminal_checker,
        ))


class WorkflowNodeViewSet(ExpiringWorkflowMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowNodeSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['canvas', 'node_type', 'status', 'is_enabled']
    search_fields = ['node_key', 'title']
    ordering_fields = ['created_at', 'updated_at', 'node_key']
    ordering = ['created_at']

    def get_queryset(self):
        return (
            WorkflowNode.objects
            .filter(canvas__project__user=self.request.user, canvas__created_by=self.request.user)
            .select_related('canvas')
        )

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        node = self.get_object()
        serializer = WorkflowNodeExecuteSerializer(data=request.data, context={'node': node})
        serializer.is_valid(raise_exception=True)
        run = serializer.save()
        enqueue_node_run(run)
        run.refresh_from_db()
        response = WorkflowNodeRunSerializer(run, context=self.get_serializer_context())
        return Response(response.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def runs(self, request, pk=None):
        node = self.get_object()
        queryset = node.runs.select_related('canvas', 'node', 'workflow_run').prefetch_related('bindings').order_by('-sequence', '-created_at')
        serializer = WorkflowNodeRunSerializer(queryset, many=True, context=self.get_serializer_context())
        return Response(serializer.data)


class WorkflowEdgeViewSet(ExpiringWorkflowMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowEdgeSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['canvas', 'source_node', 'target_node', 'is_enabled']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['created_at']

    def get_queryset(self):
        return (
            WorkflowEdge.objects
            .filter(canvas__project__user=self.request.user, canvas__created_by=self.request.user)
            .select_related('canvas', 'source_node', 'target_node')
        )


class WorkflowRunViewSet(ExpiringWorkflowMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'trigger_mode', 'project', 'series', 'definition']
    search_fields = ['external_run_id', 'current_node_key']
    ordering_fields = ['created_at', 'updated_at', 'started_at', 'completed_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return (
            WorkflowRun.objects
            .filter(project__user=self.request.user, created_by=self.request.user)
            .select_related('definition', 'project', 'series', 'created_by')
            .prefetch_related('node_runs__bindings', 'bindings')
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return WorkflowRunCreateSerializer
        if self.action == 'retrieve':
            return WorkflowRunDetailSerializer
        return WorkflowRunListSerializer

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        workflow_run = self.get_object()
        workflow_run.status = 'running'
        workflow_run.started_at = workflow_run.started_at or timezone.now()
        workflow_run.error_message = ''
        workflow_run.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])
        return Response({'message': '工作流已启动', 'workflow_run_id': str(workflow_run.id)})

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        workflow_run = self.get_object()
        workflow_run.status = 'paused'
        workflow_run.save(update_fields=['status', 'updated_at'])
        return Response({'message': '工作流已暂停', 'workflow_run_id': str(workflow_run.id)})

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        workflow_run = self.get_object()
        workflow_run.status = 'running'
        workflow_run.save(update_fields=['status', 'updated_at'])
        return Response({'message': '工作流已恢复', 'workflow_run_id': str(workflow_run.id)})

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        workflow_run = self.get_object()
        workflow_run.status = 'pending'
        workflow_run.error_message = ''
        workflow_run.completed_at = None
        workflow_run.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
        workflow_run.node_runs.update(
            status='pending',
            error_message='',
            completed_at=None,
            started_at=None,
        )
        return Response({'message': '工作流已重置为待运行', 'workflow_run_id': str(workflow_run.id)})

    @action(detail=True, methods=['get'], renderer_classes=[ServerSentEventRenderer])
    def stream(self, request, pk=None):
        workflow_run = self.get_object()
        queryset = WorkflowNodeRunEvent.objects.filter(workflow_run=workflow_run)

        def terminal_checker():
            refreshed = WorkflowRun.objects.get(id=workflow_run.id)
            if refreshed.status not in {'completed', 'failed', 'cancelled'}:
                return None
            return {
                'type': 'pipeline_done' if refreshed.status == 'completed' else 'pipeline_error',
                'workflow_run_id': str(refreshed.id),
                'canvas_id': '',
                'status': refreshed.status,
                'error': refreshed.error_message or '',
            }

        return build_sse_response(iter_workflow_event_stream(
            queryset,
            connected_payload={'workflow_run_id': str(workflow_run.id), 'type': 'connected'},
            terminal_checker=terminal_checker,
        ))


class WorkflowNodeRunViewSet(ExpiringWorkflowMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['workflow_run', 'node_key', 'node_type', 'status']
    search_fields = ['external_task_id', 'idempotency_key']
    ordering_fields = ['created_at', 'updated_at', 'sequence']
    ordering = ['workflow_run', 'sequence']

    def perform_content_negotiation(self, request, force=False):
        try:
            return super().perform_content_negotiation(request, force)
        except exceptions.NotAcceptable:
            accept_header = request.META.get('HTTP_ACCEPT', '')
            if 'text/event-stream' in accept_header:
                renderer = ServerSentEventRenderer()
                return (renderer, renderer.media_type)
            raise

    def get_queryset(self):
        return (
            WorkflowNodeRun.objects
            .filter(
                Q(canvas__project__user=self.request.user, canvas__created_by=self.request.user) |
                Q(workflow_run__project__user=self.request.user, workflow_run__created_by=self.request.user)
            )
            .select_related('workflow_run', 'canvas', 'node')
            .prefetch_related('bindings')
            .distinct()
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return WorkflowNodeRunCreateSerializer
        if self.action in ['update', 'partial_update']:
            return WorkflowNodeRunUpdateSerializer
        return WorkflowNodeRunSerializer

    @action(detail=True, methods=['post'])
    def apply(self, request, pk=None):
        node_run = self.get_object()
        result = apply_workflow_node_result(node_run)
        serializer = WorkflowNodeApplyResultSerializer({
            'message': '节点结果已回填到 ai_story',
            'result': result,
            'node_run': node_run,
        })
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], renderer_classes=[ServerSentEventRenderer])
    def stream(self, request, pk=None):
        node_run = self.get_object()

        def event_stream():
            yield f"data: {json.dumps({'type': 'connected', 'node_run_id': str(node_run.id)}, ensure_ascii=False)}\n\n"
            last_payload = None
            last_task_state = None
            idle_count = 0
            for _ in range(600):
                refreshed = self.get_queryset().get(id=node_run.id)
                payload = {
                    'type': 'status',
                    'node_run_id': str(refreshed.id),
                    'task_id': refreshed.external_task_id or '',
                    'status': refreshed.status,
                    'node_type': refreshed.node_type,
                    'error_message': refreshed.error_message or '',
                    'normalized_output': refreshed.normalized_output or {},
                    'output_payload': refreshed.output_payload or {},
                    'started_at': refreshed.started_at.isoformat() if refreshed.started_at else None,
                    'completed_at': refreshed.completed_at.isoformat() if refreshed.completed_at else None,
                }
                changed = payload != last_payload
                if changed:
                    yield f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'
                    last_payload = payload

                if refreshed.external_task_id:
                    task_state = AsyncResult(refreshed.external_task_id).state
                    if task_state in {'PENDING', 'RECEIVED', 'STARTED', 'RETRY', 'SUCCESS', 'FAILURE', 'REVOKED'}:
                        if task_state != last_task_state:
                            meta_payload = {
                                'type': 'task_state',
                                'node_run_id': str(refreshed.id),
                                'task_id': refreshed.external_task_id,
                                'task_state': task_state,
                            }
                            yield f'data: {json.dumps(meta_payload, ensure_ascii=False)}\n\n'
                            last_task_state = task_state
                            changed = True

                if refreshed.status in {'completed', 'failed', 'cancelled'}:
                    final_type = 'done' if refreshed.status == 'completed' else 'error'
                    final_payload = {
                        'type': final_type,
                        'node_run_id': str(refreshed.id),
                        'task_id': refreshed.external_task_id or '',
                        'status': refreshed.status,
                        'normalized_output': refreshed.normalized_output or {},
                        'output_payload': refreshed.output_payload or {},
                        'error': refreshed.error_message or '',
                    }
                    yield f'data: {json.dumps(final_payload, ensure_ascii=False)}\n\n'
                    break

                idle_count = 0 if changed else idle_count + 1
                time.sleep(3 if idle_count >= 3 else 1)

            yield f"data: {json.dumps({'type': 'stream_end', 'node_run_id': str(node_run.id)}, ensure_ascii=False)}\n\n"

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache, no-transform'
        response['X-Accel-Buffering'] = 'no'
        return response


class WorkflowBindingViewSet(ExpiringWorkflowMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowBindingSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['workflow_run', 'node_run', 'binding_type']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['created_at']

    def get_queryset(self):
        return (
            WorkflowBinding.objects
            .filter(
                Q(canvas__project__user=self.request.user, canvas__created_by=self.request.user) |
                Q(workflow_run__project__user=self.request.user, workflow_run__created_by=self.request.user)
            )
            .select_related('workflow_run', 'canvas', 'node', 'node_run')
            .distinct()
        )


class WorkflowNodeRunEventViewSet(ExpiringWorkflowMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowNodeRunEventSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['workflow_run', 'canvas', 'node', 'node_run', 'event_type']
    ordering_fields = ['created_at']
    ordering = ['created_at']

    def get_queryset(self):
        return (
            WorkflowNodeRunEvent.objects
            .filter(
                Q(canvas__project__user=self.request.user, canvas__created_by=self.request.user) |
                Q(workflow_run__project__user=self.request.user, workflow_run__created_by=self.request.user)
            )
            .select_related('workflow_run', 'canvas', 'node', 'node_run')
            .distinct()
        )


class WorkflowCallbackEventViewSet(ExpiringWorkflowMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowCallbackEventSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['workflow_run', 'node_run', 'provider', 'process_status']
    ordering_fields = ['received_at', 'processed_at']
    ordering = ['-received_at']

    def get_queryset(self):
        return (
            WorkflowCallbackEvent.objects
            .filter(
                Q(canvas__project__user=self.request.user, canvas__created_by=self.request.user) |
                Q(workflow_run__project__user=self.request.user, workflow_run__created_by=self.request.user)
            )
            .select_related('workflow_run', 'canvas', 'node_run')
            .distinct()
        )

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        instance = self.get_queryset().get(pk=pk)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        response_serializer = self.get_serializer(event)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

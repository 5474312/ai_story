"""工作流序列化器。"""

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import serializers

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
from .node_schema_runtime import (
    apply_node_schema_output_normalization,
)
from .services import (
    apply_workflow_node_result,
    can_auto_apply_workflow_node_result,
    handle_node_run_completed,
    create_node_run_event,
    launch_ready_node_runs,
    mark_downstream_nodes_stale,
    topologically_sort_selected_nodes,
    validate_workflow_graph,
)


class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowDefinition
        fields = [
            'id', 'key', 'name', 'version', 'source_system', 'graph_schema',
            'is_active', 'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class WorkflowNodeSchemaSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = WorkflowNodeSchema
        fields = [
            'id', 'key', 'name', 'description', 'system_prompt', 'schema_config', 'ui_config',
            'is_active', 'created_by', 'created_by_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_by_name', 'created_at', 'updated_at']

    def validate_schema_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('schema_config 必须是对象')
        return value

    def validate_ui_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('ui_config 必须是对象')
        return value


class WorkflowEdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowEdge
        fields = [
            'id', 'canvas', 'edge_key', 'source_node', 'target_node',
            'source_handle', 'target_handle', 'metadata', 'is_enabled',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WorkflowNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowNode
        fields = [
            'id', 'canvas', 'node_key', 'node_type', 'title', 'status',
            'position_x', 'position_y', 'width', 'height', 'config_data',
            'input_mapping', 'output_schema', 'latest_output', 'is_enabled',
            'last_executed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_executed_at']


class WorkflowBindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowBinding
        fields = [
            'id', 'workflow_run', 'canvas', 'node', 'node_run',
            'binding_type', 'target_id', 'target_key', 'sequence_number',
            'metadata', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WorkflowNodeRunEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowNodeRunEvent
        fields = [
            'id', 'workflow_run', 'canvas', 'node', 'node_run',
            'event_type', 'payload', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class WorkflowNodeRunSerializer(serializers.ModelSerializer):
    bindings = WorkflowBindingSerializer(many=True, read_only=True)

    class Meta:
        model = WorkflowNodeRun
        fields = [
            'id', 'workflow_run', 'canvas', 'node', 'node_key', 'node_type',
            'status', 'sequence', 'trigger_source', 'external_task_id',
            'idempotency_key', 'input_payload', 'output_payload',
            'normalized_output', 'upstream_snapshot', 'error_message',
            'retry_count', 'started_at', 'completed_at', 'created_at',
            'updated_at', 'bindings',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WorkflowNodeRunCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowNodeRun
        fields = [
            'id', 'workflow_run', 'canvas', 'node', 'node_key', 'node_type',
            'status', 'sequence', 'trigger_source', 'external_task_id',
            'idempotency_key', 'input_payload', 'output_payload',
            'normalized_output', 'upstream_snapshot', 'error_message',
            'retry_count', 'started_at', 'completed_at',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        node = attrs.get('node')
        canvas = attrs.get('canvas')
        workflow_run = attrs.get('workflow_run')

        if node:
            attrs.setdefault('canvas', node.canvas)
            attrs.setdefault('node_key', node.node_key)
            attrs.setdefault('node_type', node.node_type)
        if canvas is None and workflow_run and getattr(workflow_run, 'project_id', None):
            canvas = WorkflowCanvas.objects.filter(project_id=workflow_run.project_id, created_by=workflow_run.created_by).order_by('-updated_at').first()
            if canvas:
                attrs['canvas'] = canvas
        if not attrs.get('canvas') and not attrs.get('workflow_run'):
            raise serializers.ValidationError('至少需要提供 canvas 或 workflow_run')
        if not attrs.get('node_key'):
            raise serializers.ValidationError({'node_key': '缺少 node_key'})
        if not attrs.get('node_type'):
            raise serializers.ValidationError({'node_type': '缺少 node_type'})
        return attrs


class WorkflowNodeRunUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowNodeRun
        fields = [
            'status', 'trigger_source', 'external_task_id', 'idempotency_key',
            'input_payload', 'output_payload', 'normalized_output',
            'upstream_snapshot', 'error_message', 'retry_count',
            'started_at', 'completed_at',
        ]


class WorkflowCanvasListSerializer(serializers.ModelSerializer):
    definition_key = serializers.CharField(source='definition.key', read_only=True)
    nodes_count = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowCanvas
        fields = [
            'id', 'name', 'description', 'definition', 'definition_key',
            'series', 'project', 'status', 'external_canvas_id',
            'graph_metadata', 'viewport', 'created_by',
            'nodes_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_nodes_count(self, obj):
        return obj.nodes.count()


class WorkflowCanvasDetailSerializer(serializers.ModelSerializer):
    definition = WorkflowDefinitionSerializer(read_only=True)
    nodes = WorkflowNodeSerializer(many=True, read_only=True)
    edges = WorkflowEdgeSerializer(many=True, read_only=True)

    class Meta:
        model = WorkflowCanvas
        fields = [
            'id', 'name', 'description', 'definition', 'series', 'project',
            'status', 'external_canvas_id', 'graph_metadata', 'viewport',
            'created_by', 'created_at', 'updated_at', 'nodes', 'edges',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class WorkflowCanvasCreateSerializer(serializers.ModelSerializer):
    definition_key = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = WorkflowCanvas
        fields = [
            'id', 'name', 'description', 'definition', 'definition_key',
            'series', 'project', 'status', 'external_canvas_id',
            'graph_metadata', 'viewport',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = request.user if request and request.user and request.user.is_authenticated else None
        project = attrs.get('project')
        series = attrs.get('series')
        if user:
            if project and project.user_id != user.id:
                raise serializers.ValidationError({'project': '不能使用其他用户的项目创建工作流'})
            if series and series.user_id != user.id:
                raise serializers.ValidationError({'series': '不能使用其他用户的作品创建工作流'})
            if project and series and project.series_id and project.series_id != series.id:
                raise serializers.ValidationError({'series': '作品与项目不匹配'})

        definition = attrs.get('definition')
        definition_key = (attrs.pop('definition_key', '') or '').strip()
        if not definition and definition_key:
            definition = WorkflowDefinition.objects.filter(key=definition_key, is_active=True).order_by('-version').first()
            if not definition:
                raise serializers.ValidationError({'definition_key': '未找到可用的工作流定义'})
            attrs['definition'] = definition
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class WorkflowGraphNodeInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    canvas = serializers.UUIDField(required=False)
    node_key = serializers.CharField(max_length=100)
    node_type = serializers.CharField(max_length=50)
    title = serializers.CharField(required=False, allow_blank=True, default='')
    status = serializers.ChoiceField(choices=WorkflowNode.STATUS_CHOICES)
    position_x = serializers.FloatField(required=False, default=0)
    position_y = serializers.FloatField(required=False, default=0)
    width = serializers.IntegerField(required=False, default=320)
    height = serializers.IntegerField(required=False, default=180)
    config_data = serializers.JSONField(required=False, default=dict)
    input_mapping = serializers.JSONField(required=False, default=dict)
    output_schema = serializers.JSONField(required=False, default=dict)
    latest_output = serializers.JSONField(required=False, default=dict)
    is_enabled = serializers.BooleanField(required=False, default=True)


class WorkflowGraphEdgeInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    canvas = serializers.UUIDField(required=False)
    edge_key = serializers.CharField(max_length=100)
    source_node = serializers.UUIDField()
    target_node = serializers.UUIDField()
    source_handle = serializers.CharField(required=False, allow_blank=True, default='')
    target_handle = serializers.CharField(required=False, allow_blank=True, default='')
    metadata = serializers.JSONField(required=False, default=dict)
    is_enabled = serializers.BooleanField(required=False, default=True)


class WorkflowCanvasGraphSerializer(serializers.Serializer):
    nodes = WorkflowGraphNodeInputSerializer(many=True)
    edges = WorkflowGraphEdgeInputSerializer(many=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        canvas = self.context['canvas']
        node_ids = set()
        node_keys = set()
        for node in attrs.get('nodes', []):
            node_canvas = node.get('canvas')
            if node_canvas and str(node_canvas.id if hasattr(node_canvas, 'id') else node_canvas) != str(canvas.id):
                raise serializers.ValidationError('nodes 中存在不属于当前 canvas 的记录')
            node_id = str(node.get('id') or '')
            if node_id:
                node_ids.add(node_id)
            node_key = node.get('node_key')
            if node_key in node_keys:
                raise serializers.ValidationError({'nodes': f'重复 node_key: {node_key}'})
            node_keys.add(node_key)
        validation = validate_workflow_graph(attrs.get('nodes', []), attrs.get('edges', []))
        if validation['validation_errors']:
            raise serializers.ValidationError({
                'validation_errors': validation['validation_errors'],
                'blocked_nodes': validation['blocked_nodes'],
            })
        self.validation_result = validation
        attrs['graph_validation'] = validation
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        canvas = self.context['canvas']
        nodes_data = self.validated_data.get('nodes', [])
        edges_data = self.validated_data.get('edges', [])
        previous_nodes = {
            str(node.id): {
                'node_key': node.node_key,
                'node_type': node.node_type,
                'title': node.title,
                'position_x': node.position_x,
                'position_y': node.position_y,
                'width': node.width,
                'height': node.height,
                'config_data': node.config_data,
                'input_mapping': node.input_mapping,
                'output_schema': node.output_schema,
                'is_enabled': node.is_enabled,
            }
            for node in canvas.nodes.all()
        }
        previous_edges = {
            str(edge.id): {
                'edge_key': edge.edge_key,
                'source_node_id': str(edge.source_node_id),
                'target_node_id': str(edge.target_node_id),
                'source_handle': edge.source_handle,
                'target_handle': edge.target_handle,
                'metadata': edge.metadata,
                'is_enabled': edge.is_enabled,
            }
            for edge in canvas.edges.all()
        }

        existing_nodes = {str(node.id): node for node in canvas.nodes.all()}
        kept_node_ids = set()
        key_to_node = {}
        changed_source_node_ids = set()

        for node_data in nodes_data:
            node_data = dict(node_data)
            node_id = str(node_data.pop('id', '') or '')
            node_data['canvas'] = canvas
            if node_id and node_id in existing_nodes:
                node = existing_nodes[node_id]
                previous = previous_nodes.get(node_id, {})
                has_changed = any(previous.get(field) != node_data.get(field) for field in [
                    'node_key', 'node_type', 'title', 'position_x', 'position_y',
                    'width', 'height', 'config_data', 'input_mapping',
                    'output_schema', 'is_enabled',
                ])
                for field, value in node_data.items():
                    setattr(node, field, value)
                node.save()
                if has_changed:
                    changed_source_node_ids.add(str(node.id))
            else:
                if node_id:
                    node = WorkflowNode.objects.create(id=node_id, **node_data)
                else:
                    node = WorkflowNode.objects.create(**node_data)
                changed_source_node_ids.add(str(node.id))
            kept_node_ids.add(str(node.id))
            key_to_node[node.node_key] = node

        removed_node_ids = list(canvas.nodes.exclude(id__in=kept_node_ids).values_list('id', flat=True))
        if removed_node_ids:
            changed_source_node_ids.update(str(node_id) for node_id in removed_node_ids)
        canvas.nodes.exclude(id__in=kept_node_ids).delete()

        existing_edges = {str(edge.id): edge for edge in canvas.edges.all()}
        kept_edge_ids = set()
        for edge_data in edges_data:
            edge_data = dict(edge_data)
            edge_id = str(edge_data.pop('id', '') or '')
            source_node = edge_data.get('source_node')
            target_node = edge_data.get('target_node')
            if not isinstance(source_node, WorkflowNode):
                source_node = WorkflowNode.objects.get(id=source_node, canvas=canvas)
            if not isinstance(target_node, WorkflowNode):
                target_node = WorkflowNode.objects.get(id=target_node, canvas=canvas)
            edge_data['canvas'] = canvas
            edge_data['source_node'] = source_node
            edge_data['target_node'] = target_node
            if edge_id and edge_id in existing_edges:
                edge = existing_edges[edge_id]
                previous = previous_edges.get(edge_id, {})
                has_changed = any(previous.get(field) != (
                    str(source_node.id) if field == 'source_node_id' else
                    str(target_node.id) if field == 'target_node_id' else
                    edge_data.get(field)
                ) for field in ['edge_key', 'source_node_id', 'target_node_id', 'source_handle', 'target_handle', 'metadata', 'is_enabled'])
                for field, value in edge_data.items():
                    setattr(edge, field, value)
                edge.save()
                if has_changed:
                    changed_source_node_ids.add(str(source_node.id))
            else:
                if edge_id:
                    edge = WorkflowEdge.objects.create(id=edge_id, **edge_data)
                else:
                    edge = WorkflowEdge.objects.create(**edge_data)
                changed_source_node_ids.add(str(source_node.id))
            kept_edge_ids.add(str(edge.id))

        removed_edges = canvas.edges.exclude(id__in=kept_edge_ids)
        changed_source_node_ids.update(str(node_id) for node_id in removed_edges.values_list('source_node_id', flat=True))
        removed_edges.delete()
        canvas.status = 'active'
        canvas.save(update_fields=['status', 'updated_at'])
        if changed_source_node_ids:
            mark_downstream_nodes_stale(canvas, changed_source_node_ids, include_sources=False)
        return canvas


class WorkflowNodeExecuteSerializer(serializers.Serializer):
    input_payload = serializers.JSONField(required=False, default=dict)
    trigger_source = serializers.CharField(required=False, allow_blank=True, default='manual')
    upstream_snapshot = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, default='')

    def save(self, **kwargs):
        node = self.context['node']
        sequence = (node.runs.aggregate(max_seq=Max('sequence')).get('max_seq') or 0) + 1
        run = WorkflowNodeRun.objects.create(
            canvas=node.canvas,
            node=node,
            node_key=node.node_key,
            node_type=node.node_type,
            status='pending',
            sequence=sequence,
            trigger_source=self.validated_data.get('trigger_source') or 'manual',
            input_payload=self.validated_data.get('input_payload') or {},
            upstream_snapshot=self.validated_data.get('upstream_snapshot') or {},
            idempotency_key=(self.validated_data.get('idempotency_key') or '').strip(),
        )
        node.status = 'queued'
        node.save(update_fields=['status', 'updated_at'])
        create_node_run_event(run, 'run_created', {
            'trigger_source': run.trigger_source,
            'sequence': run.sequence,
        })
        return run


class WorkflowSelectionNodeExecuteSerializer(serializers.Serializer):
    node_id = serializers.UUIDField()
    input_payload = serializers.JSONField(required=False, default=dict)
    trigger_source = serializers.CharField(required=False, allow_blank=True, default='manual')
    upstream_snapshot = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, default='')


class WorkflowCanvasExecuteSelectionSerializer(serializers.Serializer):
    nodes = WorkflowSelectionNodeExecuteSerializer(many=True)

    SUPPORTED_NODE_TYPES = {'rewrite', 'asset_extraction', 'storyboard', 'image_generation', 'video_generation', 'audio', 'dynamic_schema'}
    ACTIVE_NODE_STATUSES = {'queued', 'running', 'waiting_callback'}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        canvas = self.context['canvas']
        node_items = attrs.get('nodes') or []
        if len(node_items) < 1:
            raise serializers.ValidationError({'nodes': '至少选择 1 个节点才能执行'})

        node_ids = [str(item['node_id']) for item in node_items]
        if len(set(node_ids)) != len(node_ids):
            raise serializers.ValidationError({'nodes': '批量执行中包含重复节点'})

        nodes = list(
            WorkflowNode.objects
            .filter(canvas=canvas, id__in=node_ids, is_enabled=True)
            .only('id', 'canvas_id', 'node_key', 'node_type', 'title', 'status')
        )
        node_map = {str(node.id): node for node in nodes}
        missing_ids = [node_id for node_id in node_ids if node_id not in node_map]
        if missing_ids:
            raise serializers.ValidationError({'nodes': f'存在无效节点或节点尚未保存: {", ".join(missing_ids)}'})

        unsupported_nodes = [
            node.title or node.node_key
            for node in nodes
            if node.node_type not in self.SUPPORTED_NODE_TYPES
        ]
        if unsupported_nodes:
            raise serializers.ValidationError({
                'nodes': f'以下节点暂不支持并发执行: {", ".join(unsupported_nodes)}'
            })

        active_nodes = [
            node.title or node.node_key
            for node in nodes
            if node.status in self.ACTIVE_NODE_STATUSES
        ]
        if active_nodes:
            raise serializers.ValidationError({
                'nodes': f'以下节点正在执行中，暂不能重复发起: {", ".join(active_nodes)}'
            })

        attrs['selected_nodes'] = [node_map[node_id] for node_id in node_ids]
        try:
            attrs['ordered_node_ids'] = topologically_sort_selected_nodes(canvas, node_ids)
        except ValueError as exc:
            raise serializers.ValidationError({'nodes': str(exc)})
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        node_items = self.validated_data.get('nodes') or []
        selected_nodes = self.validated_data.get('selected_nodes') or []
        ordered_node_ids = self.validated_data.get('ordered_node_ids') or []
        item_map = {
            str(item['node_id']): item
            for item in node_items
        }
        request = self.context.get('request')
        canvas = self.context['canvas']
        workflow_run = WorkflowRun.objects.create(
            project=canvas.project,
            series=canvas.series,
            definition=canvas.definition,
            created_by=request.user if request and request.user and request.user.is_authenticated else None,
            status='pending',
            trigger_mode='manual',
        )
        runs = []
        node_by_id = {str(node.id): node for node in selected_nodes}

        for node_id in ordered_node_ids:
            node = node_by_id[node_id]
            item = item_map[str(node.id)]
            sequence = (node.runs.aggregate(max_seq=Max('sequence')).get('max_seq') or 0) + 1
            run = WorkflowNodeRun.objects.create(
                workflow_run=workflow_run,
                canvas=node.canvas,
                node=node,
                node_key=node.node_key,
                node_type=node.node_type,
                status='pending',
                sequence=sequence,
                trigger_source=item.get('trigger_source') or 'manual',
                input_payload=item.get('input_payload') or {},
                upstream_snapshot=item.get('upstream_snapshot') or {},
                idempotency_key=(item.get('idempotency_key') or '').strip(),
            )
            create_node_run_event(run, 'run_created', {
                'trigger_source': run.trigger_source,
                'sequence': run.sequence,
            })
            runs.append(run)

        launch_ready_node_runs(str(workflow_run.id))
        return runs


class WorkflowNodeApplyResultSerializer(serializers.Serializer):
    message = serializers.CharField(read_only=True)
    result = serializers.JSONField(read_only=True)
    node_run = WorkflowNodeRunSerializer(read_only=True)


class WorkflowRunListSerializer(serializers.ModelSerializer):
    definition_key = serializers.CharField(source='definition.key', read_only=True)

    class Meta:
        model = WorkflowRun
        fields = [
            'id', 'definition', 'definition_key', 'series', 'project', 'status',
            'trigger_mode', 'external_run_id', 'current_node_key', 'started_at',
            'completed_at', 'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class WorkflowRunDetailSerializer(serializers.ModelSerializer):
    definition = WorkflowDefinitionSerializer(read_only=True)
    node_runs = WorkflowNodeRunSerializer(many=True, read_only=True)
    bindings = WorkflowBindingSerializer(many=True, read_only=True)

    class Meta:
        model = WorkflowRun
        fields = [
            'id', 'definition', 'series', 'project', 'status', 'trigger_mode',
            'external_run_id', 'current_node_key', 'context_data', 'final_output',
            'error_message', 'started_at', 'completed_at', 'created_by',
            'created_at', 'updated_at', 'node_runs', 'bindings',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class WorkflowRunCreateSerializer(serializers.ModelSerializer):
    definition_key = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = WorkflowRun
        fields = [
            'id', 'definition', 'definition_key', 'series', 'project', 'status',
            'trigger_mode', 'external_run_id', 'current_node_key', 'context_data',
            'final_output',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        definition = attrs.get('definition')
        definition_key = (attrs.pop('definition_key', '') or '').strip()
        if not definition and definition_key:
            definition = WorkflowDefinition.objects.filter(key=definition_key, is_active=True).order_by('-version').first()
            if not definition:
                raise serializers.ValidationError({'definition_key': '未找到可用的工作流定义'})
            attrs['definition'] = definition
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class WorkflowCallbackEventSerializer(serializers.ModelSerializer):
    idempotency_key = serializers.CharField()
    workflow_run_id = serializers.UUIDField(write_only=True, required=False)
    canvas_id = serializers.UUIDField(write_only=True, required=False)
    node_id = serializers.UUIDField(write_only=True, required=False)
    node_run_id = serializers.UUIDField(write_only=True, required=False)
    external_run_id = serializers.CharField(write_only=True, required=False, allow_blank=True)
    status = serializers.CharField(write_only=True, required=False, allow_blank=True)
    normalized_output = serializers.JSONField(write_only=True, required=False)
    auto_apply = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = WorkflowCallbackEvent
        fields = [
            'id', 'workflow_run', 'canvas', 'node_run', 'provider', 'event_type',
            'idempotency_key', 'external_task_id', 'payload', 'process_status',
            'error_message', 'received_at', 'processed_at',
            'workflow_run_id', 'canvas_id', 'node_id', 'node_run_id',
            'external_run_id', 'status', 'normalized_output', 'auto_apply',
        ]
        read_only_fields = [
            'id', 'workflow_run', 'canvas', 'node_run', 'process_status',
            'error_message', 'received_at', 'processed_at',
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        workflow_run_id = attrs.pop('workflow_run_id', None)
        canvas_id = attrs.pop('canvas_id', None)
        node_id = attrs.pop('node_id', None)
        node_run_id = attrs.pop('node_run_id', None)
        external_run_id = (attrs.pop('external_run_id', '') or '').strip()

        workflow_run = None
        if workflow_run_id:
            workflow_run = WorkflowRun.objects.filter(id=workflow_run_id).first()
        elif external_run_id:
            workflow_run = WorkflowRun.objects.filter(external_run_id=external_run_id).order_by('-created_at').first()

        canvas = None
        if canvas_id:
            canvas = WorkflowCanvas.objects.filter(id=canvas_id).first()
        elif workflow_run and workflow_run.project_id:
            canvas = WorkflowCanvas.objects.filter(project_id=workflow_run.project_id, created_by=workflow_run.created_by).order_by('-updated_at').first()

        if not workflow_run and not canvas:
            raise serializers.ValidationError('缺少有效的 canvas_id 或 workflow_run_id')

        node_run = None
        if node_run_id:
            node_run = WorkflowNodeRun.objects.filter(id=node_run_id).first()
        elif attrs.get('external_task_id'):
            node_run = WorkflowNodeRun.objects.filter(
                external_task_id=attrs['external_task_id'],
            ).order_by('-created_at').first()
        elif node_id:
            node_run = WorkflowNodeRun.objects.filter(node_id=node_id).order_by('-created_at').first()

        if node_run and not canvas:
            canvas = node_run.canvas
        attrs['workflow_run'] = workflow_run
        attrs['canvas'] = canvas
        attrs['node_run'] = node_run
        return attrs

    def create(self, validated_data):
        status_value = (validated_data.pop('status', '') or '').strip()
        normalized_output = validated_data.pop('normalized_output', None)
        auto_apply = validated_data.pop('auto_apply', False)

        event, created = WorkflowCallbackEvent.objects.get_or_create(
            idempotency_key=validated_data['idempotency_key'],
            defaults=validated_data,
        )
        if not created:
            return event

        node_run = event.node_run
        try:
            if node_run:
                update_fields = []
                if status_value:
                    node_run.status = status_value
                    update_fields.append('status')
                    if status_value == 'running' and not node_run.started_at:
                        node_run.started_at = timezone.now()
                        update_fields.append('started_at')
                    if status_value == 'completed':
                        node_run.completed_at = timezone.now()
                        update_fields.append('completed_at')
                if event.external_task_id and not node_run.external_task_id:
                    node_run.external_task_id = event.external_task_id
                    update_fields.append('external_task_id')
                if event.payload:
                    node_run.output_payload = event.payload
                    update_fields.append('output_payload')
                if normalized_output is not None:
                    normalized_output = apply_node_schema_output_normalization(
                        node_run,
                        output_payload=event.payload or node_run.output_payload or {},
                        normalized_output=normalized_output,
                    )
                    node_run.normalized_output = normalized_output
                    update_fields.append('normalized_output')
                if update_fields:
                    node_run.save(update_fields=list(dict.fromkeys(update_fields)))
                    if status_value:
                        create_node_run_event(node_run, f'run_{status_value}', {
                            'source': 'callback',
                            'external_task_id': event.external_task_id or node_run.external_task_id,
                        })

                if node_run.node:
                    if status_value == 'completed':
                        handle_node_run_completed(node_run, latest_output=normalized_output)
                    else:
                        node_updates = ['updated_at']
                        if status_value:
                            node_run.node.status = 'failed' if status_value == 'failed' else 'running'
                            node_updates.append('status')
                        if normalized_output is not None:
                            node_run.node.latest_output = normalized_output
                            node_updates.append('latest_output')
                        node_run.node.save(update_fields=list(dict.fromkeys(node_updates)))

                should_apply = auto_apply or (
                    status_value == 'completed'
                    and can_auto_apply_workflow_node_result(node_run)
                )
                if should_apply:
                    apply_workflow_node_result(node_run)

            event.process_status = 'processed'
            event.processed_at = timezone.now()
            event.save(update_fields=['process_status', 'processed_at'])
        except Exception as exc:
            event.process_status = 'failed'
            event.error_message = str(exc)
            event.processed_at = timezone.now()
            event.save(update_fields=['process_status', 'error_message', 'processed_at'])
            raise

        return event

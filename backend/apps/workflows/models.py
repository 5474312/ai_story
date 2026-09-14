"""工作流编排模型。"""

import uuid

from django.contrib.auth import get_user_model
from django.db import models


User = get_user_model()


class WorkflowDefinition(models.Model):
    """工作流定义。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField('定义键', max_length=100)
    name = models.CharField('名称', max_length=255)
    version = models.PositiveIntegerField('版本', default=1)
    source_system = models.CharField('来源系统', max_length=50, default='linknow')
    graph_schema = models.JSONField('图定义', default=dict, blank=True)
    is_active = models.BooleanField('是否启用', default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_workflow_definitions',
        verbose_name='创建者',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_definitions'
        verbose_name = '工作流定义'
        verbose_name_plural = '工作流定义'
        ordering = ['key', '-version']
        constraints = [
            models.UniqueConstraint(
                fields=['key', 'version'],
                name='uniq_workflow_definition_key_version',
            ),
        ]
        indexes = [
            models.Index(fields=['source_system', 'is_active'], name='workflow_def_source_active_idx'),
        ]

    def __str__(self):
        return f'{self.key}@v{self.version}'


class WorkflowNodeSchema(models.Model):
    """节点结构定义。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField('结构键', max_length=100, unique=True)
    name = models.CharField('名称', max_length=255)
    description = models.TextField('描述', blank=True, default='')
    system_prompt = models.TextField('系统提示词', blank=True, default='')
    schema_config = models.JSONField('结构配置', default=dict, blank=True)
    ui_config = models.JSONField('界面配置', default=dict, blank=True)
    is_active = models.BooleanField('是否启用', default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workflow_node_schemas',
        verbose_name='创建者',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_node_schemas'
        verbose_name = '节点结构定义'
        verbose_name_plural = '节点结构定义'
        ordering = ['key']
        indexes = [
            models.Index(fields=['is_active'], name='wf_schema_active_idx'),
        ]

    def __str__(self):
        return f'{self.key}:{self.name}'


class WorkflowCanvas(models.Model):
    """无限画板工作流。"""

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('active', '激活'),
        ('archived', '归档'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField('画板名称', max_length=255)
    description = models.TextField('画板描述', blank=True, default='')
    definition = models.ForeignKey(
        'workflows.WorkflowDefinition',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='canvases',
        verbose_name='工作流模板',
    )
    series = models.ForeignKey(
        'projects.Series',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workflow_canvases',
        verbose_name='作品',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='workflow_canvases',
        verbose_name='项目',
    )
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')
    external_canvas_id = models.CharField('外部画板ID', max_length=255, blank=True, default='')
    graph_metadata = models.JSONField('画板元数据', default=dict, blank=True)
    viewport = models.JSONField('视口信息', default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workflow_canvases',
        verbose_name='创建者',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_canvases'
        verbose_name = '工作流画板'
        verbose_name_plural = '工作流画板'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='wf_canvas_proj_status_idx'),
            models.Index(fields=['external_canvas_id'], name='wf_canvas_external_idx'),
        ]

    def __str__(self):
        return self.name


class WorkflowNode(models.Model):
    """画板节点。"""

    STATUS_CHOICES = [
        ('idle', '空闲'),
        ('dirty', '待执行'),
        ('blocked', '已阻断'),
        ('queued', '已排队'),
        ('running', '运行中'),
        ('waiting_callback', '等待回调'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('stale', '结果过期'),
        ('cancelled', '已取消'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    canvas = models.ForeignKey(
        WorkflowCanvas,
        on_delete=models.CASCADE,
        related_name='nodes',
        verbose_name='画板',
    )
    node_key = models.CharField('节点键', max_length=100)
    node_type = models.CharField('节点类型', max_length=50)
    title = models.CharField('节点标题', max_length=255, blank=True, default='')
    status = models.CharField('节点状态', max_length=20, choices=STATUS_CHOICES, default='idle')
    position_x = models.FloatField('横坐标', default=0)
    position_y = models.FloatField('纵坐标', default=0)
    width = models.IntegerField('宽度', default=320)
    height = models.IntegerField('高度', default=180)
    config_data = models.JSONField('节点配置', default=dict, blank=True)
    input_mapping = models.JSONField('输入映射', default=dict, blank=True)
    output_schema = models.JSONField('输出结构', default=dict, blank=True)
    latest_output = models.JSONField('最近一次输出', default=dict, blank=True)
    is_enabled = models.BooleanField('是否启用', default=True)
    last_executed_at = models.DateTimeField('最近执行时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_nodes'
        verbose_name = '工作流节点'
        verbose_name_plural = '工作流节点'
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['canvas', 'node_key'], name='uniq_wf_canvas_node_key'),
        ]
        indexes = [
            models.Index(fields=['canvas', 'status'], name='wf_node_canvas_status_idx'),
        ]

    def __str__(self):
        return self.title or self.node_key


class WorkflowEdge(models.Model):
    """节点连线。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    canvas = models.ForeignKey(
        WorkflowCanvas,
        on_delete=models.CASCADE,
        related_name='edges',
        verbose_name='画板',
    )
    edge_key = models.CharField('连线键', max_length=100)
    source_node = models.ForeignKey(
        WorkflowNode,
        on_delete=models.CASCADE,
        related_name='outgoing_edges',
        verbose_name='源节点',
    )
    target_node = models.ForeignKey(
        WorkflowNode,
        on_delete=models.CASCADE,
        related_name='incoming_edges',
        verbose_name='目标节点',
    )
    source_handle = models.CharField('源锚点', max_length=100, blank=True, default='')
    target_handle = models.CharField('目标锚点', max_length=100, blank=True, default='')
    metadata = models.JSONField('连线元数据', default=dict, blank=True)
    is_enabled = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_edges'
        verbose_name = '工作流连线'
        verbose_name_plural = '工作流连线'
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['canvas', 'edge_key'], name='uniq_wf_canvas_edge_key'),
        ]
        indexes = [
            models.Index(fields=['canvas', 'is_enabled'], name='wf_edge_canvas_enabled_idx'),
        ]

    def __str__(self):
        return self.edge_key


class WorkflowRun(models.Model):
    """旧版整体工作流运行实例，保留兼容。"""

    STATUS_CHOICES = [
        ('pending', '待运行'),
        ('running', '运行中'),
        ('paused', '已暂停'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]

    TRIGGER_MODE_CHOICES = [
        ('manual', '手动'),
        ('api', 'API'),
        ('callback', '回调'),
        ('retry', '重试'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.ForeignKey(
        'workflows.WorkflowDefinition',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='runs',
        verbose_name='工作流定义',
    )
    series = models.ForeignKey(
        'projects.Series',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workflow_runs',
        verbose_name='作品',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workflow_runs',
        verbose_name='项目',
    )
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    trigger_mode = models.CharField('触发方式', max_length=20, choices=TRIGGER_MODE_CHOICES, default='api')
    external_run_id = models.CharField('外部运行ID', max_length=255, blank=True, default='')
    current_node_key = models.CharField('当前节点键', max_length=100, blank=True, default='')
    context_data = models.JSONField('上下文数据', default=dict, blank=True)
    final_output = models.JSONField('最终输出', default=dict, blank=True)
    error_message = models.TextField('错误信息', blank=True, default='')
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workflow_runs',
        verbose_name='创建者',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_runs'
        verbose_name = '工作流运行'
        verbose_name_plural = '工作流运行'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status'], name='wf_run_proj_status_idx'),
            models.Index(fields=['external_run_id'], name='wf_run_external_idx'),
        ]

    def __str__(self):
        return f'WorkflowRun<{self.id}>'


class WorkflowNodeRun(models.Model):
    """工作流节点运行。"""

    STATUS_CHOICES = [
        ('pending', '待运行'),
        ('blocked', '已阻断'),
        ('queued', '已排队'),
        ('running', '运行中'),
        ('waiting_callback', '等待回调'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_run = models.ForeignKey(
        WorkflowRun,
        on_delete=models.CASCADE,
        related_name='node_runs',
        null=True,
        blank=True,
        verbose_name='工作流运行',
    )
    canvas = models.ForeignKey(
        WorkflowCanvas,
        on_delete=models.CASCADE,
        related_name='node_runs',
        null=True,
        blank=True,
        verbose_name='画板',
    )
    node = models.ForeignKey(
        WorkflowNode,
        on_delete=models.SET_NULL,
        related_name='runs',
        null=True,
        blank=True,
        verbose_name='节点',
    )
    node_key = models.CharField('节点键', max_length=100)
    node_type = models.CharField('节点类型', max_length=50)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    sequence = models.PositiveIntegerField('序号', default=1)
    trigger_source = models.CharField('触发来源', max_length=50, blank=True, default='manual')
    external_task_id = models.CharField('外部任务ID', max_length=255, blank=True, default='')
    idempotency_key = models.CharField('幂等键', max_length=255, blank=True, default='')
    input_payload = models.JSONField('输入', default=dict, blank=True)
    output_payload = models.JSONField('输出', default=dict, blank=True)
    normalized_output = models.JSONField('标准化输出', default=dict, blank=True)
    upstream_snapshot = models.JSONField('上游快照', default=dict, blank=True)
    error_message = models.TextField('错误信息', blank=True, default='')
    retry_count = models.PositiveIntegerField('重试次数', default=0)
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_node_runs'
        verbose_name = '工作流节点运行'
        verbose_name_plural = '工作流节点运行'
        ordering = ['sequence', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['workflow_run', 'node_key', 'sequence'],
                name='uniq_workflow_run_node_sequence',
            ),
            models.UniqueConstraint(
                fields=['canvas', 'node', 'sequence'],
                condition=models.Q(canvas__isnull=False, node__isnull=False),
                name='uniq_wf_canvas_node_sequence',
            ),
        ]
        indexes = [
            models.Index(fields=['workflow_run', 'status'], name='wf_node_run_status_idx'),
            models.Index(fields=['canvas', 'status'], name='wf_node_canvas_run_status_idx'),
            models.Index(fields=['external_task_id'], name='wf_node_external_idx'),
            models.Index(fields=['idempotency_key'], name='wf_node_idempotency_idx'),
        ]

    def __str__(self):
        return f'{self.workflow_run_id}:{self.node_key}#{self.sequence}'


class WorkflowBinding(models.Model):
    """工作流运行与业务对象绑定。"""

    BINDING_TYPE_CHOICES = [
        ('project', '项目'),
        ('stage', '阶段'),
        ('storyboard', '分镜'),
        ('image', '图片'),
        ('camera', '运镜'),
        ('video', '视频'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_run = models.ForeignKey(
        WorkflowRun,
        on_delete=models.CASCADE,
        related_name='bindings',
        null=True,
        blank=True,
        verbose_name='工作流运行',
    )
    canvas = models.ForeignKey(
        WorkflowCanvas,
        on_delete=models.CASCADE,
        related_name='bindings',
        null=True,
        blank=True,
        verbose_name='画板',
    )
    node = models.ForeignKey(
        WorkflowNode,
        on_delete=models.SET_NULL,
        related_name='bindings',
        null=True,
        blank=True,
        verbose_name='节点',
    )
    node_run = models.ForeignKey(
        WorkflowNodeRun,
        on_delete=models.CASCADE,
        related_name='bindings',
        null=True,
        blank=True,
        verbose_name='节点运行',
    )
    binding_type = models.CharField('绑定类型', max_length=20, choices=BINDING_TYPE_CHOICES)
    target_id = models.CharField('目标ID', max_length=64)
    target_key = models.CharField('目标键', max_length=255, blank=True, default='')
    sequence_number = models.IntegerField('分镜序号', null=True, blank=True)
    metadata = models.JSONField('元数据', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_bindings'
        verbose_name = '工作流绑定'
        verbose_name_plural = '工作流绑定'
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['node_run', 'binding_type', 'target_key'],
                condition=models.Q(node_run__isnull=False),
                name='uniq_workflow_binding_node_type_target_key',
            ),
        ]
        indexes = [
            models.Index(fields=['workflow_run', 'binding_type'], name='wf_binding_run_type_idx'),
            models.Index(fields=['canvas', 'binding_type'], name='wf_binding_canvas_type_idx'),
            models.Index(fields=['target_id'], name='wf_binding_target_idx'),
        ]

    def __str__(self):
        return f'{self.binding_type}:{self.target_id}'


class WorkflowNodeRunEvent(models.Model):
    """节点运行事件日志。"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_run = models.ForeignKey(
        WorkflowRun,
        on_delete=models.CASCADE,
        related_name='node_run_events',
        null=True,
        blank=True,
        verbose_name='工作流运行',
    )
    canvas = models.ForeignKey(
        WorkflowCanvas,
        on_delete=models.CASCADE,
        related_name='node_run_events',
        null=True,
        blank=True,
        verbose_name='画板',
    )
    node = models.ForeignKey(
        WorkflowNode,
        on_delete=models.SET_NULL,
        related_name='run_events',
        null=True,
        blank=True,
        verbose_name='节点',
    )
    node_run = models.ForeignKey(
        WorkflowNodeRun,
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name='节点运行',
    )
    event_type = models.CharField('事件类型', max_length=100)
    payload = models.JSONField('事件载荷', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'workflow_node_run_events'
        verbose_name = '节点运行事件'
        verbose_name_plural = '节点运行事件'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['node_run', 'created_at'], name='wf_node_run_event_idx'),
            models.Index(fields=['workflow_run', 'created_at'], name='wf_run_event_created_idx'),
            models.Index(fields=['canvas', 'created_at'], name='wf_canvas_event_created_idx'),
        ]

    def __str__(self):
        return f'{self.node_run_id}:{self.event_type}'


class WorkflowCallbackEvent(models.Model):
    """工作流外部回调日志。"""

    PROCESS_STATUS_CHOICES = [
        ('received', '已接收'),
        ('processed', '已处理'),
        ('ignored', '已忽略'),
        ('failed', '失败'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_run = models.ForeignKey(
        WorkflowRun,
        on_delete=models.CASCADE,
        related_name='callback_events',
        null=True,
        blank=True,
        verbose_name='工作流运行',
    )
    canvas = models.ForeignKey(
        WorkflowCanvas,
        on_delete=models.CASCADE,
        related_name='callback_events',
        null=True,
        blank=True,
        verbose_name='画板',
    )
    node_run = models.ForeignKey(
        WorkflowNodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='callback_events',
        verbose_name='节点运行',
    )
    provider = models.CharField('提供方', max_length=100)
    event_type = models.CharField('事件类型', max_length=100)
    idempotency_key = models.CharField('幂等键', max_length=255, unique=True)
    external_task_id = models.CharField('外部任务ID', max_length=255, blank=True, default='')
    payload = models.JSONField('回调数据', default=dict, blank=True)
    process_status = models.CharField('处理状态', max_length=20, choices=PROCESS_STATUS_CHOICES, default='received')
    error_message = models.TextField('错误信息', blank=True, default='')
    received_at = models.DateTimeField('接收时间', auto_now_add=True)
    processed_at = models.DateTimeField('处理时间', null=True, blank=True)

    class Meta:
        db_table = 'workflow_callback_events'
        verbose_name = '工作流回调事件'
        verbose_name_plural = '工作流回调事件'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['workflow_run', 'provider'], name='wf_cb_run_provider_idx'),
            models.Index(fields=['canvas', 'provider'], name='wf_cb_canvas_provider_idx'),
            models.Index(fields=['external_task_id'], name='wf_cb_external_idx'),
        ]

    def __str__(self):
        return f'{self.provider}:{self.event_type}'

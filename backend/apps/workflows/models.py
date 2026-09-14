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

    # 运行实例必须固定其来源版本，和画布当前编辑版本解耦。

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
    workflow_version = models.PositiveIntegerField('运行工作流版本', default=1)
    canvas_revision = models.CharField('画布编辑版本', max_length=64, blank=True, default='')
    priority = models.SmallIntegerField('优先级', default=0)
    max_concurrency = models.PositiveIntegerField('最大并发数', default=4)
    estimated_cost = models.DecimalField('预估成本', max_digits=12, decimal_places=4, default=0)
    actual_cost = models.DecimalField('实际成本', max_digits=12, decimal_places=4, default=0)
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
        ('waiting_confirmation', '等待人工确认'),
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
    status = models.CharField('状态', max_length=24, choices=STATUS_CHOICES, default='pending')
    sequence = models.PositiveIntegerField('序号', default=1)
    trigger_source = models.CharField('触发来源', max_length=50, blank=True, default='manual')
    external_task_id = models.CharField('外部任务ID', max_length=255, blank=True, default='')
    idempotency_key = models.CharField('幂等键', max_length=255, blank=True, default='')
    input_payload = models.JSONField('输入', default=dict, blank=True)
    resolved_input_payload = models.JSONField('执行时有效输入快照', default=dict, blank=True)
    output_payload = models.JSONField('输出', default=dict, blank=True)
    normalized_output = models.JSONField('标准化输出', default=dict, blank=True)
    upstream_snapshot = models.JSONField('上游快照', default=dict, blank=True)
    input_fingerprint = models.CharField('输入指纹', max_length=128, blank=True, default='')
    cache_hit = models.BooleanField('命中缓存', default=False)
    timeout_seconds = models.PositiveIntegerField('超时秒数', default=3600)
    max_retries = models.PositiveIntegerField('最大重试次数', default=2)
    model_snapshot = models.JSONField('模型参数快照', default=dict, blank=True)
    cost_estimate = models.DecimalField('节点预估成本', max_digits=12, decimal_places=4, default=0)
    cost_actual = models.DecimalField('节点实际成本', max_digits=12, decimal_places=4, default=0)
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


class WorkflowResultCandidate(models.Model):
    """Generated result with review state, ancestry, and reproducibility metadata."""

    STATUS_CHOICES = [
        ('unreviewed', '未标记'),
        ('adopted', '采用'),
        ('alternate', '备选'),
        ('discarded', '废弃'),
    ]
    MEDIA_TYPE_CHOICES = [
        ('image', '图片'),
        ('video', '视频'),
        ('text', '文本'),
        ('json', '结构化数据'),
    ]
    ORIGIN_CHOICES = [
        ('generated', '生成'),
        ('restored', '历史恢复'),
        ('branched', '分支派生'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node_run = models.ForeignKey(
        WorkflowNodeRun,
        on_delete=models.CASCADE,
        related_name='candidates',
        verbose_name='节点运行',
    )
    node = models.ForeignKey(
        WorkflowNode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='result_candidates',
        verbose_name='节点',
    )
    parent_candidate = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_candidates',
        verbose_name='父候选',
    )
    result_index = models.PositiveIntegerField('候选序号', default=0)
    status = models.CharField('评审状态', max_length=20, choices=STATUS_CHOICES, default='unreviewed')
    media_type = models.CharField('媒体类型', max_length=12, choices=MEDIA_TYPE_CHOICES, default='json')
    origin = models.CharField('来源', max_length=12, choices=ORIGIN_CHOICES, default='generated')
    artifact_url = models.TextField('产物地址', blank=True, default='')
    content = models.JSONField('候选内容', default=dict)
    prompt = models.TextField('提示词快照', blank=True, default='')
    model_name = models.CharField('模型名称', max_length=255, blank=True, default='')
    model_version = models.CharField('模型版本', max_length=255, blank=True, default='')
    parameters = models.JSONField('生成参数快照', default=dict, blank=True)
    seed = models.BigIntegerField('随机种子', null=True, blank=True)
    workflow_version = models.PositiveIntegerField('工作流版本', default=1)
    canvas_revision = models.CharField('画布版本', max_length=64, blank=True, default='')
    lineage = models.JSONField('完整血缘快照', default=dict, blank=True)
    adopted_at = models.DateTimeField('采用时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'workflow_result_candidates'
        verbose_name = '工作流结果候选'
        verbose_name_plural = '工作流结果候选'
        ordering = ['-created_at', 'result_index']
        constraints = [
            models.UniqueConstraint(fields=['node_run', 'result_index'], name='uniq_wf_candidate_run_index'),
            models.UniqueConstraint(
                fields=['node'],
                condition=models.Q(node__isnull=False, status='adopted'),
                name='uniq_wf_adopted_candidate_per_node',
            ),
        ]
        indexes = [
            models.Index(fields=['node', 'status', '-created_at'], name='wf_candidate_node_status_idx'),
            models.Index(fields=['parent_candidate'], name='wf_candidate_parent_idx'),
        ]

    def __str__(self):
        return f'{self.node_run_id}#{self.result_index}'


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


class ProductionEntity(models.Model):
    """A reusable story-world entity used to keep shots visually consistent."""

    ENTITY_TYPES = [
        ('character', '角色'),
        ('location', '场景设定'),
        ('prop', '道具'),
        ('costume', '服饰'),
        ('look', '视觉设定'),
        ('audio', '音频素材'),
        ('reference', '参考素材'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE,
        related_name='production_entities', verbose_name='项目',
    )
    entity_type = models.CharField('实体类型', max_length=20, choices=ENTITY_TYPES)
    name = models.CharField('名称', max_length=255)
    description = models.TextField('描述', blank=True, default='')
    reference_data = models.JSONField('参考资料', default=dict, blank=True)
    continuity_data = models.JSONField('连续性基准', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'production_entities'
        ordering = ['entity_type', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'entity_type', 'name'],
                name='uniq_prod_entity_project_type_name',
            ),
        ]
        indexes = [models.Index(fields=['project', 'entity_type'], name='prod_entity_proj_type_idx')]

    def __str__(self):
        return self.name


class ProductionScene(models.Model):
    """A dramatic scene within an episode/project."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE,
        related_name='production_scenes', verbose_name='项目',
    )
    canvas = models.ForeignKey(
        WorkflowCanvas, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_scenes', verbose_name='画板',
    )
    number = models.PositiveIntegerField('场次', default=1)
    name = models.CharField('场景名称', max_length=255)
    synopsis = models.TextField('场景概要', blank=True, default='')
    location = models.ForeignKey(
        ProductionEntity, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='location_scenes', verbose_name='场景设定',
        limit_choices_to={'entity_type': 'location'},
    )
    time_of_day = models.CharField('时间', max_length=50, blank=True, default='')
    interior_exterior = models.CharField('内外景', max_length=20, blank=True, default='')
    continuity_data = models.JSONField('连续性基准', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'production_scenes'
        ordering = ['number', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['project', 'number'], name='uniq_prod_scene_project_number'),
        ]
        indexes = [models.Index(fields=['project', 'number'], name='prod_scene_proj_number_idx')]

    def __str__(self):
        return f'{self.number}. {self.name}'


class Shot(models.Model):
    """A shot is the stable semantic unit shared by lists and canvas nodes."""

    STATUS_CHOICES = [('draft', '草稿'), ('ready', '待生成'), ('approved', '已确认')]
    SHOT_SIZES = [
        ('extreme_wide', '大远景'), ('wide', '远景'), ('full', '全景'),
        ('medium', '中景'), ('close_up', '近景'), ('extreme_close_up', '特写'),
    ]
    PACING_CHOICES = [('slow', '舒缓'), ('normal', '正常'), ('fast', '快速')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scene = models.ForeignKey(ProductionScene, on_delete=models.CASCADE, related_name='shots', verbose_name='场景')
    canvas = models.ForeignKey(
        WorkflowCanvas, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='shots', verbose_name='画板',
    )
    number = models.PositiveIntegerField('镜号', default=1)
    title = models.CharField('镜头标题', max_length=255, blank=True, default='')
    description = models.TextField('画面描述', blank=True, default='')
    prompt = models.TextField('生成提示词', blank=True, default='')
    shot_size = models.CharField('景别', max_length=30, choices=SHOT_SIZES, default='medium')
    camera_angle = models.CharField('机位', max_length=100, blank=True, default='eye_level')
    focal_length_mm = models.PositiveSmallIntegerField('焦段(mm)', null=True, blank=True)
    camera_movement = models.CharField('运镜', max_length=100, blank=True, default='static')
    duration_seconds = models.DecimalField('时长(秒)', max_digits=7, decimal_places=3, default=5)
    frame_rate = models.DecimalField('帧率', max_digits=7, decimal_places=3, default=24)
    aspect_ratio = models.CharField('画幅', max_length=20, default='16:9')
    pacing = models.CharField('节奏', max_length=20, choices=PACING_CHOICES, default='normal')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='draft')
    canvas_node_key = models.CharField('画布节点键', max_length=100, blank=True, default='')
    continuity_data = models.JSONField('连续性状态', default=dict, blank=True)
    is_locked = models.BooleanField('已锁定', default=False)
    locked_snapshot = models.JSONField('锁定快照', default=dict, blank=True)
    locked_at = models.DateTimeField('锁定时间', null=True, blank=True)
    version = models.PositiveIntegerField('版本', default=1)
    entities = models.ManyToManyField(ProductionEntity, through='ShotEntityBinding', related_name='shots')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'production_shots'
        ordering = ['scene__number', 'number', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['scene', 'number'], name='uniq_prod_shot_scene_number'),
        ]
        indexes = [
            models.Index(fields=['canvas', 'canvas_node_key'], name='prod_shot_canvas_node_idx'),
            models.Index(fields=['scene', 'number'], name='prod_shot_scene_number_idx'),
        ]

    def __str__(self):
        return self.title or f'{self.scene.number}-{self.number}'


class ShotEntityBinding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shot = models.ForeignKey(Shot, on_delete=models.CASCADE, related_name='entity_bindings')
    entity = models.ForeignKey(ProductionEntity, on_delete=models.CASCADE, related_name='shot_bindings')
    state_data = models.JSONField('镜头内状态', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'shot_entity_bindings'
        constraints = [models.UniqueConstraint(fields=['shot', 'entity'], name='uniq_shot_entity_binding')]


class ShotReference(models.Model):
    REFERENCE_TYPES = [
        ('first_frame', '首帧'), ('last_frame', '尾帧'),
        ('keyframe', '关键帧'), ('reference_video', '参考视频'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shot = models.ForeignKey(Shot, on_delete=models.CASCADE, related_name='references')
    reference_type = models.CharField('参考类型', max_length=30, choices=REFERENCE_TYPES)
    url = models.URLField('资源地址', max_length=1000)
    frame_time = models.DecimalField('帧时间', max_digits=8, decimal_places=3, null=True, blank=True)
    metadata = models.JSONField('元数据', default=dict, blank=True)
    sort_order = models.PositiveIntegerField('排序', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'shot_references'
        ordering = ['sort_order', 'created_at']


class ShotTake(models.Model):
    STATUS_CHOICES = [('pending', '待生成'), ('rendering', '生成中'), ('completed', '已完成'), ('failed', '失败')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shot = models.ForeignKey(Shot, on_delete=models.CASCADE, related_name='takes')
    number = models.PositiveIntegerField('Take 序号', default=1)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    media_url = models.URLField('视频地址', max_length=1000, blank=True, default='')
    thumbnail_url = models.URLField('缩略图', max_length=1000, blank=True, default='')
    model_key = models.CharField('模型', max_length=255, blank=True, default='')
    generation_data = models.JSONField('生成参数', default=dict, blank=True)
    is_final = models.BooleanField('最终 Take', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'shot_takes'
        ordering = ['number', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['shot', 'number'], name='uniq_shot_take_number'),
            models.UniqueConstraint(
                fields=['shot'], condition=models.Q(is_final=True), name='uniq_shot_final_take',
            ),
        ]


class ContinuityIssue(models.Model):
    CATEGORIES = [
        ('character', '人物'), ('costume', '服饰'), ('prop', '道具'),
        ('lighting', '光线'), ('spatial', '空间位置'), ('action', '动作衔接'),
    ]
    SEVERITIES = [('info', '提示'), ('warning', '警告'), ('error', '错误')]
    STATUS_CHOICES = [('open', '待处理'), ('ignored', '已忽略'), ('resolved', '已解决')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='continuity_issues')
    from_shot = models.ForeignKey(Shot, on_delete=models.CASCADE, related_name='outgoing_continuity_issues')
    to_shot = models.ForeignKey(Shot, on_delete=models.CASCADE, related_name='incoming_continuity_issues')
    category = models.CharField('类别', max_length=20, choices=CATEGORIES)
    severity = models.CharField('严重程度', max_length=20, choices=SEVERITIES, default='warning')
    message = models.TextField('问题描述')
    expected_value = models.JSONField('预期状态', null=True, blank=True)
    actual_value = models.JSONField('实际状态', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        db_table = 'continuity_issues'
        ordering = ['from_shot__scene__number', 'from_shot__number', 'category']
        constraints = [
            models.UniqueConstraint(
                fields=['from_shot', 'to_shot', 'category'], name='uniq_continuity_shot_pair_cat',
            ),
        ]

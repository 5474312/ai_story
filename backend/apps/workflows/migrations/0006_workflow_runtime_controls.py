from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('workflows', '0005_refine_workflownodeschema_fields')]
    operations = [
        migrations.AddField(model_name='workflowrun', name='workflow_version', field=models.PositiveIntegerField(default=1, verbose_name='运行工作流版本')),
        migrations.AddField(model_name='workflowrun', name='canvas_revision', field=models.CharField(blank=True, default='', max_length=64, verbose_name='画布编辑版本')),
        migrations.AddField(model_name='workflowrun', name='priority', field=models.SmallIntegerField(default=0, verbose_name='优先级')),
        migrations.AddField(model_name='workflowrun', name='max_concurrency', field=models.PositiveIntegerField(default=4, verbose_name='最大并发数')),
        migrations.AddField(model_name='workflowrun', name='estimated_cost', field=models.DecimalField(decimal_places=4, default=0, max_digits=12, verbose_name='预估成本')),
        migrations.AddField(model_name='workflowrun', name='actual_cost', field=models.DecimalField(decimal_places=4, default=0, max_digits=12, verbose_name='实际成本')),
        migrations.AddField(model_name='workflownoderun', name='input_fingerprint', field=models.CharField(blank=True, default='', max_length=128, verbose_name='输入指纹')),
        migrations.AddField(model_name='workflownoderun', name='cache_hit', field=models.BooleanField(default=False, verbose_name='命中缓存')),
        migrations.AddField(model_name='workflownoderun', name='timeout_seconds', field=models.PositiveIntegerField(default=3600, verbose_name='超时秒数')),
        migrations.AddField(model_name='workflownoderun', name='max_retries', field=models.PositiveIntegerField(default=2, verbose_name='最大重试次数')),
        migrations.AddField(model_name='workflownoderun', name='model_snapshot', field=models.JSONField(blank=True, default=dict, verbose_name='模型参数快照')),
        migrations.AddField(model_name='workflownoderun', name='cost_estimate', field=models.DecimalField(decimal_places=4, default=0, max_digits=12, verbose_name='节点预估成本')),
        migrations.AddField(model_name='workflownoderun', name='cost_actual', field=models.DecimalField(decimal_places=4, default=0, max_digits=12, verbose_name='节点实际成本')),
        migrations.AlterField(model_name='workflownoderun', name='status', field=models.CharField(choices=[('pending','待运行'),('blocked','已阻断'),('queued','已排队'),('running','运行中'),('waiting_callback','等待回调'),('waiting_confirmation','等待人工确认'),('completed','已完成'),('failed','失败'),('cancelled','已取消')], default='pending', max_length=24, verbose_name='状态')),
    ]

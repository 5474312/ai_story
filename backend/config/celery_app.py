"""
Celery配置
用于异步任务处理和Redis Pub/Sub集成
"""

import os

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')

app = Celery('ai_story')

# 从Django settings加载配置
app.config_from_object('django.conf:settings')

# 自动发现任务
app.autodiscover_tasks()

# Celery配置优化
# 注意: broker_url 和 result_backend 必须在这里显式设置
# 否则会使用 Celery 的默认值 redis://localhost:6379/0

app.conf.update(
    # Broker和Backend配置 (必须显式设置)
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,

    # Broker连接配置
    broker_connection_retry_on_startup=True,  # Celery 6.0+ 启动时重试连接
    broker_transport_options={
        'visibility_timeout': settings.CELERY_BROKER_VISIBILITY_TIMEOUT,
    },

    # 任务结果过期时间 (1小时)
    result_expires=3600,

    # 任务序列化
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],

    # 时区
    timezone='Asia/Shanghai',
    enable_utc=True,

    # # 任务路由 (可选，用于任务分发到不同队列)
    # task_routes={
    #     'apps.projects.tasks.execute_llm_stage': {'queue': 'llm'},
    #     'apps.projects.tasks.execute_text2image_stage': {'queue': 'image'},
    #     'apps.projects.tasks.execute_image2video_stage': {'queue': 'video'},
    # },

    # 任务优先级
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,

    # Worker配置
    worker_prefetch_multiplier=1,  # 每次只预取1个任务
    worker_max_tasks_per_child=100,  # 每个worker处理100个任务后重启
)

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """调试任务"""
    print(f'Request: {self.request!r}')


# Celery信号处理 (可选，用于监控)
@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, **kwargs):
    """任务开始前"""
    print(f'任务开始: {task.name} [{task_id}]')


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, **kwargs):
    """任务完成后"""
    print(f'任务完成: {task.name} [{task_id}]')


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
    """任务失败"""
    print(f'任务失败: {sender.name} [{task_id}] - {exception}')

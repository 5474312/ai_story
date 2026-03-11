"""
SSE流式视图
职责: 提供基于Redis Pub/Sub的Server-Sent Events接口
遵循单一职责原则(SRP)
"""

import json
import logging
import time
from typing import Generator
from django.http import StreamingHttpResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from core.redis.subscriber import RedisStreamSubscriber

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 15
MESSAGE_POLL_TIMEOUT_SECONDS = 1.0
SINGLE_STAGE_IDLE_TIMEOUT_SECONDS = 600
ALL_STAGES_IDLE_TIMEOUT_SECONDS = 1800


@method_decorator(csrf_exempt, name='dispatch')
class ProjectStageSSEView(View):
    """
    项目阶段SSE流式视图

    通过Redis Pub/Sub订阅项目阶段的实时数据流
    使用Server-Sent Events (SSE)协议推送给前端

    """

    def get(self, request, project_id: str, stage_name: str):
        """
        GET请求处理

        Args:
            project_id: 项目ID
            stage_name: 阶段名称 (rewrite/storyboard/image_generation等)

        Returns:
            StreamingHttpResponse: SSE流式响应
        """
        logger.info(f"SSE连接建立: project_id={project_id}, stage_name={stage_name}")

        event_stream = self._create_event_stream(project_id, stage_name)

        response = StreamingHttpResponse(
            event_stream,
            content_type='text/event-stream; charset=utf-8'
        )

        response['Cache-Control'] = 'no-cache, no-transform'
        response['X-Accel-Buffering'] = 'no'
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET'
        response['Access-Control-Allow-Headers'] = 'Content-Type'

        return response

    def _create_event_stream(self, project_id: str, stage_name: str) -> Generator[bytes, None, None]:
        """
        创建SSE事件流生成器

        Args:
            project_id: 项目ID
            stage_name: 阶段名称

        Yields:
            bytes: SSE格式的事件数据
        """
        subscriber = None

        try:
            subscriber = RedisStreamSubscriber(project_id, stage_name)

            yield self._format_sse_message({
                'type': 'connected',
                'project_id': project_id,
                'stage': stage_name,
                'message': 'SSE连接已建立'
            })

            yield from self._stream_messages(
                subscriber=subscriber,
                project_id=project_id,
                stage_name=stage_name,
                idle_timeout=SINGLE_STAGE_IDLE_TIMEOUT_SECONDS,
                all_stages_mode=False,
            )
        except GeneratorExit:
            logger.info(f"SSE客户端断开: project_id={project_id}, stage_name={stage_name}")
            raise
        except (BrokenPipeError, ConnectionResetError) as exc:
            logger.info(f"SSE连接被客户端关闭: project_id={project_id}, stage_name={stage_name}, error={exc}")
        except Exception as exc:
            logger.error(f"SSE流异常: {str(exc)}")
            yield self._format_sse_message({
                'type': 'error',
                'error': f'SSE流异常: {str(exc)}',
                'project_id': project_id
            })
        finally:
            if subscriber:
                subscriber.close()

            logger.info(f"SSE连接关闭: project_id={project_id}, stage_name={stage_name}")

    def _stream_messages(
        self,
        subscriber: RedisStreamSubscriber,
        project_id: str,
        stage_name: str = None,
        idle_timeout: int = SINGLE_STAGE_IDLE_TIMEOUT_SECONDS,
        all_stages_mode: bool = False,
    ) -> Generator[bytes, None, None]:
        """轮询Redis消息并定期发送心跳，确保客户端断开后能尽快释放订阅。"""
        start_time = time.monotonic()
        last_activity_at = start_time
        last_heartbeat_at = start_time

        while True:
            message = subscriber.get_message(timeout=MESSAGE_POLL_TIMEOUT_SECONDS)
            now = time.monotonic()

            if message:
                last_activity_at = now
                yield self._format_sse_message(message)

                if all_stages_mode:
                    if message.get('type') in ('pipeline_done', 'pipeline_error'):
                        logger.info(f"SSE流结束(所有阶段): {message.get('type')}")
                        break
                else:
                    if message.get('type') in ('done', 'error'):
                        logger.info(f"SSE流结束: {message.get('type')}")
                        break
                continue

            if now - last_heartbeat_at >= HEARTBEAT_INTERVAL_SECONDS:
                last_heartbeat_at = now
                yield b': heartbeat\n\n'

            if now - last_activity_at >= idle_timeout:
                logger.info(
                    "SSE空闲超时关闭: project_id=%s, stage_name=%s, all_stages=%s",
                    project_id,
                    stage_name,
                    all_stages_mode,
                )
                break

    def _format_sse_message(self, data: dict) -> bytes:
        """
        格式化SSE消息

        SSE格式:
        data: {"type": "token", "content": "..."}

        Args:
            data: 消息数据字典

        Returns:
            bytes: SSE格式的消息
        """
        try:
            json_data = json.dumps(data, ensure_ascii=False)
            sse_message = f"data: {json_data}\n\n"
            return sse_message.encode('utf-8')
        except Exception as exc:
            logger.error(f"SSE消息格式化失败: {str(exc)}")
            error_data = json.dumps({
                'type': 'error',
                'error': f'消息格式化失败: {str(exc)}'
            }, ensure_ascii=False)
            return f"data: {error_data}\n\n".encode('utf-8')


@method_decorator(csrf_exempt, name='dispatch')
class ProjectAllStagesSSEView(ProjectStageSSEView):
    """
    项目所有阶段SSE流式视图

    订阅项目的所有阶段消息 (使用Redis模式匹配)

    URL: /api/v1/sse/projects/{project_id}/
    """

    def get(self, request, project_id: str):
        """
        GET请求处理

        Args:
            project_id: 项目ID

        Returns:
            StreamingHttpResponse: SSE流式响应
        """
        logger.info(f"SSE连接建立(所有阶段): project_id={project_id}")

        event_stream = self._create_event_stream(project_id)

        response = StreamingHttpResponse(
            event_stream,
            content_type='text/event-stream; charset=utf-8'
        )

        response['Cache-Control'] = 'no-cache, no-transform'
        response['X-Accel-Buffering'] = 'no'
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'GET'
        response['Access-Control-Allow-Headers'] = 'Content-Type'

        return response

    def _create_event_stream(self, project_id: str) -> Generator[bytes, None, None]:
        """
        创建SSE事件流生成器

        Args:
            project_id: 项目ID

        Yields:
            bytes: SSE格式的事件数据
        """
        subscriber = None

        try:
            subscriber = RedisStreamSubscriber(project_id, stage_name=None)

            yield self._format_sse_message({
                'type': 'connected',
                'project_id': project_id,
                'message': 'SSE连接已建立(所有阶段)'
            })

            yield from self._stream_messages(
                subscriber=subscriber,
                project_id=project_id,
                idle_timeout=ALL_STAGES_IDLE_TIMEOUT_SECONDS,
                all_stages_mode=True,
            )
        except GeneratorExit:
            logger.info(f"SSE客户端断开(所有阶段): project_id={project_id}")
            raise
        except (BrokenPipeError, ConnectionResetError) as exc:
            logger.info(f"SSE连接被客户端关闭(所有阶段): project_id={project_id}, error={exc}")
        except Exception as exc:
            logger.error(f"SSE流异常: {str(exc)}")
            yield self._format_sse_message({
                'type': 'error',
                'error': f'SSE流异常: {str(exc)}',
                'project_id': project_id
            })
        finally:
            if subscriber:
                subscriber.close()

            logger.info(f"SSE连接关闭(所有阶段): project_id={project_id}")

"""
文生图客户端实现
支持 OpenAI 兼容的 chat/completions 图像生成接口
"""

import re
import time
from typing import List

import requests

from .base import Text2ImageClient as BaseText2ImageClient, AIResponse


class Text2ImageClient(BaseText2ImageClient):
    """
    文生图客户端实现
    支持通过 chat/completions 接口返回 Markdown 图片链接的图像服务
    """

    IMAGE_MARKDOWN_PATTERN = re.compile(r'!\[[^\]]*\]\((https?://[^)]+)\)')
    URL_PATTERN = re.compile(r'https?://\S+')

    def _build_api_url(self, api_url: str) -> str:
        """兼容传入完整 chat/completions 地址或基础地址。"""
        if api_url.endswith('/chat/completions'):
            return api_url
        return f"{api_url.rstrip('/')}/chat/completions"

    def _extract_image_urls(self, content: str) -> List[str]:
        """从返回内容中提取 Markdown 图片链接。"""
        if not content:
            return []

        urls = self.IMAGE_MARKDOWN_PATTERN.findall(content)
        if urls:
            return urls

        fallback_urls = []
        for candidate in self.URL_PATTERN.findall(content):
            cleaned = candidate.rstrip(').,]\n\r\t ')
            if cleaned:
                fallback_urls.append(cleaned)
        return fallback_urls

    def _generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        **kwargs
    ) -> AIResponse:
        """
        生成图片

        按 OpenAI 兼容的 chat/completions 方式调用图像模型，
        并将返回的 Markdown 图片链接转换为统一图片列表结构。
        """
        start_time = time.time()

        api_url = kwargs.get('api_url', self.api_url)
        api_key = kwargs.get('api_key') or kwargs.get('session_id') or self.api_key
        model_name = kwargs.get('model') or self.model_name
        ratio = kwargs.get('ratio', '1:1')
        resolution = kwargs.get('resolution', '2k')
        timeout = kwargs.get('timeout', self.config.get('timeout', 60))

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }

        content = prompt.strip()
        if negative_prompt:
            content = f"{content}\n\n负面提示词：{negative_prompt.strip()}"

        payload = {
            'model': model_name,
            'messages': [
                {
                    'role': 'system',
                    'content': content,
                }
            ],
        }

        if steps:
            payload['steps'] = steps
        if kwargs.get('response_format'):
            payload['response_format'] = kwargs['response_format']

        request_url = self._build_api_url(api_url)

        try:
            response = requests.post(
                request_url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

            if response.status_code != 200:
                return AIResponse(
                    success=False,
                    error=f'API请求失败: {response.status_code} - {response.text}'
                )

            result = response.json()
            latency_ms = int((time.time() - start_time) * 1000)

            if 'choices' not in result or not result['choices']:
                return AIResponse(
                    success=False,
                    error='响应格式错误: 缺少choices字段或choices为空'
                )

            message = result['choices'][0].get('message', {})
            message_content = message.get('content', '')
            image_urls = self._extract_image_urls(message_content)

            if not image_urls:
                legacy_data = result.get('data') or []
                if isinstance(legacy_data, list):
                    image_urls = [item.get('url', '') for item in legacy_data if item.get('url')]

            if not image_urls:
                return AIResponse(
                    success=False,
                    error='响应格式错误: 未从返回内容中解析到图片URL',
                    metadata={
                        'raw_content': message_content,
                        'latency_ms': latency_ms,
                        'model': result.get('model', model_name),
                    }
                )

            images_data = [
                {
                    'url': image_url,
                    'width': width,
                    'height': height,
                }
                for image_url in image_urls
            ]

            return AIResponse(
                success=True,
                text=message_content,
                data=images_data,
                metadata={
                    'latency_ms': latency_ms,
                    'model': result.get('model', model_name),
                    'ratio': ratio,
                    'resolution': resolution,
                    'width': width,
                    'height': height,
                    'steps': steps,
                    'request_url': request_url,
                    'response_id': result.get('id', ''),
                    'finish_reason': result['choices'][0].get('finish_reason'),
                    'usage': result.get('usage', {}),
                }
            )

        except requests.exceptions.RequestException as exc:
            return AIResponse(
                success=False,
                error=f'网络请求错误: {str(exc)}'
            )
        except ValueError as exc:
            return AIResponse(
                success=False,
                error=f'响应解析错误: {str(exc)}'
            )
        except Exception as exc:
            return AIResponse(
                success=False,
                error=f'未知错误: {str(exc)}'
            )

    def validate_config(self) -> bool:
        """验证配置"""
        if not self.api_url or not self.api_key or not self.model_name:
            return False

        return True

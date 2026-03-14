"""
文生图客户端实现
支持 OpenAI 兼容的 chat/completions 图像生成接口
"""

import re
import time
from typing import List
from urllib.parse import urlparse

import requests

from .base import Text2ImageClient as BaseText2ImageClient, AIResponse


class Text2ImageClient(BaseText2ImageClient):
    """
    文生图客户端实现
    支持通过 chat/completions 接口返回 Markdown 图片链接的图像服务
    """

    IMAGE_MARKDOWN_PATTERN = re.compile(r'!\[[^\]]*\]\((https?://[^)]+)\)')
    URL_PATTERN = re.compile(r'https?://\S+')

    def _is_images_generations_endpoint(self, api_url: str) -> bool:
        """判断是否为 images/generations 接口。"""
        path = urlparse(api_url).path.rstrip('/')
        return path.endswith('/images/generations')

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

        根据接口类型调用图像模型，并将返回结果转换为统一图片列表结构。
        """
        start_time = time.time()

        api_url = kwargs.get('api_url', self.api_url)
        api_key = kwargs.get('api_key') or kwargs.get('session_id') or self.api_key
        model_name = kwargs.get('model') or self.model_name
        ratio = kwargs.get('ratio', '1:1')
        resolution = kwargs.get('resolution', '2k')
        timeout = kwargs.get('timeout', self.config.get('timeout', 60))
        size = f'{width}x{height}'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }

        content = prompt.strip()
        if negative_prompt:
            content = f"{content}\n\n负面提示词：{negative_prompt.strip()}"

        request_url = api_url
        is_images_generations = self._is_images_generations_endpoint(request_url)

        if is_images_generations:
            payload = {
                'model': model_name,
                'prompt': content,
                'size': size
            }
        else:
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

            if is_images_generations:
                result_data = result.get('data') or []
                if not isinstance(result_data, list) or not result_data:
                    return AIResponse(
                        success=False,
                        error='响应格式错误: 缺少data字段或data为空'
                    )

                images_data = []
                image_urls = []
                for item in result_data:
                    image_url = item.get('url', '')
                    b64_json = item.get('b64_json', '')

                    if not image_url and not b64_json:
                        continue

                    if image_url:
                        image_urls.append(image_url)

                    image_item = {
                        'width': width,
                        'height': height,
                    }
                    if image_url:
                        image_item['url'] = image_url
                    if b64_json:
                        image_item['b64_json'] = b64_json

                    images_data.append(image_item)

                if not images_data:
                    return AIResponse(
                        success=False,
                        error='响应格式错误: 未从data中解析到有效图片结果',
                        metadata={
                            'latency_ms': latency_ms,
                            'model': model_name,
                            'request_url': request_url,
                            'usage': result.get('usage', {}),
                        }
                    )

                return AIResponse(
                    success=True,
                    text='\n'.join(image_urls),
                    data=images_data,
                    metadata={
                        'latency_ms': latency_ms,
                        'model': model_name,
                        'ratio': ratio,
                        'resolution': resolution,
                        'width': width,
                        'height': height,
                        'steps': steps,
                        'request_url': request_url,
                        'created': result.get('created'),
                        'usage': result.get('usage', {}),
                    }
                )

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

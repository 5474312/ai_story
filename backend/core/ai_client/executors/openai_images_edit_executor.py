"""显式的 OpenAI Images Edits 协议执行器。"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests

from core.ai_client.base import AIResponse, ImageEditClient as BaseImageEditClient
from core.ai_client.image_result_utils import (
    localize_image_item,
    merge_extra_payload,
    normalize_result_data,
)
from core.ai_client.schemas import ImageEditRequest


class OpenAIImagesEditExecutor(BaseImageEditClient):
    """适配 `/images/edits` 风格的图片编辑接口。"""

    def generate_from_image_edit_request(self, request: ImageEditRequest) -> AIResponse:
        return self._run_request(request=request)

    def _edit_image(
        self,
        image_url: str,
        prompt: str = "",
        mask_url: str = "",
        strength: float = 0.35,
        width: int = 1024,
        height: int = 1024,
        **kwargs
    ) -> AIResponse:
        source_images = kwargs.get('source_images') or [image_url]
        request = ImageEditRequest(
            source_images=source_images,
            prompt=prompt,
            mask_image=mask_url,
            negative_prompt=kwargs.get('negative_prompt', ''),
            strength=strength,
            width=width,
            height=height,
            edit_mode=kwargs.get('edit_mode', 'img2img'),
            extra={
                'steps': kwargs.get('steps'),
                'response_format': kwargs.get('response_format'),
            },
        )
        return self._run_request(request=request)

    def _run_request(
        self,
        request: ImageEditRequest,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> AIResponse:
        start_time = time.time()
        request_url = api_url or self.api_url
        request_key = api_key or self.api_key
        request_model = model_name or self.model_name
        timeout = int(request.extra.get('timeout') or self.config.get('timeout', 300))

        payload: Dict[str, Any] = {
            'model': request_model,
            'prompt': request.prompt,
            'strength': request.strength,
            'size': request.size or '1024x1024',
            'width': request.width or 1024,
            'height': request.height or 1024,
            'edit_mode': request.edit_mode,
        }
        if request.source_images:
            payload['image'] = request.source_images if len(request.source_images) > 1 else request.primary_source_image
            payload['image_url'] = request.primary_source_image
        if request.mask_image:
            payload['mask'] = request.mask_image
            payload['mask_url'] = request.mask_image
        if request.negative_prompt:
            payload['negative_prompt'] = request.negative_prompt
        if request.extra.get('steps'):
            payload['steps'] = request.extra['steps']
        if request.extra.get('response_format'):
            payload['response_format'] = request.extra['response_format']

        merge_extra_payload(
            payload,
            request.extra,
            reserved_keys={'timeout', 'steps', 'response_format'},
        )

        headers = {
            'Authorization': f'Bearer {request_key}',
            'Content-Type': 'application/json',
        }

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
                    error=f'API请求失败: {response.status_code} - {response.text}',
                )

            result = response.json()
            latency_ms = int((time.time() - start_time) * 1000)
            result_data = normalize_result_data(result.get('data'))
            if not result_data:
                return AIResponse(
                    success=False,
                    error='响应格式错误: 未从返回结果中解析到图片数据',
                    metadata={
                        'latency_ms': latency_ms,
                        'model': request_model,
                        'request_url': request_url,
                    },
                )

            localized_data = []
            for item in result_data:
                if not item.get('url') and not item.get('b64_json'):
                    continue
                localized_item = localize_image_item(
                    item=item,
                    width=request.width or 1024,
                    height=request.height or 1024,
                    timeout=timeout,
                )
                localized_item['source_image_url'] = request.primary_source_image
                localized_data.append(localized_item)

            if not localized_data:
                return AIResponse(
                    success=False,
                    error='响应格式错误: 未从data中解析到有效图片结果',
                )

            return AIResponse(
                success=True,
                text='\n'.join(item.get('url', '') for item in localized_data if item.get('url')),
                data=localized_data,
                metadata={
                    'latency_ms': latency_ms,
                    'model': request_model,
                    'request_url': request_url,
                    'source_image_url': request.primary_source_image,
                    'strength': request.strength,
                    'usage': result.get('usage', {}),
                },
            )
        except requests.exceptions.RequestException as exc:
            return AIResponse(success=False, error=f'网络请求错误: {str(exc)}')
        except ValueError as exc:
            return AIResponse(success=False, error=f'响应解析错误: {str(exc)}')
        except Exception as exc:
            return AIResponse(success=False, error=f'未知错误: {str(exc)}')

    def validate_config(self) -> bool:
        return bool(self.api_url and self.api_key and self.model_name)

"""图片能力统一调用入口。"""

from __future__ import annotations

from typing import Optional

from .base import AIResponse
from .factory import create_ai_client
from .schemas import ImageEditRequest, Text2ImageRequest


class ImageGenerationService:
    """统一封装文生图和图片编辑请求。"""

    @staticmethod
    def generate(provider, request: Text2ImageRequest, client=None) -> AIResponse:
        current_client = client or create_ai_client(provider)
        request_method = getattr(type(current_client), 'generate_from_text2image_request', None)
        if callable(request_method):
            return request_method(current_client, request)

        return current_client.generate(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width or 1024,
            height=request.height or 1024,
            ratio=request.aspect_ratio,
            image=request.reference_images,
            sample_count=request.sample_count,
            seed=request.seed,
            **(request.extra or {}),
        )

    @staticmethod
    def edit(provider, request: ImageEditRequest, client=None) -> AIResponse:
        current_client = client or create_ai_client(provider)
        request_method = getattr(type(current_client), 'generate_from_image_edit_request', None)
        if callable(request_method):
            return request_method(current_client, request)

        return current_client.generate(
            image_url=request.primary_source_image,
            prompt=request.prompt,
            mask_url=request.mask_image,
            strength=request.strength,
            width=request.width or 1024,
            height=request.height or 1024,
            negative_prompt=request.negative_prompt,
            edit_mode=request.edit_mode,
            source_images=request.source_images,
            **(request.extra or {}),
        )

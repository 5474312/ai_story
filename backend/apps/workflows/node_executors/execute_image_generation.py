"""图片生成节点执行逻辑。"""

from typing import Any, Dict

from apps.models.token_utils import create_ai_client_for_user
from core.ai_client.image_service import ImageGenerationService
from core.ai_client.schemas import ImageEditRequest, Text2ImageRequest
from core.services.multi_grid_image_service import MultiGridImageService

from apps.ai_proxy.views import (
    _ensure_list,
    _parse_float,
    _parse_int,
    _parse_size,
    _pick_provider,
)

from .image_input_helpers import prepare_image_inputs_for_api
from .response_helpers import extract_image_url, normalize_image_response


def _build_image_context(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """从输入参数构建图片生成上下文。"""
    size = _parse_size(input_payload.get('size'))
    width = _parse_int(input_payload.get('width'), size['width'])
    height = _parse_int(input_payload.get('height'), size['height'])
    reference_images = _ensure_list(
        input_payload.get('image') or input_payload.get('images') or input_payload.get('source_images')
    )
    source_image_url = input_payload.get('source_image_url')
    if source_image_url and source_image_url not in reference_images:
        reference_images.insert(0, source_image_url)
    prepared_images = prepare_image_inputs_for_api(reference_images, prefer_online_url=True)

    return {
        'model': input_payload.get('model', ''),
        'prompt': input_payload.get('prompt', ''),
        'negative_prompt': input_payload.get('negative_prompt', ''),
        'mask': input_payload.get('mask') or input_payload.get('mask_image') or '',
        'width': width,
        'height': height,
        'reference_images': prepared_images['api_image_inputs'],
        'original_reference_images': prepared_images['original_urls'],
        'aspect_ratio': input_payload.get('aspect_ratio') or input_payload.get('ratio') or '',
        'sample_count': _parse_int(input_payload.get('n'), _parse_int(input_payload.get('sample_count'), 1)) or 1,
        'seed': _parse_int(input_payload.get('seed')),
        'strength': _parse_float(input_payload.get('strength'), 0.35) or 0.35,
        'mode': input_payload.get('mode') or input_payload.get('edit_mode') or '',
        'provider_type': input_payload.get('provider_type') or '',
        'force_edit': input_payload.get('force_edit') is True,
        'extra': {
            key: value for key, value in input_payload.items()
            if key not in {
                'model', 'prompt', 'negative_prompt', 'mask', 'mask_image', 'width', 'height',
                'image', 'images', 'source_images', 'source_image_url', 'aspect_ratio', 'ratio',
                'n', 'sample_count', 'seed', 'strength', 'mode', 'edit_mode', 'size',
                'provider_type', 'force_edit',
            }
        },
    }


def _resolve_image_provider_type(context: Dict[str, Any]) -> str:
    """根据上下文判断应使用 text2image 还是 image_edit 提供商。"""
    mode = str(context.get('mode') or '').lower()
    reference_images = context.get('reference_images') or []
    if mode in {'inpaint', 'img2img', 'image_edit', 'edit'}:
        return 'image_edit'
    if context.get('mask'):
        return 'image_edit'
    if context.get('provider_type') == 'image_edit':
        return 'image_edit'
    if reference_images and context.get('force_edit'):
        return 'image_edit'
    return 'text2image'


def execute_image_generation(input_payload: Dict[str, Any], user_id=None) -> Dict[str, Any]:
    """执行图片生成节点，支持宫格切割、文生图、图生图。"""
    operation = str(input_payload.get('operation') or '').strip().lower()
    if operation == 'grid_split':
        source_image_url = str(
            input_payload.get('source_image_url')
            or input_payload.get('image_url')
            or input_payload.get('image')
            or ''
        ).strip()
        grid_rows = _parse_int(input_payload.get('grid_rows'), 0) or 0
        grid_cols = _parse_int(input_payload.get('grid_cols'), 0) or 0

        if not source_image_url:
            raise RuntimeError('缺少可切割的图片地址')
        if grid_rows <= 0 or grid_cols <= 0:
            raise RuntimeError('缺少有效的宫格配置')

        split_result = MultiGridImageService.split_image(
            image_url=source_image_url,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            tile_gap=0,
            outer_padding=0,
        )

        normalized_output = {
            'operation': 'grid_split',
            'imageUrl': source_image_url,
            'image_url': source_image_url,
            'grid_rows': split_result['grid_rows'],
            'grid_cols': split_result['grid_cols'],
            'tiles': split_result['tiles'],
        }
        return {
            'output_payload': split_result,
            'normalized_output': normalized_output,
        }

    context = _build_image_context(input_payload)
    if not context['prompt']:
        raise RuntimeError('prompt 不能为空')

    provider_type = _resolve_image_provider_type(context)
    provider = _pick_provider(provider_type, context['model'])
    if not provider:
        raise RuntimeError(f'没有可用的 {provider_type} 模型提供商')

    client = create_ai_client_for_user(provider, user_id=user_id)
    if provider_type == 'image_edit':
        ai_response = ImageGenerationService.edit(
            provider,
            ImageEditRequest(
                source_images=context['reference_images'],
                prompt=context['prompt'],
                mask_image=context['mask'],
                negative_prompt=context['negative_prompt'],
                strength=context['strength'],
                width=context['width'],
                height=context['height'],
                edit_mode=context['mode'] or 'img2img',
                extra=context['extra'],
            ),
            client=client,
        )
    else:
        ai_response = ImageGenerationService.generate(
            provider,
            Text2ImageRequest(
                prompt=context['prompt'],
                negative_prompt=context['negative_prompt'],
                reference_images=context['reference_images'],
                width=context['width'],
                height=context['height'],
                aspect_ratio=context['aspect_ratio'],
                sample_count=context['sample_count'],
                seed=context['seed'],
                extra=context['extra'],
            ),
            client=client,
        )

    output_payload = normalize_image_response(ai_response, provider, provider_type)
    image_url = extract_image_url(output_payload)
    if not image_url:
        raise RuntimeError('模型未返回可用图片地址')

    normalized_output = {
        'imageUrl': image_url,
        'image_url': image_url,
        'prompt': context['prompt'],
        'model': context['model'] or provider.model_name,
        'scale': input_payload.get('scale') or '1x',
        'resolution': context['extra'].get('resolution') or input_payload.get('resolution') or '2k',
        'source_image_url': (context['original_reference_images'] or [''])[0] if context['original_reference_images'] else '',
        'text': input_payload.get('text') or '',
    }
    return {
        'output_payload': output_payload,
        'normalized_output': normalized_output,
    }

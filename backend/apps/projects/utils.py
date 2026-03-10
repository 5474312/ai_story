import json
import re

from apps.prompts.models import PromptTemplate, PromptTemplateSet


PROJECT_STAGE_TYPES = [
    'rewrite',
    'storyboard',
    'image_generation',
    'camera_movement',
    'video_generation',
]


def get_effective_prompt_template_set(project):
    """获取项目实际生效的提示词集。"""
    template_set = getattr(project, 'prompt_template_set', None)
    if template_set:
        return template_set

    return PromptTemplateSet.objects.filter(is_default=True).first()


def get_stage_template_states(project):
    """返回项目各阶段对应提示词模板是否启用。"""
    template_set = get_effective_prompt_template_set(project)

    if not template_set:
        return {stage_type: False for stage_type in PROJECT_STAGE_TYPES}

    enabled_stage_types = set(
        PromptTemplate.objects.filter(
            template_set=template_set,
            is_active=True,
            stage_type__in=PROJECT_STAGE_TYPES,
        ).values_list('stage_type', flat=True)
    )

    return {
        stage_type: stage_type in enabled_stage_types
        for stage_type in PROJECT_STAGE_TYPES
    }


def is_stage_template_enabled(project, stage_type: str) -> bool:
    """判断指定阶段的提示词模板是否启用。"""
    return get_stage_template_states(project).get(stage_type, False)


def _extract_json_from_text(text: str) -> str:
        """从文本中提取JSON内容,处理可能包含markdown代码块的情况"""
        # 尝试移除 markdown 代码块标记
        text = text.strip()

        # 如果有 ```json 或 ``` 标记,提取其中的内容
        if '```' in text:
            # 匹配 ```json ... ``` 或 ``` ... ```
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        return text.replace("\n", "")

def parse_storyboard_json(json_text: str) -> dict:
    """解析分镜JSON数据"""
    try:
        # 提取纯JSON内容
        clean_json = _extract_json_from_text(json_text)

        # 解析JSON
        storyboard_data = json.loads(clean_json)

        # 验证数据结构
        if 'scenes' not in storyboard_data:
            raise ValueError("JSON数据中缺少 'scenes' 字段")

        if not isinstance(storyboard_data['scenes'], list):
            raise ValueError("'scenes' 必须是数组类型")

        # 验证每个场景的必需字段
        for i, scene in enumerate(storyboard_data['scenes']):
            required_fields = ['scene_number', 'narration', 'visual_prompt', 'shot_type']
            for field in required_fields:
                if field not in scene:
                    raise ValueError(f"场景 {i+1} 缺少必需字段: {field}")

        return storyboard_data

    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {str(e)}\n原始内容:\n{json_text[:200]}...")
    except Exception as e:
        raise ValueError(f"分镜数据解析失败: {str(e)}")


def parse_json(json_text: str) -> dict:
    """解析JSON数据"""
    try:
        # 提取纯JSON内容
        clean_json = _extract_json_from_text(json_text)

        # 解析JSON
        data = json.loads(clean_json)

        return data

    except json.JSONDecodeError:
        return json_text
    except Exception:
        return json_text

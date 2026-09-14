"""统一的图片能力请求与响应 schema。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


_RESOLUTION_LONG_SIDE_MAP = {
    "1k": 960,
    "2k": 1920,
    "4k": 3840,
}


@dataclass
class GeneratedImageItem:
    """统一的图片结果项。"""

    url: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    b64_json: str = ""
    original_url: str = ""
    storage_path: str = ""
    source_image_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Text2ImageRequest:
    """统一的文生图请求。"""

    prompt: str
    negative_prompt: str = ""
    reference_images: List[str] = field(default_factory=list)
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: str = ""
    sample_count: int = 1
    seed: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> str:
        if self.aspect_ratio:
            try:
                w_ratio, h_ratio = map(int, self.aspect_ratio.split(':'))
                resolution = str((self.extra or {}).get("resolution") or "").strip().lower()
                long_side = _RESOLUTION_LONG_SIDE_MAP.get(resolution)

                if long_side:
                    if self.aspect_ratio == "9:16":
                        w = max(64, int(long_side * w_ratio / h_ratio))
                        h = long_side
                    elif w_ratio >= h_ratio:
                        w = long_side
                        h = max(64, int(long_side * h_ratio / w_ratio))
                    else:
                        h = long_side
                        w = max(64, int(long_side * w_ratio / h_ratio))
                    return f"{w}x{h}"

                max_dim = 1024
                if w_ratio >= h_ratio:
                    w = max_dim
                    h = max(64, int(max_dim * h_ratio / w_ratio) // 8 * 8)
                else:
                    h = max_dim
                    w = max(64, int(max_dim * w_ratio / h_ratio) // 8 * 8)
                return f"{w}x{h}"
            except (ValueError, ZeroDivisionError):
                pass
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return ""


@dataclass
class ImageEditRequest:
    """统一的图片编辑请求。"""

    source_images: List[str]
    prompt: str
    mask_image: str = ""
    negative_prompt: str = ""
    strength: float = 0.35
    width: Optional[int] = None
    height: Optional[int] = None
    edit_mode: str = "img2img"
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def primary_source_image(self) -> str:
        return self.source_images[0] if self.source_images else ""

    @property
    def size(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return ""

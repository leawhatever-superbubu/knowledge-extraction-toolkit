"""图片预处理模块 — 压缩、EXIF 修正、base64 编码。

为 Vision AI 调用准备好图片数据：
1. EXIF 方向修正（部分手机照片旋转问题）
2. 大图缩放到 Vision AI 友好尺寸
3. 统一转为 JPEG/PNG 格式
4. 编码为 base64 字符串
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_MAX_DIMENSION = 2048  # Vision AI 推荐的最大边长
DEFAULT_MAX_SIZE_BYTES = 4 * 1024 * 1024  # 4MB
JPEG_QUALITY = 85


@dataclass
class ProcessedImage:
    """预处理后的图片数据。"""

    base64_data: str  # base64 编码的图片数据
    mime_type: str  # MIME 类型（image/jpeg, image/png, image/webp）
    original_path: str  # 原始文件路径
    original_size: int  # 原始文件大小（bytes）
    processed_size: int  # 处理后大小（bytes）
    width: int = 0  # 处理后宽度
    height: int = 0  # 处理后高度

    @property
    def data_url(self) -> str:
        """返回 data URL 格式（用于 Vision API）。"""
        return f"data:{self.mime_type};base64,{self.base64_data}"

    @property
    def compression_ratio(self) -> float:
        """压缩比率。"""
        if self.original_size == 0:
            return 0
        return self.processed_size / self.original_size


def preprocess_image(
    image_path: str | Path,
    max_dimension: int = DEFAULT_MAX_DIMENSION,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
) -> ProcessedImage:
    """预处理单张图片。

    Args:
        image_path: 图片文件路径
        max_dimension: 最大边长（超过则等比缩放）
        max_size_bytes: 最大文件大小（超过则压缩质量）

    Returns:
        ProcessedImage 包含 base64 编码的图片数据。
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    original_size = image_path.stat().st_size

    try:
        from PIL import Image, ExifTags
    except ImportError:
        # 如果没安装 Pillow，直接读取原始文件做 base64
        logger.warning("Pillow 未安装，跳过图片预处理（直接读取原始文件）")
        return _fallback_read(image_path, original_size)

    # 读取图片
    img = Image.open(image_path)

    # Step 1: EXIF 方向修正
    img = _fix_exif_orientation(img)

    # Step 2: 格式转换（GIF 取第一帧，RGBA 转 RGB）
    if img.mode == "RGBA":
        # PNG 带透明通道 → 保持 PNG 格式
        output_format = "PNG"
        mime_type = "image/png"
    elif img.mode == "P":
        img = img.convert("RGBA")
        output_format = "PNG"
        mime_type = "image/png"
    else:
        # 其他格式统一转 JPEG（更小）
        if img.mode != "RGB":
            img = img.convert("RGB")
        output_format = "JPEG"
        mime_type = "image/jpeg"

    # Step 3: 尺寸缩放
    w, h = img.size
    if max(w, h) > max_dimension:
        ratio = max_dimension / max(w, h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        logger.info("图片缩放: %dx%d → %dx%d", w, h, new_w, new_h)
        w, h = new_w, new_h

    # Step 4: 编码为 bytes
    buffer = io.BytesIO()
    if output_format == "JPEG":
        img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    else:
        img.save(buffer, format="PNG", optimize=True)

    image_bytes = buffer.getvalue()
    processed_size = len(image_bytes)

    # Step 5: 如果超过大小限制，降低质量重试（仅 JPEG）
    if processed_size > max_size_bytes and output_format == "JPEG":
        for quality in [70, 55, 40]:
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            image_bytes = buffer.getvalue()
            processed_size = len(image_bytes)
            if processed_size <= max_size_bytes:
                logger.info("降低 JPEG 质量到 %d%%，大小: %d bytes", quality, processed_size)
                break

    # Step 6: base64 编码
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    result = ProcessedImage(
        base64_data=b64_data,
        mime_type=mime_type,
        original_path=str(image_path),
        original_size=original_size,
        processed_size=processed_size,
        width=w,
        height=h,
    )

    logger.info(
        "图片预处理完成: %s (%dx%d, %d→%d bytes, %.1f%%)",
        image_path.name, w, h, original_size, processed_size,
        result.compression_ratio * 100,
    )

    return result


def _fix_exif_orientation(img) -> "Image.Image":
    """根据 EXIF 信息修正图片方向。"""
    try:
        from PIL import ExifTags

        exif = img.getexif()
        if not exif:
            return img

        # 找到 Orientation 标签
        orientation_key = None
        for tag, name in ExifTags.TAGS.items():
            if name == "Orientation":
                orientation_key = tag
                break

        if orientation_key is None or orientation_key not in exif:
            return img

        orientation = exif[orientation_key]

        # 根据 EXIF Orientation 值旋转/翻转
        from PIL import Image
        if orientation == 2:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        elif orientation == 3:
            img = img.rotate(180, expand=True)
        elif orientation == 4:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        elif orientation == 5:
            img = img.rotate(270, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
        elif orientation == 6:
            img = img.rotate(270, expand=True)
        elif orientation == 7:
            img = img.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
        elif orientation == 8:
            img = img.rotate(90, expand=True)

        logger.debug("EXIF 方向修正: orientation=%d", orientation)

    except Exception as e:
        logger.debug("EXIF 方向修正失败（忽略）: %s", e)

    return img


def _fallback_read(image_path: Path, original_size: int) -> ProcessedImage:
    """Pillow 不可用时的回退方案：直接读取原始文件。"""
    suffix = image_path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime_type = mime_map.get(suffix, "image/jpeg")

    raw_bytes = image_path.read_bytes()
    b64_data = base64.b64encode(raw_bytes).decode("utf-8")

    return ProcessedImage(
        base64_data=b64_data,
        mime_type=mime_type,
        original_path=str(image_path),
        original_size=original_size,
        processed_size=len(raw_bytes),
    )

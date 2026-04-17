"""图片加载器 — 支持三种输入源。

1. 本地文件夹批量扫描（jpg/png/webp/gif）
2. 手动指定单张/多张图片路径
3. 飞书云盘文件 URL/token 下载
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 支持的图片格式
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@dataclass
class ImageItem:
    """单张待处理图片的元数据。"""

    path: Path  # 本地文件路径
    source_type: str = "local"  # local | feishu | manual
    original_name: str = ""  # 原始文件名（用于知识点 ID 前缀）
    feishu_token: str = ""  # 飞书文件 token（如果来源是飞书）

    def __post_init__(self):
        if not self.original_name:
            self.original_name = self.path.stem


@dataclass
class ImageBatch:
    """一批待处理的图片集合。"""

    items: list[ImageItem] = field(default_factory=list)
    batch_name: str = ""  # 批次名称（用于知识点 ID 前缀）

    @property
    def count(self) -> int:
        return len(self.items)

    def __repr__(self) -> str:
        return f"ImageBatch(name={self.batch_name!r}, count={self.count})"


def scan_folder(
    folder_path: str | Path,
    recursive: bool = False,
) -> ImageBatch:
    """扫描本地文件夹，收集所有支持格式的图片。

    Args:
        folder_path: 文件夹路径
        recursive: 是否递归扫描子目录

    Returns:
        ImageBatch 包含所有找到的图片。
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise FileNotFoundError(f"文件夹不存在: {folder}")

    items: list[ImageItem] = []

    if recursive:
        all_files = sorted(folder.rglob("*"))
    else:
        all_files = sorted(folder.iterdir())

    for fp in all_files:
        if fp.is_file() and fp.suffix.lower() in SUPPORTED_EXTENSIONS:
            # 跳过隐藏文件和以 _ 开头的文件
            if fp.name.startswith(".") or fp.name.startswith("_"):
                continue
            items.append(ImageItem(
                path=fp,
                source_type="local",
                original_name=fp.stem,
            ))

    batch = ImageBatch(
        items=items,
        batch_name=folder.name,
    )

    logger.info(
        "扫描文件夹 %s: 发现 %d 张图片 (recursive=%s)",
        folder, batch.count, recursive,
    )
    return batch


def load_paths(
    paths: list[str | Path],
) -> ImageBatch:
    """从手动指定的路径列表加载图片。

    Args:
        paths: 图片文件路径列表

    Returns:
        ImageBatch 包含所有有效的图片。
    """
    items: list[ImageItem] = []

    for p in paths:
        fp = Path(p)
        if not fp.exists():
            logger.warning("图片文件不存在，跳过: %s", fp)
            continue
        if not fp.is_file():
            logger.warning("不是文件，跳过: %s", fp)
            continue
        if fp.suffix.lower() not in SUPPORTED_EXTENSIONS:
            logger.warning("不支持的图片格式 (%s)，跳过: %s", fp.suffix, fp)
            continue

        items.append(ImageItem(
            path=fp,
            source_type="manual",
            original_name=fp.stem,
        ))

    batch = ImageBatch(
        items=items,
        batch_name="manual",
    )

    logger.info("手动加载 %d 张图片", batch.count)
    return batch


def download_feishu_images(
    feishu_client: Any,
    file_tokens_or_urls: list[str],
    download_dir: str | Path | None = None,
) -> ImageBatch:
    """从飞书云盘下载图片到本地临时目录。

    Args:
        feishu_client: FeishuClient 实例
        file_tokens_or_urls: 飞书文件 token 或 URL 列表
        download_dir: 下载目录，默认使用临时目录

    Returns:
        ImageBatch 包含所有成功下载的图片。
    """
    from feishu_client import parse_doc_token

    if download_dir is None:
        download_dir = Path(tempfile.mkdtemp(prefix="img2k_feishu_"))
    else:
        download_dir = Path(download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)

    items: list[ImageItem] = []

    for token_or_url in file_tokens_or_urls:
        try:
            file_token = parse_doc_token(token_or_url)

            # 尝试获取文件元信息以确定文件名
            try:
                meta = feishu_client.get_file_meta(file_token)
                file_name = meta.get("title", file_token)
            except Exception:
                file_name = file_token

            # 确保有合理的扩展名
            save_name = file_name
            if not any(save_name.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                save_name += ".png"  # 默认扩展名

            save_path = download_dir / save_name

            # 下载文件
            feishu_client.download_file(file_token, str(save_path))

            # 验证是否为支持的图片格式
            if save_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                logger.warning("下载的文件不是支持的图片格式: %s", save_path)
                continue

            items.append(ImageItem(
                path=save_path,
                source_type="feishu",
                original_name=save_path.stem,
                feishu_token=file_token,
            ))

            logger.info("已下载飞书图片: %s → %s", file_token, save_path)

        except Exception as e:
            logger.error("下载飞书图片失败 (%s): %s", token_or_url, e)

    batch = ImageBatch(
        items=items,
        batch_name="feishu",
    )

    logger.info("从飞书下载 %d 张图片", batch.count)
    return batch

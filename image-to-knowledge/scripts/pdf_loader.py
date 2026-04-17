"""PDF 文件加载器 — 将 PDF 页面渲染为图片供 Vision AI 分析。

支持将多页 PDF 拆分为单页图片，每页作为独立的 ImageItem 进入处理流程。
依赖 PyMuPDF (fitz) 库。
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from image_loader import ImageBatch, ImageItem

logger = logging.getLogger(__name__)

# PDF 渲染默认 DPI（越高越清晰，但文件越大）
DEFAULT_DPI = 200
# 单个 PDF 最大处理页数（防止超大文件卡住）
MAX_PAGES = 50


def is_pdf(file_path: str | Path) -> bool:
    """判断文件是否为 PDF。"""
    return Path(file_path).suffix.lower() == ".pdf"


def load_pdf(
    pdf_path: str | Path,
    dpi: int = DEFAULT_DPI,
    max_pages: int = MAX_PAGES,
    page_range: Optional[tuple[int, int]] = None,
    output_dir: str | Path | None = None,
) -> ImageBatch:
    """将 PDF 文件的每一页渲染为 PNG 图片。

    Args:
        pdf_path: PDF 文件路径
        dpi: 渲染分辨率，默认 200
        max_pages: 最大处理页数
        page_range: 可选的页码范围 (start, end)，从 0 开始
        output_dir: 图片输出目录，默认使用临时目录

    Returns:
        ImageBatch 包含每页渲染后的图片。
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError(
            "PDF 处理需要 PyMuPDF 库。请安装：pip install PyMuPDF\n"
            "或：pip install -r requirements.txt"
        )

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    if not pdf_path.suffix.lower() == ".pdf":
        raise ValueError(f"不是 PDF 文件: {pdf_path}")

    # 输出目录
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="img2k_pdf_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    pdf_name = pdf_path.stem

    logger.info("打开 PDF: %s (%d 页)", pdf_path.name, total_pages)

    # 确定页码范围
    start_page = 0
    end_page = min(total_pages, max_pages)

    if page_range:
        start_page = max(0, page_range[0])
        end_page = min(total_pages, page_range[1])

    if end_page - start_page > max_pages:
        logger.warning(
            "PDF 页数 %d 超过上限 %d，只处理前 %d 页",
            end_page - start_page, max_pages, max_pages,
        )
        end_page = start_page + max_pages

    items: list[ImageItem] = []
    zoom = dpi / 72  # PDF 默认 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    for page_num in range(start_page, end_page):
        try:
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix)

            # 保存为 PNG
            page_name = f"{pdf_name}_p{page_num + 1:03d}"
            png_path = output_dir / f"{page_name}.png"
            pix.save(str(png_path))

            items.append(ImageItem(
                path=png_path,
                source_type="pdf",
                original_name=page_name,
            ))

            logger.debug(
                "PDF 第 %d 页渲染完成: %s (%dx%d)",
                page_num + 1, png_path.name, pix.width, pix.height,
            )

        except Exception as e:
            logger.error("PDF 第 %d 页渲染失败: %s", page_num + 1, e)

    doc.close()

    batch = ImageBatch(
        items=items,
        batch_name=pdf_name,
    )

    logger.info(
        "PDF 加载完成: %s → %d/%d 页成功渲染",
        pdf_path.name, batch.count, end_page - start_page,
    )
    return batch


def load_pdf_batch(
    paths: list[str | Path],
    dpi: int = DEFAULT_DPI,
    max_pages: int = MAX_PAGES,
    output_dir: str | Path | None = None,
) -> list[ImageBatch]:
    """批量加载多个 PDF 文件。

    Args:
        paths: PDF 文件路径列表
        dpi: 渲染分辨率
        max_pages: 每个 PDF 最大处理页数
        output_dir: 共享输出目录

    Returns:
        每个 PDF 对应一个 ImageBatch。
    """
    batches: list[ImageBatch] = []

    for p in paths:
        p = Path(p)
        if not p.exists():
            logger.warning("PDF 文件不存在，跳过: %s", p)
            continue
        if not is_pdf(p):
            logger.warning("不是 PDF 文件，跳过: %s", p)
            continue

        try:
            batch = load_pdf(p, dpi=dpi, max_pages=max_pages, output_dir=output_dir)
            if batch.count > 0:
                batches.append(batch)
        except Exception as e:
            logger.error("加载 PDF 失败 (%s): %s", p, e)

    return batches

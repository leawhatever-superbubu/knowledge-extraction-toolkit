#!/usr/bin/env python3
"""image-to-knowledge Pipeline — 主入口。

将案例图片和 PDF 文件（营销海报、数据报表截图、聊天记录、PPT截图等）
通过 Vision AI 分析后提取面向中小客的结构化知识点，
输出到本地 Markdown/JSON 或飞书多维表格。

用法:
  # 从本地文件夹批量处理（图片+PDF混合扫描）
  python3 pipeline.py --folder /path/to/files/

  # 处理 PDF 文件
  python3 pipeline.py --pdf report.pdf slides.pdf

  # 处理指定图片
  python3 pipeline.py --images img1.jpg img2.png

  # 指定输出格式
  python3 pipeline.py --folder /path/ --output-format json
  python3 pipeline.py --folder /path/ --output-format both
  python3 pipeline.py --folder /path/ --output-format feishu

  # 预览模式（只分析不输出）
  python3 pipeline.py --folder /path/ --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 确保脚本目录在 Python 路径中
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from dotenv import load_dotenv

from image_loader import ImageBatch, ImageItem, scan_folder, load_paths
from image_preprocessor import preprocess_image, ProcessedImage
from vision_analyzer import analyze_image, VisionAnalysis
from knowledge_extractor import extract_all_knowledge, KnowledgeItem
from gemini_client import create_ai_client
from local_writer import write_markdown, write_json
from pdf_loader import is_pdf, load_pdf, load_pdf_batch

# ── 日志配置 ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


# ── 配置加载 ──────────────────────────────────────────────

def load_config() -> dict:
    """加载 config.json。"""
    config_path = SKILL_ROOT / "config.json"
    if not config_path.exists():
        logger.warning("配置文件不存在: %s，使用默认配置", config_path)
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


# ── 核心处理流程 ─────────────────────────────────────────

def process_image_batch(
    batch: ImageBatch,
    ai_client,
    config: dict,
    output_dir: Path,
    dry_run: bool = False,
    output_format: str = "markdown",
    source_context: str = "",
) -> dict:
    """处理一批图片的完整流程。

    Args:
        ai_client: AI 客户端
        config: 运行时配置
        output_dir: 输出目录
        dry_run: 预览模式（只分析不输出）
        output_format: 输出格式 — "markdown" / "json" / "both" / "feishu"
        source_context: 案例来源场景（如"微信小店商家使用小店广告"）

    Returns:
        结果字典: {"batch_name", "status", "image_count", "knowledge_count", ...}
    """
    result = {
        "batch_name": batch.batch_name,
        "status": "pending",
        "image_count": batch.count,
        "valid_analyses": 0,
        "knowledge_count": 0,
        "output_files": [],
        "error": None,
        "image_details": [],
    }

    try:
        if batch.count == 0:
            raise ValueError("没有图片需要处理")

        vision_config = config.get("vision", {})
        max_dim = vision_config.get("max_image_dimension", 2048)
        max_size = vision_config.get("max_image_size_bytes", 4194304)
        vision_model = vision_config.get("model", config.get("ai", {}).get("model", "gemini-2.5-flash"))

        # ── Step 1: 图片预处理 ────────────────────────
        logger.info("=" * 60)
        logger.info("Step 1/4: 图片预处理 (%d 张)", batch.count)

        processed_images: list[tuple[str, ProcessedImage]] = []

        for item in batch.items:
            try:
                processed = preprocess_image(
                    item.path,
                    max_dimension=max_dim,
                    max_size_bytes=max_size,
                )
                processed_images.append((item.original_name, processed))
            except Exception as e:
                logger.error("预处理失败: %s — %s", item.path, e)
                result["image_details"].append({
                    "image_name": item.original_name,
                    "status": "preprocess_failed",
                    "error": str(e),
                })

        logger.info("预处理完成: %d/%d 张成功", len(processed_images), batch.count)

        if not processed_images:
            raise ValueError("所有图片预处理失败，无法继续")

        # ── Step 2: Vision AI 分析 ───────────────────
        logger.info("Step 2/4: Vision AI 分析")

        analyses: list[VisionAnalysis] = []

        for i, (name, img) in enumerate(processed_images):
            logger.info("  分析 [%d/%d]: %s", i + 1, len(processed_images), name)

            analysis = analyze_image(
                ai_client=ai_client,
                processed_image=img,
                image_name=name,
                model=vision_model,
                temperature=vision_config.get("temperature", 0.3),
                max_tokens=vision_config.get("max_tokens_per_request", 16384),
                source_context=source_context,
            )
            analyses.append(analysis)

            result["image_details"].append({
                "image_name": name,
                "image_type": analysis.image_type,
                "confidence": analysis.confidence,
                "is_valid": analysis.is_valid,
                "text_length": len(analysis.structured_text),
            })

            # API 调用间隔
            if i < len(processed_images) - 1:
                import time
                time.sleep(1.0)

        valid_analyses = [a for a in analyses if a.is_valid]
        result["valid_analyses"] = len(valid_analyses)

        logger.info(
            "Vision 分析完成: %d/%d 张有效",
            len(valid_analyses), len(analyses),
        )

        if not valid_analyses:
            raise ValueError("所有图片 Vision 分析失败或结果不足，无法提取知识点")

        # ── Step 3: AI 知识点提取 ────────────────────
        logger.info("Step 3/4: AI 知识点提取")

        knowledge_items = extract_all_knowledge(
            ai_client=ai_client,
            analyses=valid_analyses,
            config=config,
            source_context=source_context,
        )

        result["knowledge_count"] = len(knowledge_items)

        if not knowledge_items:
            raise ValueError("未提取到任何知识点")

        logger.info("提取完成: 共 %d 个知识点", len(knowledge_items))

        # 打印知识点概况
        for item in knowledge_items:
            logger.info("  [%s] %s — %s (%s)", item.id, item.title, item.type, item.difficulty)

        # ── Step 4: 输出知识点 ───────────────────────
        if dry_run:
            logger.info("Step 4/4: [DRY RUN] 跳过输出")
        else:
            doc_title = f"{batch.batch_name}(图片案例)"
            logger.info("Step 4/4: 导出知识点 (格式: %s)", output_format)

            if output_format in ("markdown", "both"):
                md_path = write_markdown(
                    items=knowledge_items,
                    doc_title=doc_title,
                    output_dir=output_dir,
                    source_context=source_context,
                )
                result["output_files"].append({"type": "markdown", "path": str(md_path)})

            if output_format in ("json", "both"):
                json_path = write_json(
                    items=knowledge_items,
                    doc_title=doc_title,
                    output_dir=output_dir,
                    source_context=source_context,
                )
                result["output_files"].append({"type": "json", "path": str(json_path)})

            if output_format == "feishu":
                # 飞书写入（需要额外安装飞书依赖）
                _write_to_feishu(knowledge_items, batch.batch_name, config)
                result["output_files"].append({"type": "feishu", "path": "bitable"})

            # 始终导出一份 JSON 备份
            if output_format != "json" and output_format != "both":
                backup_path = _export_json(
                    batch_name=batch.batch_name,
                    analyses=valid_analyses,
                    items=knowledge_items,
                    output_dir=output_dir,
                )
                result["output_files"].append({"type": "json_backup", "path": str(backup_path)})

        result["status"] = "completed"

    except Exception as e:
        logger.error("处理批次 '%s' 失败: %s", batch.batch_name, e, exc_info=True)
        result["status"] = "failed"
        result["error"] = str(e)

    return result


def _write_to_feishu(items: list, batch_name: str, config: dict):
    """飞书写入（延迟导入，仅在选择飞书输出时才需要依赖）。"""
    from feishu_client import FeishuClient
    from bitable_writer import write_knowledge_to_bitable

    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        raise RuntimeError("飞书输出需要配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

    feishu_client = FeishuClient(app_id, app_secret)
    feishu_cfg = config.get("feishu", {})
    app_token = feishu_cfg.get("app_token") or os.getenv("FEISHU_BITABLE_APP_TOKEN", "")
    table_id = feishu_cfg.get("table_id") or os.getenv("FEISHU_BITABLE_TABLE_ID", "")

    if not app_token or not table_id:
        raise RuntimeError("未配置飞书多维表格 app_token/table_id")

    doc_title = f"{batch_name}(图片案例)"
    write_knowledge_to_bitable(
        client=feishu_client,
        app_token=app_token,
        table_id=table_id,
        items=items,
        doc_title=doc_title,
        field_map=config.get("field_map"),
    )


def _export_json(
    batch_name: str,
    analyses: list[VisionAnalysis],
    items: list[KnowledgeItem],
    output_dir: Path,
) -> Path:
    """导出知识点到本地 JSON 文件。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in batch_name)
    json_path = output_dir / f"IMG_{safe_name}_knowledge.json"

    tz_cn = timezone(timedelta(hours=8))
    data = {
        "batch_name": batch_name,
        "extracted_at": datetime.now(tz_cn).isoformat(),
        "total_images": len(analyses),
        "total_knowledge_count": len(items),
        "image_analyses": [
            {
                "image_name": a.image_name,
                "image_type": a.image_type,
                "confidence": a.confidence,
                "structured_text_length": len(a.structured_text),
            }
            for a in analyses
        ],
        "knowledge_items": [item.to_dict() for item in items],
    }

    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("已导出 JSON: %s (%d 个知识点)", json_path, len(items))
    return json_path


# ── CLI 入口 ──────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="image-to-knowledge: 图片/PDF → 面向中小客的结构化知识点",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # ── 输入源 ──────────────────────────────────────
    parser.add_argument(
        "--folder", default=None,
        help="本地文件夹路径（自动扫描所有 jpg/png/webp/gif/pdf）",
    )
    parser.add_argument(
        "--images", nargs="+", default=None,
        help="手动指定图片文件路径（支持多个，空格分隔）",
    )
    parser.add_argument(
        "--pdf", nargs="+", default=None,
        help="PDF 文件路径（支持多个，每页渲染为图片后分析）",
    )
    parser.add_argument(
        "--feishu-files", nargs="+", default=None,
        help="飞书云盘文件 token 或 URL（需配置飞书凭证）",
    )
    parser.add_argument(
        "--recursive", action="store_true",
        help="递归扫描子目录（配合 --folder 使用）",
    )
    # ── 输出控制 ────────────────────────────────────
    parser.add_argument(
        "--output-format", default="markdown",
        choices=["markdown", "json", "both", "feishu"],
        help="输出格式：markdown（默认）/ json / both / feishu（需飞书凭证）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="预览模式：只分析和提取，不生成输出文件",
    )
    parser.add_argument(
        "--output", default=None,
        help="输出目录，默认为 skill 根目录下的 output/",
    )
    # ── AI 模型 ─────────────────────────────────────
    parser.add_argument(
        "--model", default=None,
        help="AI 模型名称，覆盖 config.json 中的配置",
    )
    parser.add_argument(
        "--env", default=None,
        help=".env 文件路径，默认为 skill 根目录下的 .env",
    )
    # ── 场景上下文 ──────────────────────────────────
    parser.add_argument(
        "--scene", default=None,
        help="案例来源场景描述（如 '微信小店商家使用小店广告'），注入 Prompt 标注知识点来源",
    )
    # ── PDF 参数 ────────────────────────────────────
    parser.add_argument(
        "--pdf-dpi", type=int, default=200,
        help="PDF 渲染分辨率（默认 200 DPI）",
    )
    parser.add_argument(
        "--pdf-max-pages", type=int, default=50,
        help="PDF 最大处理页数（默认 50）",
    )
    # ── IPC 契约 ────────────────────────────────────
    parser.add_argument(
        "--output-meta", type=str, default=None,
        help="[pipeline-ceo] 输出 meta JSON 路径（IPC 文件契约）",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    # 加载 .env
    env_path = Path(args.env) if args.env else SKILL_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info("已加载 %s", env_path)
    else:
        logger.warning(".env 文件不存在: %s，将从环境变量读取凭证", env_path)

    # 加载配置
    config = load_config()

    # 覆盖模型
    if args.model:
        config.setdefault("ai", {})["model"] = args.model
        config.setdefault("vision", {})["model"] = args.model

    # 收集图片批次
    batches: list[ImageBatch] = []

    # 本地文件夹扫描（图片 + PDF 混合）
    if args.folder:
        folder = Path(args.folder)
        # 扫描图片
        batch = scan_folder(args.folder, recursive=args.recursive)
        if batch.count > 0:
            batches.append(batch)

        # 扫描文件夹中的 PDF
        pdf_files = sorted(folder.glob("*.pdf")) if not args.recursive else sorted(folder.rglob("*.pdf"))
        if pdf_files:
            logger.info("文件夹中发现 %d 个 PDF 文件", len(pdf_files))
            pdf_batches = load_pdf_batch(
                pdf_files,
                dpi=args.pdf_dpi,
                max_pages=args.pdf_max_pages,
            )
            batches.extend(pdf_batches)

        if not batches:
            logger.warning("文件夹中没有找到支持的图片或 PDF: %s", args.folder)

    # 手动指定图片
    if args.images:
        batch = load_paths(args.images)
        if batch.count > 0:
            batches.append(batch)
        else:
            logger.warning("指定的图片路径均无效")

    # PDF 文件
    if args.pdf:
        pdf_batches = load_pdf_batch(
            args.pdf,
            dpi=args.pdf_dpi,
            max_pages=args.pdf_max_pages,
        )
        batches.extend(pdf_batches)

    # 飞书云盘图片（延迟导入）
    if args.feishu_files:
        from feishu_client import FeishuClient
        from image_loader import download_feishu_images

        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if not app_id or not app_secret:
            logger.error("从飞书下载图片需要配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
            return 1
        feishu_client = FeishuClient(app_id, app_secret)
        batch = download_feishu_images(feishu_client, args.feishu_files)
        if batch.count > 0:
            batches.append(batch)
        else:
            logger.warning("从飞书下载图片均失败")

    if not batches:
        logger.error("请指定输入来源（--folder / --images / --pdf / --feishu-files）")
        return 1

    # 读取 AI 凭证
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_api_key:
        logger.error("缺少 AI 模型 API Key，请设置 OPENAI_API_KEY")
        return 1

    # 初始化 AI 客户端
    ai_config = config.get("ai", {})
    ai_base_url = os.getenv("OPENAI_BASE_URL") or ai_config.get("base_url", "")
    ai_client = create_ai_client(
        api_key=openai_api_key,
        base_url=ai_base_url,
    )
    logger.info("AI 客户端已初始化 (model=%s)", ai_config.get("model", "gemini-2.5-flash"))

    # 输出目录
    output_dir = Path(args.output) if args.output else SKILL_ROOT / "output"

    # 场景上下文：--scene > config.extraction.source_context > 空
    source_context = args.scene or config.get("extraction", {}).get("source_context", "") or ""
    if source_context:
        logger.info("案例来源场景: %s", source_context)

    # ── 逐批处理 ──────────────────────────────────────

    results = []

    for batch in batches:
        logger.info("开始处理批次: %s (%d 张图片)", batch.batch_name, batch.count)
        result = process_image_batch(
            batch=batch,
            ai_client=ai_client,
            config=config,
            output_dir=output_dir,
            dry_run=args.dry_run,
            output_format=args.output_format,
            source_context=source_context,
        )
        results.append(result)

    # ── 最终汇总 ──────────────────────────────────────

    print("\n" + "=" * 60)
    print("处理完成汇总")
    print("=" * 60)

    for r in results:
        status_icon = {"completed": "OK", "failed": "XX"}.get(r["status"], "??")
        print(f"  [{status_icon}] {r['batch_name']}")
        print(f"       图片: {r['image_count']} 张, Vision 有效: {r['valid_analyses']} 张")
        print(f"       知识点: {r['knowledge_count']} 个")
        if r["output_files"]:
            for of in r["output_files"]:
                print(f"       输出 [{of['type']}]: {of['path']}")
        if r["error"]:
            print(f"       错误: {r['error']}")

    total_batches = len(results)
    success = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    total_images = sum(r["image_count"] for r in results)
    total_knowledge = sum(r["knowledge_count"] for r in results)

    print(f"\n总计: {total_batches} 批次, 成功: {success}, 失败: {failed}")
    print(f"      {total_images} 张图片, {total_knowledge} 个知识点")

    # 保存汇总报告
    report_path = output_dir / "image_pipeline_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"汇总报告: {report_path}")

    # ── output-meta（IPC 文件契约）────────────────────
    if args.output_meta:
        try:
            meta_data = {
                "stage_name": "image-to-knowledge",
                "status": "success" if failed == 0 else "partial",
                "summary": {
                    "total_batches": total_batches,
                    "success": success,
                    "failed": failed,
                    "total_images": total_images,
                    "total_knowledge_points": total_knowledge,
                },
                "artifacts": [
                    f["path"]
                    for r in results if r["status"] == "completed"
                    for f in r.get("output_files", [])
                ],
            }
            os.makedirs(os.path.dirname(args.output_meta), exist_ok=True)
            with open(args.output_meta, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Warning] Failed to write output-meta: {e}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

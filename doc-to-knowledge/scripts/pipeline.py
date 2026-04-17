#!/usr/bin/env python3
"""doc-to-knowledge Pipeline — 主入口。

将飞书文档（视频转录稿）转化为面向中小客的结构化知识点，
写入飞书多维表格并导出本地 JSON 备份。

用法:
  # 处理单个飞书文档
  python3 pipeline.py --doc-token XxXxXx

  # 处理飞书文档 URL
  python3 pipeline.py --doc-url "https://your-domain.feishu.cn/docx/XxXxXx"

  # 批量处理多个文档
  python3 pipeline.py --doc-token AAA BBB CCC

  # 只提取不写入多维表格（预览模式）
  python3 pipeline.py --doc-token XxXxXx --dry-run

  # 只导出 JSON 不写飞书
  python3 pipeline.py --doc-token XxXxXx --json-only

  # 从本地 .docx 文件提取
  python3 pipeline.py --local-docx path/to/file.docx

  # 从 Obsidian Markdown 笔记提取（Playbook 模式）
  python3 pipeline.py --local-md path/to/playbook/
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
from openai import OpenAI

from feishu_client import FeishuClient, parse_doc_token
from doc_reader import read_document, read_local_docx, read_local_markdown, DocumentContent
from knowledge_extractor import extract_all_knowledge, KnowledgeItem
from bitable_writer import write_knowledge_to_bitable
from local_writer import write_markdown, write_json
from gemini_client import create_ai_client

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


# ── 单文档处理 ────────────────────────────────────────────

def process_single_document(
    doc_token: str,
    feishu_client: FeishuClient | None,
    ai_client: OpenAI,
    config: dict,
    output_dir: Path,
    dry_run: bool = False,
    output_format: str = "markdown",
) -> dict:
    """处理单个飞书文档的完整流程。

    Returns:
        结果字典: {"doc_title", "doc_token", "status", "knowledge_count", "error"}
    """
    result = {
        "doc_title": "",
        "doc_token": doc_token,
        "status": "pending",
        "knowledge_count": 0,
        "write_result": None,
        "output_files": [],
        "error": None,
    }

    try:
        # ── Step 1: 读取飞书文档 ────────────────────────
        logger.info("=" * 60)
        logger.info("Step 1/4: 读取飞书文档 — %s", doc_token)
        if not feishu_client:
            raise ValueError("需要读取飞书文档，但未配置飞书凭证")
            
        doc = read_document(feishu_client, doc_token)
        result["doc_title"] = doc.doc_title

        logger.info(
            "文档概况: %s — %d 章节, %d 字",
            doc.doc_title, len(doc.chapters), doc.total_word_count,
        )

        if not doc.chapters:
            raise ValueError("文档中没有可提取的章节内容")

        # 打印章节概况
        for i, ch in enumerate(doc.chapters, 1):
            logger.info("  章节 %d: %s (%d 字, %d 段)", i, ch.title, ch.word_count, len(ch.paragraphs))

        # ── Step 2: AI 提取知识点 ──────────────────────
        logger.info("Step 2/4: AI 提取知识点")
        knowledge_items = extract_all_knowledge(
            ai_client=ai_client,
            doc=doc,
            config=config,
        )

        result["knowledge_count"] = len(knowledge_items)

        if not knowledge_items:
            raise ValueError("未提取到任何知识点")

        logger.info("提取完成: 共 %d 个知识点", len(knowledge_items))

        # 打印知识点概况
        for item in knowledge_items:
            logger.info("  [%s] %s — %s (%s)", item.id, item.title, item.type, item.difficulty)

        # ── Step 3: 输出知识点 ────────────────────────
        if dry_run:
            logger.info("Step 3/4: [DRY RUN] 跳过输出")
        else:
            logger.info("Step 3/4: 输出知识点 (格式: %s)", output_format)
            
            if output_format in ("markdown", "both", "all"):
                md_path = write_markdown(
                    items=knowledge_items,
                    doc_title=doc.doc_title,
                    output_dir=output_dir,
                    source_context="",
                )
                result["output_files"].append({"type": "markdown", "path": str(md_path)})
                
            if output_format in ("json", "both", "all"):
                json_path = write_json(
                    items=knowledge_items,
                    doc_title=doc.doc_title,
                    output_dir=output_dir,
                    source_context="",
                )
                result["output_files"].append({"type": "json", "path": str(json_path)})
                
            if output_format in ("feishu", "all"):
                feishu_cfg = config.get("feishu", {})
                app_token = feishu_cfg.get("app_token") or os.getenv("FEISHU_BITABLE_APP_TOKEN", "")
                table_id = feishu_cfg.get("table_id") or os.getenv("FEISHU_BITABLE_TABLE_ID", "")
    
                if not app_token or not table_id:
                    logger.warning("未配置多维表格 app_token/table_id，跳过写入飞书")
                else:
                    write_result = write_knowledge_to_bitable(
                        client=feishu_client,
                        app_token=app_token,
                        table_id=table_id,
                        items=knowledge_items,
                        doc_title=doc.doc_title,
                        field_map=config.get("field_map"),
                    )
                    result["write_result"] = write_result
                    result["output_files"].append({"type": "feishu", "path": "bitable"})

        # ── Step 4: 本地 JSON 备份 ───────────────────
        if not dry_run and output_format not in ("json", "both", "all"):
            logger.info("Step 4/4: 导出本地 JSON 备份")
            json_path = _export_json(doc, knowledge_items, output_dir)
            result["output_files"].append({"type": "json_backup", "path": str(json_path)})

        result["status"] = "completed"

    except Exception as e:
        logger.error("处理文档 %s 失败: %s", doc_token, e, exc_info=True)
        result["status"] = "failed"
        result["error"] = str(e)

    return result


def _process_doc_content(
    doc: DocumentContent,
    feishu_client: FeishuClient | None,
    ai_client: OpenAI,
    config: dict,
    output_dir: Path,
    dry_run: bool = False,
    output_format: str = "markdown",
    knowledge_id_prefix: str | None = None,
    knowledge_seq_offset: int = 0,
) -> dict:
    """从已解析的 DocumentContent 开始处理（Step 2-4）。

    用于 --local-docx / --local-md 等场景，跳过 Step 1（读取飞书文档）。

    Args:
        knowledge_id_prefix: 知识点 ID 前缀（用于 Playbook 多卡片模式，避免 ID 冲突）
        knowledge_seq_offset: 全局知识点序号偏移量（跨卡片递增）
    """
    result = {
        "doc_title": doc.doc_title,
        "doc_token": doc.doc_token,
        "status": "pending",
        "knowledge_count": 0,
        "write_result": None,
        "output_files": [],
        "error": None,
    }

    try:
        logger.info("=" * 60)
        logger.info("处理本地文档: %s — %d 章节, %d 字",
                     doc.doc_title, len(doc.chapters), doc.total_word_count)

        if not doc.chapters:
            raise ValueError("文档中没有可提取的章节内容")

        for i, ch in enumerate(doc.chapters, 1):
            logger.info("  章节 %d: %s (%d 字, %d 段)", i, ch.title, ch.word_count, len(ch.paragraphs))

        # ── Step 2: AI 提取知识点 ──────────────────────
        logger.info("Step 2/4: AI 提取知识点")
        knowledge_items = extract_all_knowledge(
            ai_client=ai_client,
            doc=doc,
            config=config,
        )

        result["knowledge_count"] = len(knowledge_items)

        if not knowledge_items:
            raise ValueError("未提取到任何知识点")

        # 如果指定了 ID 前缀，重新编号避免跨卡片 ID 冲突
        if knowledge_id_prefix:
            for idx, item in enumerate(knowledge_items, 1):
                global_seq = knowledge_seq_offset + idx
                item.id = f"{knowledge_id_prefix}_K{idx:02d}"
                logger.debug("重编号: %s → 全局序号 %d", item.id, global_seq)

        logger.info("提取完成: 共 %d 个知识点", len(knowledge_items))

        for item in knowledge_items:
            logger.info("  [%s] %s — %s (%s)", item.id, item.title, item.type, item.difficulty)

        # ── Step 3: 输出知识点 ────────────────────────
        if dry_run:
            logger.info("Step 3/4: [DRY RUN] 跳过输出")
        else:
            logger.info("Step 3/4: 输出知识点 (格式: %s)", output_format)
            
            if output_format in ("markdown", "both", "all"):
                md_path = write_markdown(
                    items=knowledge_items,
                    doc_title=doc.doc_title,
                    output_dir=output_dir,
                    source_context="",
                )
                result["output_files"].append({"type": "markdown", "path": str(md_path)})
                
            if output_format in ("json", "both", "all"):
                json_path = write_json(
                    items=knowledge_items,
                    doc_title=doc.doc_title,
                    output_dir=output_dir,
                    source_context="",
                )
                result["output_files"].append({"type": "json", "path": str(json_path)})
                
            if output_format in ("feishu", "all"):
                feishu_cfg = config.get("feishu", {})
                app_token = feishu_cfg.get("app_token") or os.getenv("FEISHU_BITABLE_APP_TOKEN", "")
                table_id = feishu_cfg.get("table_id") or os.getenv("FEISHU_BITABLE_TABLE_ID", "")
    
                if not app_token or not table_id:
                    logger.warning("未配置多维表格 app_token/table_id，跳过写入飞书")
                elif not feishu_client:
                    logger.warning("需要写入飞书多维表格，但未配置飞书应用凭证")
                else:
                    write_result = write_knowledge_to_bitable(
                        client=feishu_client,
                        app_token=app_token,
                        table_id=table_id,
                        items=knowledge_items,
                        doc_title=doc.doc_title,
                        field_map=config.get("field_map"),
                    )
                    result["write_result"] = write_result
                    result["output_files"].append({"type": "feishu", "path": "bitable"})

        # ── Step 4: 本地 JSON 备份 ───────────────────
        if not dry_run and output_format not in ("json", "both", "all"):
            logger.info("Step 4/4: 导出本地 JSON 备份")
            json_path = _export_json(doc, knowledge_items, output_dir)
            result["output_files"].append({"type": "json_backup", "path": str(json_path)})

        result["status"] = "completed"

    except Exception as e:
        logger.error("处理文档 %s 失败: %s", doc.doc_token, e, exc_info=True)
        result["status"] = "failed"
        result["error"] = str(e)

    return result


def _export_json(
    doc: DocumentContent,
    items: list[KnowledgeItem],
    output_dir: Path,
) -> Path:
    """导出知识点到本地 JSON 文件。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 使用文档标题作为文件名（清理非法字符）
    safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in doc.doc_title)
    json_path = output_dir / f"{safe_title}_knowledge.json"

    tz_cn = timezone(timedelta(hours=8))
    data = {
        "doc_title": doc.doc_title,
        "doc_token": doc.doc_token,
        "extracted_at": datetime.now(tz_cn).isoformat(),
        "total_knowledge_count": len(items),
        "doc_summary": doc.to_dict(),
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
        description="doc-to-knowledge: 飞书文档 → 面向中小客的结构化知识点",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--doc-token", nargs="+", default=None,
        help="飞书文档 token（支持多个，空格分隔）",
    )
    parser.add_argument(
        "--doc-url", nargs="+", default=None,
        help="飞书文档 URL（支持多个，空格分隔）",
    )
    parser.add_argument(
        "--local-docx", nargs="+", default=None,
        help="本地 .docx 文件路径（支持多个，飞书下载失败时使用）",
    )
    parser.add_argument(
        "--local-md", nargs="+", default=None,
        help="本地 Obsidian Markdown 文件路径或目录（支持多个，自动扫描 *.md）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="预览模式：只提取知识点，不写入飞书多维表格",
    )
    parser.add_argument(
        "--output-format", choices=["markdown", "json", "feishu", "all"], default="markdown",
        help="输出格式：markdown(默认，输出md文件), json(纯数据), feishu(写入飞书多维表格), all(全部)",
    )
    parser.add_argument(
        "--output", default=None,
        help="JSON 输出目录，默认为 skill 根目录下的 output/",
    )
    parser.add_argument(
        "--model", default=None,
        help="AI 模型名称，覆盖 config.json 中的配置",
    )
    parser.add_argument(
        "--env", default=None,
        help=".env 文件路径，默认为 skill 根目录下的 .env",
    )
    parser.add_argument(
        "--output-meta", type=str, default=None,
        help="输出 meta JSON 路径（用于 pipeline 级联调度的 IPC 文件契约）",
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

    # 加载配置（提前，后续 token 回退需要用到）
    config = load_config()

    # 收集所有待处理的文档 token
    doc_tokens: list[str] = []
    if args.doc_token:
        doc_tokens.extend(args.doc_token)
    if args.doc_url:
        for url in args.doc_url:
            doc_tokens.append(parse_doc_token(url))

    # 如果 CLI 未指定 token，从 config.json 的 source.doc_tokens 读取
    if not doc_tokens and not args.local_docx and not args.local_md:
        source_tokens = config.get("source", {}).get("doc_tokens", [])
        if source_tokens:
            doc_tokens.extend(source_tokens)
            logger.info("从 config.json 读取 %d 个 doc_tokens", len(source_tokens))

    if not doc_tokens and not args.local_docx and not args.local_md:
        logger.error("请指定至少一个飞书文档（--doc-token / --doc-url / --local-docx / --local-md）或在 config.json 中配置 source.doc_tokens")
        return 1

    # 读取飞书凭证（按需）
    feishu_client = None
    if doc_tokens or args.output_format in ("feishu", "all"):
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if not app_id or not app_secret:
            logger.error("缺少飞书应用凭证，请设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
            return 1
        feishu_client = FeishuClient(app_id, app_secret)
        logger.info("飞书客户端已初始化")

    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_api_key:
        logger.error("缺少 AI 模型 API Key，请设置 OPENAI_API_KEY")
        return 1

    # 覆盖模型（如果 CLI 指定了）
    if args.model:
        config.setdefault("ai", {})["model"] = args.model

    ai_config = config.get("ai", {})
    ai_base_url = os.getenv("OPENAI_BASE_URL") or ai_config.get("base_url", "")
    ai_client = create_ai_client(
        api_key=openai_api_key,
        base_url=ai_base_url,
    )
    logger.info("AI 客户端已初始化 (model=%s)", ai_config.get("model", "gpt-4o"))

    # 输出目录
    output_dir = Path(args.output) if args.output else SKILL_ROOT / "output"

    # ── 逐文档处理 ────────────────────────────────────

    results = []

    # 处理远程飞书文档（通过 token）
    for token in doc_tokens:
        result = process_single_document(
            doc_token=token,
            feishu_client=feishu_client,
            ai_client=ai_client,
            config=config,
            output_dir=output_dir,
            dry_run=args.dry_run,
            output_format=args.output_format,
        )
        results.append(result)

    # 处理本地 .docx 文件（--local-docx 指定）
    if args.local_docx:
        for docx_path_str in args.local_docx:
            docx_path = Path(docx_path_str)
            if not docx_path.exists():
                logger.error("本地 .docx 文件不存在: %s", docx_path)
                results.append({
                    "doc_title": docx_path.stem,
                    "doc_token": f"local:{docx_path.name}",
                    "status": "failed",
                    "knowledge_count": 0,
                    "write_result": None,
                    "json_path": "",
                    "error": f"文件不存在: {docx_path}",
                })
                continue

            logger.info("处理本地 .docx: %s", docx_path)
            doc = read_local_docx(docx_path)
            result = _process_doc_content(
                doc=doc,
                feishu_client=feishu_client,
                ai_client=ai_client,
                config=config,
                output_dir=output_dir,
                dry_run=args.dry_run,
                output_format=args.output_format,
            )
            results.append(result)

    # 处理本地 Obsidian Markdown 文件（--local-md 指定）
    if args.local_md:
        # 收集所有 .md 文件路径（支持目录和文件混合传入）
        md_files: list[Path] = []
        for md_path_str in args.local_md:
            md_path = Path(md_path_str)
            if md_path.is_dir():
                found = sorted(md_path.glob("*.md"))
                # 排除以 _ 开头的文件（如 _生成指令.md）
                found = [f for f in found if not f.name.startswith("_")]
                md_files.extend(found)
                logger.info("扫描目录 %s: 发现 %d 个 .md 文件", md_path, len(found))
            elif md_path.is_file() and md_path.suffix == ".md":
                md_files.append(md_path)
            else:
                logger.error("路径不存在或不是 .md 文件: %s", md_path)
                results.append({
                    "doc_title": md_path.stem,
                    "doc_token": f"local-md:{md_path.name}",
                    "status": "failed",
                    "knowledge_count": 0,
                    "write_result": None,
                    "json_path": "",
                    "error": f"路径不存在或不是 .md 文件: {md_path}",
                })

        if md_files:
            logger.info("共 %d 个 Markdown 文件待处理", len(md_files))

            # 自动切换到 playbook 提取模式
            config.setdefault("extraction", {})["mode"] = "playbook"
            logger.info("已自动切换到 Playbook 提取模式（操作级颗粒度）")

            # 全局知识点序号计数器：确保不同卡片之间 ID 不冲突
            global_knowledge_seq = 0

            for card_idx, md_file in enumerate(md_files, 1):
                logger.info("处理 Obsidian MD [%d/%d]: %s", card_idx, len(md_files), md_file.name)
                try:
                    doc = read_local_markdown(md_file)
                    result = _process_doc_content(
                        doc=doc,
                        feishu_client=feishu_client,
                        ai_client=ai_client,
                        config=config,
                        output_dir=output_dir,
                        dry_run=args.dry_run,
                        output_format=args.output_format,
                        knowledge_id_prefix=f"SMB_PB{card_idx:02d}",
                        knowledge_seq_offset=global_knowledge_seq,
                    )
                    # 更新全局计数器
                    global_knowledge_seq += result.get("knowledge_count", 0)
                    results.append(result)
                except Exception as e:
                    logger.error("处理 %s 失败: %s", md_file.name, e)
                    results.append({
                        "doc_title": md_file.stem,
                        "doc_token": f"local-md:{md_file.name}",
                        "status": "failed",
                        "knowledge_count": 0,
                        "write_result": None,
                        "json_path": "",
                        "error": str(e),
                    })

    # ── 最终汇总 ──────────────────────────────────────

    print("\n" + "=" * 60)
    print("处理完成汇总")
    print("=" * 60)

    for r in results:
        status_icon = {"completed": "OK", "failed": "XX"}.get(r["status"], "??")
        print(f"  [{status_icon}] {r['doc_title'] or r['doc_token']}")
        print(f"       知识点: {r['knowledge_count']} 个")
        if r["write_result"]:
            wr = r["write_result"]
            print(f"       写入: 创建 {wr['created']}, 更新 {wr['updated']}, 失败 {wr['failed']}")
        if r.get("output_files"):
            for of in r["output_files"]:
                print(f"       输出 [{of['type']}]: {of['path']}")
        if r["error"]:
            print(f"       错误: {r['error']}")

    total = len(results)
    success = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    total_knowledge = sum(r["knowledge_count"] for r in results)

    print(f"\n总计: {total} 篇文档, 成功: {success}, 失败: {failed}, 共 {total_knowledge} 个知识点")

    # 保存汇总报告
    report_path = output_dir / "pipeline_report.json"
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
                "stage_name": "doc-to-knowledge",
                "status": "success" if failed == 0 else "partial",
                "summary": {
                    "total_documents": total,
                    "success": success,
                    "failed": failed,
                    "total_knowledge_points": total_knowledge,
                },
                "artifacts": [
                    f["path"] for r in results if r["status"] == "completed" 
                    for f in r.get("output_files", []) if f["type"] in ("markdown", "json")
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

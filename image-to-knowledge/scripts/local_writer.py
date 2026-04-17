"""本地输出模块 — 将知识点导出为 Markdown / JSON 文件。

替代飞书写入，提供本地友好的输出格式：
1. Markdown 文档：结构化、可读性强，适合直接阅读或粘贴到腾讯文档
2. JSON 文件：结构化数据，适合程序处理或导入其他系统
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from knowledge_extractor import KnowledgeItem

logger = logging.getLogger(__name__)

# 知识点类型中英文映射
TYPE_DISPLAY_MAP = {
    "concept": "概念解释",
    "how_to": "操作方法",
    "pitfall": "避坑提醒",
    "data_insight": "数据洞察",
    "trend": "行业趋势",
    "tool_tip": "工具技巧",
}

# 难度等级 badge
DIFFICULTY_BADGE = {
    "入门": "🟢 入门",
    "进阶": "🟡 进阶",
    "高级": "🔴 高级",
}


def write_markdown(
    items: list[KnowledgeItem],
    doc_title: str,
    output_dir: str | Path,
    source_context: str = "",
) -> Path:
    """将知识点列表导出为 Markdown 文档。

    生成的 Markdown 结构清晰，适合：
    - 直接阅读
    - 粘贴到腾讯文档
    - 导入 Obsidian 等知识管理工具

    Args:
        items: 知识点列表
        doc_title: 文档标题
        output_dir: 输出目录
        source_context: 案例来源场景

    Returns:
        生成的 Markdown 文件路径。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tz_cn = timezone(timedelta(hours=8))
    now = datetime.now(tz_cn)

    # 文件名
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in doc_title)
    md_path = output_dir / f"{safe_name}_知识点.md"

    lines: list[str] = []

    # 标题和元信息
    lines.append(f"# {doc_title}")
    lines.append("")
    lines.append(f"> 提取时间：{now.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 知识点总数：{len(items)} 个")
    if source_context:
        lines.append(f"> 案例来源场景：{source_context}")
    lines.append("")

    # 统计概览
    type_counts: dict[str, int] = {}
    difficulty_counts: dict[str, int] = {}
    for item in items:
        t = TYPE_DISPLAY_MAP.get(item.type, item.type)
        type_counts[t] = type_counts.get(t, 0) + 1
        difficulty_counts[item.difficulty] = difficulty_counts.get(item.difficulty, 0) + 1

    lines.append("## 概览")
    lines.append("")
    lines.append("| 类型 | 数量 |")
    lines.append("|------|------|")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {t} | {c} |")
    lines.append("")

    lines.append("| 难度 | 数量 |")
    lines.append("|------|------|")
    for d, c in sorted(difficulty_counts.items()):
        badge = DIFFICULTY_BADGE.get(d, d)
        lines.append(f"| {badge} | {c} |")
    lines.append("")

    # 目录
    lines.append("## 目录")
    lines.append("")
    for i, item in enumerate(items, 1):
        t = TYPE_DISPLAY_MAP.get(item.type, item.type)
        lines.append(f"{i}. [{item.title}](#{_slugify(item.id)}) ({t})")
    lines.append("")

    # 逐个知识点
    lines.append("---")
    lines.append("")

    for item in items:
        lines.extend(_render_knowledge_item(item))
        lines.append("")

    # 写入文件
    content = "\n".join(lines)
    md_path.write_text(content, encoding="utf-8")

    logger.info("已导出 Markdown: %s (%d 个知识点, %d 字)", md_path, len(items), len(content))
    return md_path


def write_json(
    items: list[KnowledgeItem],
    doc_title: str,
    output_dir: str | Path,
    source_context: str = "",
) -> Path:
    """将知识点列表导出为 JSON 文件。

    Args:
        items: 知识点列表
        doc_title: 文档标题
        output_dir: 输出目录
        source_context: 案例来源场景

    Returns:
        生成的 JSON 文件路径。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tz_cn = timezone(timedelta(hours=8))
    now = datetime.now(tz_cn)

    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in doc_title)
    json_path = output_dir / f"{safe_name}_知识点.json"

    data = {
        "title": doc_title,
        "extracted_at": now.isoformat(),
        "source_context": source_context,
        "total_count": len(items),
        "knowledge_items": [_item_to_export_dict(item) for item in items],
    }

    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("已导出 JSON: %s (%d 个知识点)", json_path, len(items))
    return json_path


# ── 内部函数 ──────────────────────────────────────────────


def _render_knowledge_item(item: KnowledgeItem) -> list[str]:
    """渲染单个知识点为 Markdown 段落。"""
    lines: list[str] = []

    t = TYPE_DISPLAY_MAP.get(item.type, item.type)
    badge = DIFFICULTY_BADGE.get(item.difficulty, item.difficulty)

    # 标题行
    lines.append(f"### <a id=\"{_slugify(item.id)}\"></a>{item.id} — {item.title}")
    lines.append("")

    # 元信息行
    meta_parts = [f"**类型**：{t}", f"**难度**：{badge}"]
    if item.source_chapter:
        meta_parts.append(f"**来源**：{item.source_chapter}")
    lines.append(" | ".join(meta_parts))
    lines.append("")

    # 痛点标签
    if item.pain_tags:
        tags = " ".join(f"`{tag}`" for tag in item.pain_tags)
        lines.append(f"**痛点标签**：{tags}")
        lines.append("")

    # 核心内容
    lines.append("**核心内容**")
    lines.append("")
    lines.append(item.content)
    lines.append("")

    # 关键要点
    if item.key_points:
        lines.append("**关键要点**")
        lines.append("")
        for kp in item.key_points:
            lines.append(f"- {kp}")
        lines.append("")

    # 适用场景
    if item.applicable_scenario:
        lines.append(f"**适用场景**：{item.applicable_scenario}")
        lines.append("")

    # 原文摘录（折叠）
    if item.original_excerpt:
        lines.append("<details>")
        lines.append("<summary>原文摘录</summary>")
        lines.append("")
        lines.append(f"> {item.original_excerpt}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("---")
    return lines


def _item_to_export_dict(item: KnowledgeItem) -> dict[str, Any]:
    """将 KnowledgeItem 转为导出用字典（带中文字段名）。"""
    return {
        "知识点ID": item.id,
        "来源": item.source_chapter,
        "标题": item.title,
        "类型": TYPE_DISPLAY_MAP.get(item.type, item.type),
        "核心内容": item.content,
        "关键要点": item.key_points,
        "适用场景": item.applicable_scenario,
        "痛点标签": item.pain_tags,
        "难度等级": item.difficulty,
        "原文摘录": item.original_excerpt,
    }


def _slugify(text: str) -> str:
    """生成 Markdown 锚点 ID。"""
    return text.lower().replace(" ", "-").replace("_", "-")

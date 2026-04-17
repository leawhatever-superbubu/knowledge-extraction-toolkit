"""飞书多维表格写入模块 — 将知识点写入 Bitable。

负责将 knowledge_extractor 输出的知识点列表写入飞书多维表格，
支持幂等 upsert（通过知识点ID判重）。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from feishu_client import FeishuClient
from knowledge_extractor import KnowledgeItem

logger = logging.getLogger(__name__)

# 飞书 API 调用间隔
API_CALL_INTERVAL = 0.4  # 秒

# 多维表格字段名映射（与 SKILL_SPEC.md §4.1 严格一致）
DEFAULT_FIELD_MAP = {
    "id": "知识点ID",
    "source_doc": "来源文档",
    "source_chapter": "来源章节",
    "title": "知识点标题",
    "type": "知识点类型",
    "content": "核心内容",
    "key_points": "关键要点",
    "applicable_scenario": "适用场景",
    "pain_tags": "痛点标签",
    "difficulty": "难度等级",
    "original_excerpt": "原文摘录",
    "status": "处理状态",
    "social_copy_status": "社交文案状态",
}

# 知识点类型中英文映射（飞书单选字段用中文显示）
TYPE_DISPLAY_MAP = {
    "concept": "概念解释",
    "how_to": "操作方法",
    "pitfall": "避坑提醒",
    "data_insight": "数据洞察",
    "trend": "行业趋势",
    "tool_tip": "工具技巧",
}


def build_record_fields(
    item: KnowledgeItem,
    doc_title: str,
    field_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """将 KnowledgeItem 转换为飞书多维表格的 fields 字典。

    Args:
        item: 知识点对象
        doc_title: 来源文档标题
        field_map: 字段名映射，默认使用 DEFAULT_FIELD_MAP

    Returns:
        可直接传给 FeishuClient.create_record() 的 fields 字典。
    """
    fm = field_map or DEFAULT_FIELD_MAP

    fields: dict[str, Any] = {
        fm["id"]: item.id,
        fm["source_doc"]: doc_title,
        fm["source_chapter"]: item.source_chapter,
        fm["title"]: item.title,
        fm["type"]: TYPE_DISPLAY_MAP.get(item.type, item.type),
        fm["content"]: item.content,
        fm["key_points"]: "\n".join(f"- {p}" for p in item.key_points),
        fm["applicable_scenario"]: item.applicable_scenario,
        fm["pain_tags"]: item.pain_tags,  # 多选字段，传 list
        fm["difficulty"]: item.difficulty,
        fm["original_excerpt"]: _truncate(item.original_excerpt, 2000),
        fm["status"]: "待审核",
        fm["social_copy_status"]: "未生成",
    }

    return fields


def write_knowledge_to_bitable(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    items: list[KnowledgeItem],
    doc_title: str,
    field_map: dict[str, str] | None = None,
    upsert: bool = True,
) -> dict[str, Any]:
    """将知识点列表写入飞书多维表格。

    Args:
        client: 飞书 API 客户端
        app_token: 多维表格 app_token
        table_id: 数据表 ID
        items: 知识点列表
        doc_title: 来源文档标题
        field_map: 字段名映射
        upsert: 是否启用幂等模式（按知识点ID查重，存在则更新）

    Returns:
        写入结果汇总：{"created": int, "updated": int, "failed": int, "details": list}
    """
    fm = field_map or DEFAULT_FIELD_MAP
    result = {"created": 0, "updated": 0, "failed": 0, "details": []}

    # 如果启用 upsert，先查询已存在的知识点ID
    existing_map: dict[str, str] = {}  # knowledge_id -> record_id
    max_seq = 0  # 当前最大序号，用于给新记录自动编号
    if upsert:
        existing_map, max_seq = _load_existing_records_with_seq(client, app_token, table_id, fm)
        logger.info("已有 %d 条记录（用于去重判断），最大序号 %d", len(existing_map), max_seq)
    else:
        # 非 upsert 模式也需要知道最大序号
        try:
            _, max_seq = _load_existing_records_with_seq(client, app_token, table_id, fm)
        except Exception:
            max_seq = 0

    next_seq = max_seq + 1  # 下一个可用序号

    # 逐条写入
    for item in items:
        fields = build_record_fields(item, doc_title, fm)
        detail = {"knowledge_id": item.id, "title": item.title, "action": "", "error": None}

        try:
            if upsert and item.id in existing_map:
                # 已存在 → 更新（不更新序号）
                record_id = existing_map[item.id]
                time.sleep(API_CALL_INTERVAL)
                client.update_record(app_token, table_id, record_id, fields)
                detail["action"] = "updated"
                result["updated"] += 1
                logger.info("已更新: %s (%s)", item.id, item.title)
            else:
                # 不存在 → 创建，自动分配序号
                fields["序号"] = f"{next_seq:04d}"
                next_seq += 1
                time.sleep(API_CALL_INTERVAL)
                client.create_record(app_token, table_id, fields)
                detail["action"] = "created"
                result["created"] += 1
                logger.info("已创建: %s (%s) [序号 %s]", item.id, item.title, fields["序号"])

        except Exception as e:
            detail["action"] = "failed"
            detail["error"] = str(e)
            result["failed"] += 1
            logger.error("写入失败: %s (%s) — %s", item.id, item.title, e)

        result["details"].append(detail)

    logger.info(
        "写入完成: 创建 %d, 更新 %d, 失败 %d (共 %d)",
        result["created"], result["updated"], result["failed"], len(items),
    )
    return result


def _load_existing_records_with_seq(
    client: FeishuClient,
    app_token: str,
    table_id: str,
    field_map: dict[str, str],
) -> tuple[dict[str, str], int]:
    """查询多维表格中已有的知识点ID → record_id 映射，以及最大序号。

    Returns:
        (mapping, max_seq): mapping 是 knowledge_id -> record_id，max_seq 是当前最大序号。
    """
    try:
        records = client.list_records(app_token, table_id)
    except Exception as e:
        logger.warning("查询已有记录失败: %s — 将以全量新增模式写入", e)
        return {}, 0

    id_field_name = field_map.get("id", "知识点ID")
    mapping = {}
    max_seq = 0

    for record in records:
        fields = record.get("fields", {})
        kid = _extract_text_value(fields.get(id_field_name))
        if kid:
            mapping[kid] = record["record_id"]
        # 获取当前最大序号
        seq_val = _extract_text_value(fields.get("序号"))
        if seq_val:
            try:
                seq_num = int(seq_val)
                if seq_num > max_seq:
                    max_seq = seq_num
            except ValueError:
                pass

    return mapping, max_seq


def _extract_text_value(value: Any) -> str:
    """从飞书多维表格的字段值中提取纯文本。

    字段值可能是：字符串、富文本数组、None。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    return str(value).strip()


def _truncate(text: str, max_len: int) -> str:
    """截断过长的文本。"""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."

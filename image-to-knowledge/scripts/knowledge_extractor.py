"""AI 知识点提取模块 — image-to-knowledge 核心。

使用 LLM 对 Vision AI 分析后的图片描述文本进行知识点提取，
然后执行全局去重、补充和编号后处理。

与 doc-to-knowledge 版本共享相同的 KnowledgeItem 数据结构和输出格式，
但 Prompt 策略针对图片案例素材做了专门设计。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from vision_analyzer import VisionAnalysis

logger = logging.getLogger(__name__)

# ── 预定义闭集标签 ──────────────────────────────────────

VALID_KNOWLEDGE_TYPES = {
    "concept", "how_to", "pitfall", "data_insight", "trend", "tool_tip",
}

VALID_PAIN_TAGS = [
    "预算有限", "缺乏经验", "人手不足", "获客困难",
    "转化率低", "不懂数据", "素材匮乏", "复购难",
]

VALID_DIFFICULTY_LEVELS = {"入门", "进阶", "高级"}


# ── 数据结构（与 doc-to-knowledge 完全一致）────────────────

@dataclass
class KnowledgeItem:
    """一个独立的知识点。"""
    id: str = ""
    source_chapter: str = ""  # 这里复用为 source_image（图片名称）
    title: str = ""
    type: str = "how_to"
    content: str = ""
    key_points: list[str] = field(default_factory=list)
    applicable_scenario: str = ""
    pain_tags: list[str] = field(default_factory=list)
    difficulty: str = "入门"
    original_excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> list[str]:
        """验证知识点字段合规性，返回问题列表。"""
        issues = []
        if not self.title:
            issues.append("缺少标题")
        elif len(self.title) > 20:
            issues.append(f"标题过长 ({len(self.title)} 字，建议 ≤15)")
        if self.type not in VALID_KNOWLEDGE_TYPES:
            issues.append(f"无效的知识点类型: {self.type}")
        if not self.content:
            issues.append("缺少核心内容")
        if not self.key_points:
            issues.append("缺少关键要点")
        if self.difficulty not in VALID_DIFFICULTY_LEVELS:
            issues.append(f"无效的难度等级: {self.difficulty}")
        # 痛点标签必须来自闭集
        invalid_tags = [t for t in self.pain_tags if t not in VALID_PAIN_TAGS]
        if invalid_tags:
            issues.append(f"无效的痛点标签: {invalid_tags}")
        return issues


# ── 图片案例专用 Prompt 构建函数 ──────────────────────────
#
# 所有 Prompt 均为函数动态构建，通过 source_context 参数注入场景上下文。
# source_context 示例："微信小店商家使用小店广告（腾讯广告-小店版）"
# 如果 source_context 为空，则退化为原有的泛化 Prompt。


def build_system_prompt(source_context: str = "") -> str:
    """构建 Image Case System Prompt。"""
    scene_block = ""
    if source_context:
        scene_block = f"""
【案例来源场景】
本批次所有案例图片来自：{source_context}
你在提取每个知识点时，必须在 content（核心内容）和 applicable_scenario（适用场景）中明确标注该操作经验来源于上述场景，让读者清楚知道"这是在哪个平台/工具上的实操经验"。
"""

    return f"""你是一位「腾讯营销」领域的资深内容策略师，专门服务中小客商家 (SMB)。

你的任务是从**营销案例图片的分析结果**中提取知识点。图片已经过 Vision AI 分析，你收到的是结构化的文本描述。你必须始终站在以下目标受众的视角来提取和重写：

【目标受众画像】
- 身份：月预算 5 千~5 万的中小商家、个体创业者、小型电商卖家
- 痛点：预算有限、缺乏投放经验、没有专业团队、获客成本高、不懂数据分析
- 认知水平：了解基础互联网营销概念，但对腾讯营销平台的高级功能不熟悉
- 需求：可直接落地的方法论，而非宏观策略
{scene_block}
【提取原则】
1. 案例翻译：原始案例可能来自大客户/品牌商家，你必须将策略和方法"翻译"为中小客也能执行的版本
2. 可操作性优先：优先提取"怎么做"类知识点（how_to），而非"是什么"类概念
3. 数据驱动：案例中的具体数据（ROI、GMV、转化率等）是最有说服力的证据，务必在知识点中引用
4. 去术语化：将行业黑话替换为通俗表达，必要时加括号注释
5. 强调 ROI：中小客最关心投入产出比，每个知识点尽量关联到"花多少钱能带来什么效果"
6. 独立完整：每个知识点必须独立成文，不依赖其他知识点也能被读者理解
7. 适度颗粒度：一个案例图片通常提取 3-6 个知识点，不要拆得太碎也不要太粗
8. 场景标注：如果已知案例来源场景，必须在每个知识点的 content 和 applicable_scenario 中明确注明"""


def build_extraction_prompt(
    image_name: str,
    image_type: str,
    analysis_text: str,
    source_context: str = "",
) -> str:
    """构建逐图提取 User Prompt。"""
    scene_hint = ""
    if source_context:
        scene_hint = f"""
【案例来源场景】：{source_context}
（请在 content 和 applicable_scenario 中明确标注上述来源场景，例如"在{source_context}的实操中…"）
"""

    return f"""请从以下案例图片的分析结果中提取知识点。

【图片名称】：{image_name}
【图片类型】：{image_type}
{scene_hint}【分析内容】：
---
{analysis_text}
---

请提取该案例中所有对中小客商家有价值的知识点，每个知识点按如下 JSON 格式输出：

{{{{
  "title": "15字以内的精炼标题",
  "type": "concept | how_to | pitfall | data_insight | trend | tool_tip",
  "content": "200-500字的完整知识点描述，用中小客能理解的语言重写。务必引用案例中的具体数据作为支撑。{('必须明确标注该经验来自' + source_context + '的实操') if source_context else ''}",
  "key_points": ["要点1", "要点2", "要点3"],
  "applicable_scenario": "这个知识点最适合什么场景下使用（具体到商家类型+平台/工具+预算范围+投放目标）{('，需注明适用于' + source_context) if source_context else ''}",
  "pain_tags": ["从以下选择：预算有限/缺乏经验/人手不足/获客困难/转化率低/不懂数据/素材匮乏/复购难"],
  "difficulty": "入门 | 进阶 | 高级",
  "original_excerpt": "从分析结果中摘录支撑这个知识点的关键信息（原文，不改写）"
}}}}

要求：
1. 每张案例图片提取 3-6 个知识点
2. 跳过与中小客无关的内容（如：仅适用于年预算百万以上的策略）
3. 如果案例数据模糊或信息量不足以形成独立知识点，跳过即可
4. 优先提取可复制的具体操作方法，而非泛泛的策略方向
5. 输出一个 JSON 数组，包含所有知识点
6. 只输出 JSON 数组，不要附加其他解释文字"""


def build_post_process_prompt(
    batch_name: str,
    all_knowledge_items_json: str,
    valid_pain_tags: str,
    source_context: str = "",
) -> str:
    """构建全局后处理 User Prompt。"""
    scene_hint = ""
    if source_context:
        scene_hint = f"\n6. 场景一致性检查：确保每个知识点的 content 和 applicable_scenario 中都明确标注了来源场景（{source_context}）"

    return f"""你刚才从多张营销案例图片中分别提取了知识点，现在需要做全局后处理。

【批次名称】：{batch_name}
【所有已提取的知识点】：
{all_knowledge_items_json}

请执行以下操作：
1. 去重：合并内容高度相似的知识点（比如多个案例都提到"LBS定向"或"相似人群扩展"，保留最完整的版本）
2. 补充：检查是否有跨案例的知识点被遗漏（某些洞察需要结合多个案例才能看出，如行业共性策略）
3. 编号：按 IMG_{batch_name}_K{{{{01,02,...}}}} 格式统一编号，赋值到每个知识点的 "id" 字段
4. 质量检查：确保每个知识点都满足"独立完整、面向中小客、可操作"的标准
5. 痛点标签必须从以下闭集中选择：{valid_pain_tags}{scene_hint}

输出最终的去重、补充、编号后的知识点 JSON 数组。
只输出 JSON 数组，不要附加其他解释文字。"""


# ── 核心提取函数 ─────────────────────────────────────────

def extract_knowledge_from_analysis(
    ai_client: Any,
    analysis: VisionAnalysis,
    model: str = "gemini-2.5-flash",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    source_context: str = "",
) -> list[KnowledgeItem]:
    """对单张图片的 Vision 分析结果提取知识点。

    Args:
        ai_client: AI 客户端（兼容接口）
        analysis: Vision AI 分析结果
        model: 使用的模型
        temperature: 采样温度
        max_tokens: 最大输出 token 数
        source_context: 案例来源场景（如"微信小店商家使用小店广告"）

    Returns:
        从该图片提取的知识点列表。
    """
    if not analysis.is_valid:
        logger.warning("图片 '%s' 的 Vision 分析结果不足，跳过", analysis.image_name)
        return []

    system_prompt = build_system_prompt(source_context)
    user_prompt = build_extraction_prompt(
        image_name=analysis.image_name,
        image_type=analysis.image_type,
        analysis_text=analysis.structured_text,
        source_context=source_context,
    )

    logger.info(
        "正在从图片 '%s' 的分析结果中提取知识点 (%d 字)...%s",
        analysis.image_name, len(analysis.structured_text),
        f" [场景: {source_context}]" if source_context else "",
    )

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = ai_client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            raw_output = response.choices[0].message.content or ""
            logger.info("AI 原始输出长度: %d 字符", len(raw_output))
            items = _parse_knowledge_json(raw_output, analysis.image_name)

            if items:
                # 标记来源图片
                for item in items:
                    item.source_chapter = analysis.image_name
                logger.info(
                    "图片 '%s' 提取了 %d 个知识点",
                    analysis.image_name, len(items),
                )
                return items

            if attempt < max_retries:
                logger.warning(
                    "图片 '%s' 第 %d 次尝试未解析到知识点，重试...",
                    analysis.image_name, attempt + 1,
                )
                import time
                time.sleep(2)
                continue

            logger.warning("图片 '%s' 所有重试均未解析到知识点", analysis.image_name)
            return []

        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    "图片 '%s' 第 %d 次尝试失败: %s，重试...",
                    analysis.image_name, attempt + 1, e,
                )
                import time
                time.sleep(2)
                continue
            logger.error("图片 '%s' 提取失败: %s", analysis.image_name, e)
            return []

    return []


def post_process_knowledge(
    ai_client: Any,
    batch_name: str,
    all_items: list[KnowledgeItem],
    model: str = "gemini-2.5-flash",
    temperature: float = 0.3,
    max_tokens: int = 16384,
    source_context: str = "",
) -> list[KnowledgeItem]:
    """全局后处理：去重、补充、编号、质检。

    当知识点数量 > 40 时，跳过 AI 后处理（避免输出截断），
    改为本地去重 + 编号。
    """
    if not all_items:
        logger.warning("无知识点需要后处理")
        return []

    MAX_FOR_AI_POST_PROCESS = 40
    if len(all_items) > MAX_FOR_AI_POST_PROCESS:
        logger.warning(
            "知识点数量 %d 超过 AI 后处理上限 %d，使用本地去重+编号",
            len(all_items), MAX_FOR_AI_POST_PROCESS,
        )
        return _local_post_process(all_items, batch_name)

    # 序列化为 JSON
    items_json = json.dumps(
        [item.to_dict() for item in all_items],
        ensure_ascii=False,
        indent=2,
    )

    system_prompt = build_system_prompt(source_context)
    user_prompt = build_post_process_prompt(
        batch_name=batch_name,
        all_knowledge_items_json=items_json,
        valid_pain_tags="、".join(VALID_PAIN_TAGS),
        source_context=source_context,
    )

    logger.info("开始全局后处理: %d 个原始知识点", len(all_items))

    try:
        response = ai_client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw_output = response.choices[0].message.content or ""
        items = _parse_knowledge_json(raw_output, "全局后处理")

        if not items:
            logger.warning("AI 后处理未返回有效结果，使用本地后处理")
            return _local_post_process(all_items, batch_name)

        # 验证每个知识点
        valid_items = []
        for item in items:
            issues = item.validate()
            if issues:
                logger.warning("知识点 '%s' 存在问题: %s — 尝试自动修复", item.title, issues)
                item = _auto_fix_item(item)
            valid_items.append(item)

        logger.info("后处理完成: %d → %d 个知识点", len(all_items), len(valid_items))
        return valid_items

    except Exception as e:
        logger.error("全局后处理失败: %s — 使用本地后处理", e)
        return _local_post_process(all_items, batch_name)


def extract_all_knowledge(
    ai_client: Any,
    analyses: list[VisionAnalysis],
    config: dict[str, Any] | None = None,
    source_context: str = "",
) -> list[KnowledgeItem]:
    """端到端提取：逐图提取 + 全局后处理。

    这是 knowledge_extractor 的主入口函数。

    Args:
        ai_client: AI 客户端
        analyses: Vision 分析结果列表
        config: 提取配置（来自 config.json）
        source_context: 案例来源场景（如"微信小店商家使用小店广告"）

    Returns:
        最终的知识点列表（已去重、编号）。
    """
    config = config or {}
    ai_config = config.get("ai", {})
    extraction_config = config.get("extraction", {})

    model = ai_config.get("model", "gemini-2.5-flash")
    temperature = ai_config.get("temperature", 0.3)
    max_tokens = ai_config.get("max_tokens_per_request", 8192)

    max_per_image = extraction_config.get("max_knowledge_per_image", 8)

    # source_context 优先级：函数参数 > config 配置
    if not source_context:
        source_context = extraction_config.get("source_context", "")

    if source_context:
        logger.info("场景上下文: %s", source_context)

    # 收集批次名称
    batch_name = "案例图片"
    if analyses:
        # 使用第一张图片名的前缀作为批次名
        first_name = analyses[0].image_name
        if "_" in first_name:
            batch_name = first_name.rsplit("_", 1)[0]
        else:
            batch_name = first_name

    # Step 1: 逐图提取
    all_raw_items: list[KnowledgeItem] = []

    for analysis in analyses:
        if not analysis.is_valid:
            logger.warning("跳过无效的 Vision 分析: %s", analysis.image_name)
            continue

        items = extract_knowledge_from_analysis(
            ai_client=ai_client,
            analysis=analysis,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            source_context=source_context,
        )

        # 限制每图最大知识点数
        if len(items) > max_per_image:
            logger.warning(
                "图片 '%s' 提取了 %d 个知识点，超出上限 %d，截取前 %d 个",
                analysis.image_name, len(items), max_per_image, max_per_image,
            )
            items = items[:max_per_image]

        all_raw_items.extend(items)

    logger.info("逐图提取完成: 共 %d 个原始知识点", len(all_raw_items))

    if not all_raw_items:
        logger.warning("未提取到任何知识点")
        return []

    # Step 2: 全局后处理（去重、补充、编号）
    final_items = post_process_knowledge(
        ai_client=ai_client,
        batch_name=batch_name,
        all_items=all_raw_items,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens * 2,
        source_context=source_context,
    )

    # 最终兜底：确保所有知识点都有 ID
    for i, item in enumerate(final_items):
        if not item.id:
            item.id = f"IMG_{batch_name}_K{i + 1:02d}"

    return final_items


# ── 内部工具函数 ─────────────────────────────────────────

def _local_post_process(
    all_items: list[KnowledgeItem],
    batch_name: str,
) -> list[KnowledgeItem]:
    """本地后处理：去重（按标题）、编号、质检。"""
    # 1. 按标题去重
    seen_titles: set[str] = set()
    unique_items: list[KnowledgeItem] = []
    for item in all_items:
        title_key = item.title.strip().lower()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_items.append(item)

    # 2. 编号
    for i, item in enumerate(unique_items, 1):
        item.id = f"IMG_{batch_name}_K{i:02d}"

    # 3. 自动修复
    for item in unique_items:
        issues = item.validate()
        if issues:
            _auto_fix_item(item)

    logger.info(
        "本地后处理完成: %d → %d 个知识点（去重 %d 个）",
        len(all_items), len(unique_items), len(all_items) - len(unique_items),
    )
    return unique_items


def _parse_knowledge_json(raw_output: str, context: str) -> list[KnowledgeItem]:
    """从 AI 输出中解析知识点 JSON 数组。"""
    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("[%s] JSON 解析失败 (%s)，尝试提取 JSON 数组...", context, e)
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.error("[%s] 二次 JSON 解析也失败，放弃该段输出", context)
                return []
        else:
            logger.error("[%s] 未找到 JSON 数组，放弃该段输出", context)
            return []

    if not isinstance(data, list):
        logger.error("[%s] 输出不是 JSON 数组，而是 %s", context, type(data).__name__)
        return []

    items = []
    for raw_item in data:
        if not isinstance(raw_item, dict):
            continue
        try:
            item = KnowledgeItem(
                id=raw_item.get("id", ""),
                source_chapter=raw_item.get("source_chapter", ""),
                title=raw_item.get("title", ""),
                type=raw_item.get("type", "how_to"),
                content=raw_item.get("content", ""),
                key_points=raw_item.get("key_points", []),
                applicable_scenario=raw_item.get("applicable_scenario", ""),
                pain_tags=raw_item.get("pain_tags", []),
                difficulty=raw_item.get("difficulty", "入门"),
                original_excerpt=raw_item.get("original_excerpt", ""),
            )
            items.append(item)
        except Exception as e:
            logger.warning("[%s] 解析单个知识点失败: %s", context, e)

    return items


def _auto_fix_item(item: KnowledgeItem) -> KnowledgeItem:
    """自动修复知识点的常见问题。"""
    if item.type not in VALID_KNOWLEDGE_TYPES:
        item.type = "how_to"

    if item.difficulty not in VALID_DIFFICULTY_LEVELS:
        item.difficulty = "入门"

    item.pain_tags = [t for t in item.pain_tags if t in VALID_PAIN_TAGS]
    if not item.pain_tags:
        item.pain_tags = ["缺乏经验"]

    if not item.key_points:
        sentences = re.split(r"[。！？]", item.content)
        item.key_points = [s.strip() for s in sentences[:3] if s.strip()]

    return item

"""AI 知识点提取模块 — doc-to-knowledge 核心。

使用 LLM（OpenAI 兼容接口）对飞书文档的每个章节进行知识点提取，
然后执行全局去重、补充和编号后处理。

所有 Prompt 策略严格遵循 SKILL_SPEC.md §5 的定义。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from openai import OpenAI

from doc_reader import Chapter, DocumentContent

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


# ── 数据结构 ─────────────────────────────────────────────

@dataclass
class KnowledgeItem:
    """一个独立的知识点。"""
    id: str = ""
    source_chapter: str = ""
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


# ── System Prompt ────────────────────────────────────────

SYSTEM_PROMPT = """你是一位数字营销领域的资深内容策略师，专门服务中小客商家 (SMB)。

你的任务是从视频课程转录稿中提取知识点。你必须始终站在以下目标受众的视角来提取和重写：

【目标受众画像】
- 身份：月预算 5 千~5 万的中小商家、个体创业者、小型电商卖家
- 痛点：预算有限、缺乏投放经验、没有专业团队、获客成本高、不懂数据分析
- 认知水平：了解基础互联网营销概念，但对广告投放平台的高级功能不熟悉
- 需求：可直接落地的方法论，而非宏观策略

【提取原则】
1. 翻译视角：原始转录稿可能是面向大客户/品牌的视角，你必须将其"翻译"为中小客能理解、能执行的语言
2. 可操作性优先：优先提取"怎么做"类知识点，而非"是什么"类概念
3. 去术语化：将行业黑话替换为通俗表达，必要时加括号注释
4. 强调 ROI：中小客最关心投入产出比，每个知识点尽量关联到"花多少钱能带来什么效果"
5. 独立完整：每个知识点必须独立成文，不依赖其他知识点也能被读者理解
6. 拆到原子级：一个知识点只讲一件事，宁可多拆也不要混杂多个主题"""


# ── User Prompt 模板：逐章提取 ───────────────────────────

CHAPTER_EXTRACTION_PROMPT = """请从以下课程转录稿章节中提取知识点。

【文档标题】：{doc_title}
【章节标题】：{chapter_title}
【章节内容】：
---
{chapter_content}
---

请提取该章节中所有对中小客商家有价值的知识点，每个知识点按如下 JSON 格式输出：

{{
  "title": "15字以内的精炼标题",
  "type": "concept | how_to | pitfall | data_insight | trend | tool_tip",
  "content": "200-500字的完整知识点描述，用中小客能理解的语言重写",
  "key_points": ["要点1", "要点2", "要点3"],
  "applicable_scenario": "这个知识点最适合什么场景下使用",
  "pain_tags": ["从以下选择：预算有限/缺乏经验/人手不足/获客困难/转化率低/不懂数据/素材匮乏/复购难"],
  "difficulty": "入门 | 进阶 | 高级",
  "original_excerpt": "从原文中摘录支撑这个知识点的关键段落（原文，不改写）"
}}

要求：
1. 尽量多拆解，一个段落可能包含多个独立知识点
2. 跳过与中小客无关的内容（如：仅适用于年预算百万以上的策略）
3. 如果某段内容含糊不清或信息量不足以形成独立知识点，跳过即可
4. 输出一个 JSON 数组，包含该章节所有知识点
5. 只输出 JSON 数组，不要附加其他解释文字"""


# ── User Prompt 模板：全局后处理 ─────────────────────────

POST_PROCESS_PROMPT = """你刚才从同一课程的多个章节中分别提取了知识点，现在需要做全局后处理。

【文档标题】：{doc_title}
【所有已提取的知识点】：
{all_knowledge_items_json}

请执行以下操作：
1. 去重：合并内容高度相似的知识点（保留更完整的版本）
2. 补充：检查是否有跨章节的知识点被遗漏（某些洞察需要结合多个章节才能看出）
3. 编号：按 {doc_title}_K{{01,02,...}} 格式统一编号，赋值到每个知识点的 "id" 字段
4. 质量检查：确保每个知识点都满足"独立完整、面向中小客、可操作"的标准
5. 痛点标签必须从以下闭集中选择：{valid_pain_tags}

输出最终的去重、补充、编号后的知识点 JSON 数组。
只输出 JSON 数组，不要附加其他解释文字。"""


# ── Playbook 专用 Prompt（SMB 操作级知识点提取）────────────

PLAYBOOK_SYSTEM_PROMPT = """你是一位数字营销领域的资深内容策略师，专门服务中小客商家 (SMB)。

你的任务是从已编写完成的 **SMB Playbook 实操卡片** 中提取知识点。这些卡片已经是面向中小客的成品内容，你需要从中提取可直接入库的结构化知识点。

【目标受众画像】
- 身份：月预算 5 千~5 万的中小商家、个体创业者、小型电商卖家
- 痛点：预算有限、缺乏投放经验、没有专业团队、获客成本高、不懂数据分析
- 认知水平：了解基础互联网营销概念，但对广告平台的高级功能不熟悉
- 需求：可直接落地的方法论，而非宏观策略

【提取原则】
1. **操作级颗粒度**：每个 Action 对应一个知识点，避坑指南和效果衡量各可合并为一个知识点。目标是每张卡片 3-5 个知识点
2. 不要拆得太碎：一个 Action 就是一个完整的操作方法，不要再继续往下拆
3. 可操作性优先：优先提取"怎么做"类知识点（how_to），避坑类用 pitfall
4. 独立完整：每个知识点必须独立成文，不依赖其他知识点也能被读者理解
5. 保持原有语言风格：卡片本身已经是口语化的 SMB 友好表达，不需要再"翻译"
6. 强调 ROI：每个知识点尽量关联到投入产出比"""


PLAYBOOK_EXTRACTION_PROMPT = """请从以下 SMB Playbook 实操卡片中提取知识点。

【卡片标题】：{doc_title}
【卡片来源】：{chapter_title}
【卡片正文】：
---
{chapter_content}
---

请按以下规则提取：
1. 每个 **Action** 提取为 1 个独立的 how_to 类型知识点
2. **避坑指南** 提取为 1 个 pitfall 类型知识点（如果内容足够丰富）
3. **效果怎么看** 可提取为 1 个 data_insight 类型知识点（如果包含具体指标阈值）
4. 每张卡片总共 3-5 个知识点，不要更多

每个知识点按如下 JSON 格式输出：

{{
  "title": "15字以内的精炼标题",
  "type": "how_to | pitfall | data_insight | tool_tip",
  "content": "200-400字的完整知识点描述，保持卡片原有的口语化风格",
  "key_points": ["要点1", "要点2", "要点3"],
  "applicable_scenario": "这个知识点最适合什么场景下使用",
  "pain_tags": ["从以下选择：预算有限/缺乏经验/人手不足/获客困难/转化率低/不懂数据/素材匮乏/复购难"],
  "difficulty": "入门 | 进阶 | 高级",
  "original_excerpt": "从卡片原文中摘录支撑这个知识点的关键段落（原文，不改写）"
}}

要求：
1. 输出一个 JSON 数组
2. 只输出 JSON 数组，不要附加其他解释文字
3. 不要把"痛点场景"和"大盘启示"单独拆成知识点，它们是背景信息"""


PLAYBOOK_POST_PROCESS_PROMPT = """你刚才从多张 SMB Playbook 实操卡片中分别提取了知识点，现在需要做全局后处理。

【所有已提取的知识点】：
{all_knowledge_items_json}

请执行以下操作：
1. 去重：合并内容高度相似的知识点（比如多张卡片都提到"LBS定向"，保留最完整的版本）
2. 补充：检查是否有跨卡片的知识点被遗漏
3. 编号：按 SMB_Playbook_K{{01,02,...}} 格式统一编号，赋值到每个知识点的 "id" 字段
4. 质量检查：确保每个知识点都满足"独立完整、面向中小客、可操作"的标准
5. 痛点标签必须从以下闭集中选择：{valid_pain_tags}

输出最终的去重、补充、编号后的知识点 JSON 数组。
只输出 JSON 数组，不要附加其他解释文字。"""


# ── 核心提取函数 ─────────────────────────────────────────

def extract_knowledge_from_chapter(
    ai_client: OpenAI,
    doc_title: str,
    chapter: Chapter,
    model: str = "gpt-4o",
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> list[KnowledgeItem]:
    """对单个章节调用 AI 提取知识点。

    Args:
        ai_client: OpenAI 客户端（兼容接口）
        doc_title: 文档标题
        chapter: 待提取的章节
        model: 使用的模型
        temperature: 采样温度（低温 = 稳定输出）
        max_tokens: 最大输出 token 数

    Returns:
        从该章节提取的知识点列表。
    """
    if not chapter.content.strip():
        logger.warning("章节 '%s' 内容为空，跳过", chapter.title)
        return []

    user_prompt = CHAPTER_EXTRACTION_PROMPT.format(
        doc_title=doc_title,
        chapter_title=chapter.title,
        chapter_content=chapter.content,
    )

    logger.info("正在提取章节 '%s' 的知识点 (%d 字)...", chapter.title, chapter.word_count)

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = ai_client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )

            raw_output = response.choices[0].message.content or ""
            logger.info("AI 原始输出长度: %d 字符, 前 300 字: %s", len(raw_output), raw_output[:300])
            items = _parse_knowledge_json(raw_output, chapter.title)

            if items:
                logger.info("章节 '%s' 提取了 %d 个知识点", chapter.title, len(items))
                return items

            if attempt < max_retries:
                logger.warning("章节 '%s' 第 %d 次尝试未解析到知识点，重试...", chapter.title, attempt + 1)
                import time
                time.sleep(2)
                continue

            logger.warning("章节 '%s' 所有重试均未解析到知识点", chapter.title)
            return []

        except Exception as e:
            if attempt < max_retries:
                logger.warning("章节 '%s' 第 %d 次尝试失败: %s，重试...", chapter.title, attempt + 1, e)
                import time
                time.sleep(2)
                continue
            logger.error("章节 '%s' 提取失败: %s", chapter.title, e)
            return []

    return []


def post_process_knowledge(
    ai_client: OpenAI,
    doc_title: str,
    all_items: list[KnowledgeItem],
    model: str = "gpt-4o",
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> list[KnowledgeItem]:
    """全局后处理：去重、补充、编号、质检。

    当知识点数量 > 30 时，跳过 AI 后处理（避免输出截断），
    改为本地去重 + 编号。

    Args:
        ai_client: OpenAI 客户端
        doc_title: 文档标题
        all_items: 所有章节提取的原始知识点列表
        model: 使用的模型
        temperature: 采样温度
        max_tokens: 最大输出 token 数

    Returns:
        后处理完成的最终知识点列表。
    """
    if not all_items:
        logger.warning("无知识点需要后处理")
        return []

    # 如果知识点太多，跳过 AI 后处理（避免输出截断）
    MAX_FOR_AI_POST_PROCESS = 30
    if len(all_items) > MAX_FOR_AI_POST_PROCESS:
        logger.warning(
            "知识点数量 %d 超过 AI 后处理上限 %d，使用本地去重+编号",
            len(all_items), MAX_FOR_AI_POST_PROCESS
        )
        return _local_post_process(all_items, doc_title)

    # 序列化为 JSON
    items_json = json.dumps(
        [item.to_dict() for item in all_items],
        ensure_ascii=False,
        indent=2,
    )

    user_prompt = POST_PROCESS_PROMPT.format(
        doc_title=doc_title,
        all_knowledge_items_json=items_json,
        valid_pain_tags="、".join(VALID_PAIN_TAGS),
    )

    logger.info("开始全局后处理: %d 个原始知识点", len(all_items))

    try:
        response = ai_client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw_output = response.choices[0].message.content or ""
        items = _parse_knowledge_json(raw_output, "全局后处理")

        if not items:
            logger.warning("AI 后处理未返回有效结果，使用本地后处理")
            return _local_post_process(all_items, doc_title)

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
        return _local_post_process(all_items, doc_title)


def _local_post_process(all_items: list[KnowledgeItem], doc_title: str) -> list[KnowledgeItem]:
    """本地后处理：去重（按标题）、编号、质检。

    不依赖 AI，适用于知识点数量过多的情况。
    """
    # 1. 按标题去重（保留第一个出现的）
    seen_titles: set[str] = set()
    unique_items: list[KnowledgeItem] = []
    for item in all_items:
        title_key = item.title.strip().lower()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_items.append(item)

    # 2. 编号
    for i, item in enumerate(unique_items, 1):
        item.id = f"{doc_title}_K{i:02d}"

    # 3. 自动修复每个知识点
    for item in unique_items:
        issues = item.validate()
        if issues:
            _auto_fix_item(item)

    logger.info("本地后处理完成: %d → %d 个知识点（去重 %d 个）",
                len(all_items), len(unique_items), len(all_items) - len(unique_items))
    return unique_items


def extract_all_knowledge(
    ai_client: OpenAI,
    doc: DocumentContent,
    config: dict[str, Any] | None = None,
) -> list[KnowledgeItem]:
    """端到端提取：逐章提取 + 全局后处理。

    这是 knowledge_extractor 的主入口函数。

    支持两种模式（通过 config["extraction"]["mode"] 切换）：
    - ``"transcript"``（默认）：面向视频课程转录稿，原子级拆解
    - ``"playbook"``：面向 SMB Playbook 卡片，操作级颗粒度（3-5 个/卡片）

    Args:
        ai_client: OpenAI 客户端
        doc: 解析后的文档内容
        config: 提取配置（来自 config.json 的 extraction + ai 部分）

    Returns:
        最终的知识点列表（已去重、编号）。
    """
    config = config or {}
    ai_config = config.get("ai", {})
    extraction_config = config.get("extraction", {})

    model = ai_config.get("model", "gpt-4o")
    temperature = ai_config.get("temperature", 0.3)
    max_tokens = ai_config.get("max_tokens_per_request", 4096)

    max_per_chapter = extraction_config.get("max_knowledge_per_chapter", 10)

    # 判断提取模式
    mode = extraction_config.get("mode", "transcript")
    is_playbook = mode == "playbook"

    if is_playbook:
        logger.info("使用 Playbook 模式提取（操作级颗粒度，3-5 个/卡片）")
        sys_prompt = PLAYBOOK_SYSTEM_PROMPT
        chapter_prompt_tpl = PLAYBOOK_EXTRACTION_PROMPT
        post_prompt_tpl = PLAYBOOK_POST_PROCESS_PROMPT
    else:
        sys_prompt = SYSTEM_PROMPT
        chapter_prompt_tpl = CHAPTER_EXTRACTION_PROMPT
        post_prompt_tpl = POST_PROCESS_PROMPT

    # Step 1: 逐章节提取
    all_raw_items: list[KnowledgeItem] = []

    for chapter in doc.chapters:
        if is_playbook:
            # Playbook 模式：使用专用 Prompt
            items = _extract_playbook_chapter(
                ai_client=ai_client,
                doc_title=doc.doc_title,
                chapter=chapter,
                sys_prompt=sys_prompt,
                chapter_prompt_tpl=chapter_prompt_tpl,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            items = extract_knowledge_from_chapter(
                ai_client=ai_client,
                doc_title=doc.doc_title,
                chapter=chapter,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # 限制每章最大知识点数
        if len(items) > max_per_chapter:
            logger.warning(
                "章节 '%s' 提取了 %d 个知识点，超出上限 %d，截取前 %d 个",
                chapter.title, len(items), max_per_chapter, max_per_chapter,
            )
            items = items[:max_per_chapter]

        # 标记来源章节
        for item in items:
            item.source_chapter = chapter.title

        all_raw_items.extend(items)

    logger.info("逐章提取完成: 共 %d 个原始知识点", len(all_raw_items))

    if not all_raw_items:
        logger.warning("未提取到任何知识点")
        return []

    # Step 2: 全局后处理（去重、补充、编号）
    if is_playbook:
        final_items = _post_process_playbook(
            ai_client=ai_client,
            all_items=all_raw_items,
            post_prompt_tpl=post_prompt_tpl,
            sys_prompt=sys_prompt,
            model=model,
            temperature=temperature,
            max_tokens=ai_config.get("max_tokens_per_request", 4096) * 2,
        )
    else:
        final_items = post_process_knowledge(
            ai_client=ai_client,
            doc_title=doc.doc_title,
            all_items=all_raw_items,
            model=model,
            temperature=temperature,
            max_tokens=ai_config.get("max_tokens_per_request", 4096) * 2,
        )

    # 最终兜底：确保所有知识点都有 ID
    id_prefix = "SMB_Playbook" if is_playbook else doc.doc_title
    for i, item in enumerate(final_items):
        if not item.id:
            item.id = f"{id_prefix}_K{i + 1:02d}"

    return final_items


def _extract_playbook_chapter(
    ai_client: OpenAI,
    doc_title: str,
    chapter: Chapter,
    sys_prompt: str,
    chapter_prompt_tpl: str,
    model: str = "gpt-4o",
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> list[KnowledgeItem]:
    """Playbook 模式：对单张卡片调用 AI 提取知识点。"""
    if not chapter.content.strip():
        logger.warning("章节 '%s' 内容为空，跳过", chapter.title)
        return []

    user_prompt = chapter_prompt_tpl.format(
        doc_title=doc_title,
        chapter_title=chapter.title,
        chapter_content=chapter.content,
    )

    logger.info("正在提取 Playbook 卡片 '%s' 的知识点 (%d 字)...", chapter.title, chapter.word_count)

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = ai_client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            raw_output = response.choices[0].message.content or ""
            logger.info("AI 原始输出长度: %d 字符", len(raw_output))
            items = _parse_knowledge_json(raw_output, chapter.title)

            if items:
                logger.info("卡片 '%s' 提取了 %d 个知识点", chapter.title, len(items))
                return items

            if attempt < max_retries:
                logger.warning("卡片 '%s' 第 %d 次尝试未解析到知识点，重试...", chapter.title, attempt + 1)
                import time
                time.sleep(2)
                continue

            logger.warning("卡片 '%s' 所有重试均未解析到知识点", chapter.title)
            return []

        except Exception as e:
            if attempt < max_retries:
                logger.warning("卡片 '%s' 第 %d 次尝试失败: %s，重试...", chapter.title, attempt + 1, e)
                import time
                time.sleep(2)
                continue
            logger.error("卡片 '%s' 提取失败: %s", chapter.title, e)
            return []

    return []


def _post_process_playbook(
    ai_client: OpenAI,
    all_items: list[KnowledgeItem],
    post_prompt_tpl: str,
    sys_prompt: str,
    model: str = "gpt-4o",
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> list[KnowledgeItem]:
    """Playbook 模式的全局后处理。"""
    if not all_items:
        return []

    # 如果知识点太多，使用本地后处理
    if len(all_items) > 50:
        logger.warning("知识点数量 %d 过多，使用本地后处理", len(all_items))
        return _local_post_process(all_items, "SMB_Playbook")

    items_json = json.dumps(
        [item.to_dict() for item in all_items],
        ensure_ascii=False,
        indent=2,
    )

    user_prompt = post_prompt_tpl.format(
        all_knowledge_items_json=items_json,
        valid_pain_tags="、".join(VALID_PAIN_TAGS),
    )

    logger.info("开始 Playbook 全局后处理: %d 个原始知识点", len(all_items))

    try:
        response = ai_client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw_output = response.choices[0].message.content or ""
        items = _parse_knowledge_json(raw_output, "Playbook全局后处理")

        if not items:
            logger.warning("Playbook 后处理未返回有效结果，使用本地后处理")
            return _local_post_process(all_items, "SMB_Playbook")

        # 验证和修复
        valid_items = []
        for item in items:
            issues = item.validate()
            if issues:
                logger.warning("知识点 '%s' 存在问题: %s — 自动修复", item.title, issues)
                item = _auto_fix_item(item)
            valid_items.append(item)

        logger.info("Playbook 后处理完成: %d → %d 个知识点", len(all_items), len(valid_items))
        return valid_items

    except Exception as e:
        logger.error("Playbook 全局后处理失败: %s — 使用本地后处理", e)
        return _local_post_process(all_items, "SMB_Playbook")


# ── 内部工具函数 ─────────────────────────────────────────

def _parse_knowledge_json(raw_output: str, context: str) -> list[KnowledgeItem]:
    """从 AI 输出中解析知识点 JSON 数组。

    容错处理：
    - 去除 markdown 代码块标记
    - 尝试修复常见 JSON 问题
    """
    # 去除 markdown 代码块包裹
    text = raw_output.strip()
    if text.startswith("```"):
        # 去掉首尾的 ``` 标记
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 尝试解析 JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("[%s] JSON 解析失败 (%s)，尝试提取 JSON 数组...", context, e)
        # 尝试找到 JSON 数组部分
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
    # 修复类型
    if item.type not in VALID_KNOWLEDGE_TYPES:
        item.type = "how_to"  # 默认设为最常用的类型

    # 修复难度
    if item.difficulty not in VALID_DIFFICULTY_LEVELS:
        item.difficulty = "入门"

    # 修复痛点标签 — 过滤掉不在闭集中的标签
    item.pain_tags = [t for t in item.pain_tags if t in VALID_PAIN_TAGS]
    if not item.pain_tags:
        item.pain_tags = ["缺乏经验"]  # 默认标签

    # 修复关键要点
    if not item.key_points:
        # 从 content 中提取前 3 句话作为要点
        sentences = re.split(r"[。！？]", item.content)
        item.key_points = [s.strip() for s in sentences[:3] if s.strip()]

    return item

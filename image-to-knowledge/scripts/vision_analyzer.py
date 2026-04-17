"""Vision AI 图片分析模块 — 将图片转为结构化文本描述。

使用 Gemini Vision 多模态能力分析案例图片，输出结构化的文本描述，
供下游 knowledge_extractor 提取知识点。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from image_preprocessor import ProcessedImage

logger = logging.getLogger(__name__)


# ── Vision 分析结果 ────────────────────────────────────────

@dataclass
class VisionAnalysis:
    """Vision AI 对单张图片的分析结果。"""

    image_name: str  # 图片名称
    image_type: str  # 图片类型（marketing_poster / data_report / chat_record / ppt_slide / other）
    structured_text: str  # 结构化文本描述（用于知识点提取）
    raw_response: str  # AI 原始响应
    confidence: str = "medium"  # high / medium / low

    @property
    def is_valid(self) -> bool:
        """分析结果是否有效（有足够内容用于知识点提取）。"""
        return len(self.structured_text.strip()) >= 50


# ── Vision Prompt 构建函数 ─────────────────────────────────
#
# 支持通过 source_context 注入场景上下文，让 Vision 分析时就感知来源语境。


def build_vision_system_prompt(source_context: str = "") -> str:
    """构建 Vision System Prompt。"""
    scene_block = ""
    if source_context:
        scene_block = f"""

【案例来源场景】
本批次图片来自：{source_context}
在分析时请关注与该场景相关的平台功能、投放工具、运营策略等内容，并在 smb_relevance 中结合该场景给出参考价值分析。"""

    return f"""你是一位「腾讯营销」领域的资深案例分析师，专门从营销案例图片中提取有价值的信息。

你的任务是仔细观察图片内容，输出一份结构化的文本描述，便于后续提取面向中小客商家 (SMB) 的知识点。
{scene_block}
【你需要识别的图片类型】
1. **营销海报/案例卡片** — 通常包含品牌名、案例标题、核心数据（GMV、ROI等）、策略描述
2. **数据报表截图** — 包含数据图表、指标数字、趋势分析
3. **聊天记录/对话截图** — 包含客户反馈、运营沟通、策略讨论
4. **PPT/演示文稿截图** — 包含策略框架、流程图、方法论
5. **广告投放后台截图** — 包含投放数据、账户结构、定向设置
6. **产品页面/落地页截图** — 包含商品信息、页面设计、转化要素

【输出要求】
请按以下 JSON 格式输出分析结果：

{{
  "image_type": "marketing_poster | data_report | chat_record | ppt_slide | ad_backend | landing_page | other",
  "title": "图片内容的简短标题（20字以内）",
  "brand_or_client": "涉及的品牌或客户名称（如有）",
  "industry": "所属行业（如：食品饮料、服装、美妆、教育、本地生活等）",
  "core_data": [
    {{"metric": "指标名称", "value": "具体数值", "context": "数据背景说明"}}
  ],
  "strategies": [
    {{"name": "策略名称", "description": "策略详细描述（尽可能完整）"}}
  ],
  "key_findings": [
    "发现1：具体的可操作洞察",
    "发现2：...",
    "发现3：..."
  ],
  "smb_relevance": "这个案例对月预算5千~5万的中小商家有什么参考价值？",
  "full_text_extraction": "图片中所有可识别的文字内容（原样提取，不改写）",
  "confidence": "high | medium | low"
}}

【注意事项】
1. 尽可能完整地提取图片中的所有文字和数据
2. 如果图片包含多个区域/板块，分别描述每个部分
3. 数字和数据必须精确提取，不要四舍五入或概括
4. 如果看不清某些文字，用 [不清晰] 标注
5. 始终从中小客商家 (SMB) 的视角分析案例价值
6. 只输出 JSON，不要附加其他解释文字"""


def build_vision_user_prompt(image_name: str, source_context: str = "") -> str:
    """构建 Vision User Prompt。"""
    scene_hint = ""
    if source_context:
        scene_hint = f"\n该图片来自「{source_context}」相关案例，请在分析时关注该场景的特定信息。"

    return f"""请分析这张「腾讯营销」相关的案例图片，提取所有有价值的信息。

【图片来源】：{image_name}{scene_hint}

请按照系统指令中的 JSON 格式输出分析结果。确保：
1. 完整提取图片中所有可见的文字内容
2. 精确记录所有数据指标
3. 识别并描述使用的营销策略
4. 评估对中小客商家的参考价值"""


# ── 核心分析函数 ─────────────────────────────────────────

def analyze_image(
    ai_client: Any,
    processed_image: ProcessedImage,
    image_name: str,
    model: str = "gemini-2.5-flash",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    source_context: str = "",
) -> VisionAnalysis:
    """使用 Vision AI 分析单张图片。

    Args:
        ai_client: AI 客户端（GeminiClient 或 OpenAI）
        processed_image: 预处理后的图片数据
        image_name: 图片名称（用于日志和知识点 ID）
        model: 使用的模型
        temperature: 采样温度
        max_tokens: 最大输出 token 数
        source_context: 案例来源场景（如"微信小店商家使用小店广告"）

    Returns:
        VisionAnalysis 包含结构化文本描述。
    """
    logger.info(
        "开始 Vision 分析: %s (%dx%d, %d bytes)%s",
        image_name, processed_image.width, processed_image.height,
        processed_image.processed_size,
        f" [场景: {source_context}]" if source_context else "",
    )

    system_prompt = build_vision_system_prompt(source_context)
    user_prompt = build_vision_user_prompt(image_name, source_context)

    # 构建多模态消息（OpenAI 格式，GeminiClient 会自动转换）
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": processed_image.data_url},
                },
                {
                    "type": "text",
                    "text": user_prompt,
                },
            ],
        },
    ]

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = ai_client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=messages,
            )

            raw_output = response.choices[0].message.content or ""
            logger.info("Vision AI 原始输出长度: %d 字符", len(raw_output))

            # 解析结构化结果
            analysis = _parse_vision_response(raw_output, image_name)

            if analysis.is_valid:
                logger.info(
                    "Vision 分析完成: %s — 类型=%s, 置信度=%s",
                    image_name, analysis.image_type, analysis.confidence,
                )
                return analysis

            if attempt < max_retries:
                logger.warning(
                    "Vision 分析结果不足（%d 字），重试...",
                    len(analysis.structured_text),
                )
                time.sleep(2)
                continue

            logger.warning("Vision 分析结果不足，使用当前结果")
            return analysis

        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    "Vision 分析第 %d 次尝试失败: %s，重试...",
                    attempt + 1, e,
                )
                time.sleep(2)
                continue
            logger.error("Vision 分析失败: %s — %s", image_name, e)
            return VisionAnalysis(
                image_name=image_name,
                image_type="other",
                structured_text="",
                raw_response=str(e),
                confidence="low",
            )

    # 不应到达这里
    return VisionAnalysis(
        image_name=image_name,
        image_type="other",
        structured_text="",
        raw_response="max retries exceeded",
        confidence="low",
    )


def analyze_batch(
    ai_client: Any,
    processed_images: list[tuple[str, ProcessedImage]],
    model: str = "gemini-2.5-flash",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    delay_between: float = 1.0,
    source_context: str = "",
) -> list[VisionAnalysis]:
    """批量分析多张图片。

    Args:
        ai_client: AI 客户端
        processed_images: (image_name, ProcessedImage) 列表
        model: 使用的模型
        temperature: 采样温度
        max_tokens: 最大输出 token 数
        delay_between: 两次 API 调用之间的间隔（秒）
        source_context: 案例来源场景

    Returns:
        VisionAnalysis 列表。
    """
    results: list[VisionAnalysis] = []

    for i, (name, img) in enumerate(processed_images):
        logger.info("批量分析 [%d/%d]: %s", i + 1, len(processed_images), name)

        analysis = analyze_image(
            ai_client=ai_client,
            processed_image=img,
            image_name=name,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            source_context=source_context,
        )
        results.append(analysis)

        # API 调用间隔
        if i < len(processed_images) - 1:
            time.sleep(delay_between)

    valid_count = sum(1 for r in results if r.is_valid)
    logger.info(
        "批量 Vision 分析完成: %d/%d 张有效",
        valid_count, len(results),
    )

    return results


# ── 内部工具函数 ─────────────────────────────────────────

def _parse_vision_response(raw_output: str, image_name: str) -> VisionAnalysis:
    """从 Vision AI 输出中解析结构化分析结果。"""
    import re

    # 去除 markdown 代码块包裹
    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 尝试解析 JSON
    parsed: dict = {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到 JSON 对象部分
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Vision 响应 JSON 解析失败，使用原始文本")

    if parsed:
        # 从 JSON 构建结构化文本
        structured_text = _build_structured_text(parsed)
        return VisionAnalysis(
            image_name=image_name,
            image_type=parsed.get("image_type", "other"),
            structured_text=structured_text,
            raw_response=raw_output,
            confidence=parsed.get("confidence", "medium"),
        )
    else:
        # JSON 解析失败，使用原始文本
        return VisionAnalysis(
            image_name=image_name,
            image_type="other",
            structured_text=raw_output,
            raw_response=raw_output,
            confidence="low",
        )


def _build_structured_text(parsed: dict) -> str:
    """从解析后的 JSON 构建结构化文本（用于知识点提取）。"""
    parts: list[str] = []

    title = parsed.get("title", "")
    if title:
        parts.append(f"【案例标题】{title}")

    brand = parsed.get("brand_or_client", "")
    if brand:
        parts.append(f"【品牌/客户】{brand}")

    industry = parsed.get("industry", "")
    if industry:
        parts.append(f"【行业】{industry}")

    # 核心数据
    core_data = parsed.get("core_data", [])
    if core_data:
        parts.append("【核心数据】")
        for d in core_data:
            metric = d.get("metric", "")
            value = d.get("value", "")
            context = d.get("context", "")
            line = f"- {metric}: {value}"
            if context:
                line += f" ({context})"
            parts.append(line)

    # 策略
    strategies = parsed.get("strategies", [])
    if strategies:
        parts.append("【营销策略】")
        for s in strategies:
            name = s.get("name", "")
            desc = s.get("description", "")
            parts.append(f"- {name}: {desc}")

    # 关键发现
    key_findings = parsed.get("key_findings", [])
    if key_findings:
        parts.append("【关键发现】")
        for f in key_findings:
            parts.append(f"- {f}")

    # SMB 参考价值
    smb_rel = parsed.get("smb_relevance", "")
    if smb_rel:
        parts.append(f"【中小客参考价值】{smb_rel}")

    # 完整文字提取
    full_text = parsed.get("full_text_extraction", "")
    if full_text:
        parts.append(f"【图片原文提取】\n{full_text}")

    return "\n".join(parts)

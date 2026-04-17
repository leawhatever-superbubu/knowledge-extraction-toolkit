"""Gemini 原生 API 客户端 — 扩展版，支持 Vision 多模态调用。

基于 doc-to-knowledge 的 gemini_client.py 扩展，新增：
- Vision API 调用（base64 图片 + text prompt 的多模态输入）
- 兼容纯文本调用（与 OpenAI SDK chat.completions.create 接口兼容）
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class Message:
    role: str = "assistant"
    content: str = ""


@dataclass
class Choice:
    index: int = 0
    message: Message = field(default_factory=Message)
    finish_reason: str = "stop"


@dataclass
class ChatCompletionResponse:
    """兼容 OpenAI ChatCompletion 返回格式。"""
    choices: list[Choice] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""


class GeminiChatCompletions:
    """模拟 openai.OpenAI().chat.completions 接口。"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def create(
        self,
        model: str = "gemini-2.5-flash",
        messages: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatCompletionResponse:
        """调用 Gemini generateContent API，返回兼容 OpenAI 的结果。

        支持纯文本和多模态（图片）消息。
        messages 中的 content 可以是：
        - 字符串（纯文本）
        - 列表（多模态，包含 text 和 image_url 类型的 content parts）
        """
        messages = messages or []

        # 转换 OpenAI messages 格式 → Gemini contents 格式
        system_instruction = None
        contents: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # system prompt 特殊处理
                if isinstance(content, str):
                    system_instruction = content
                else:
                    # 多模态 system prompt — 提取文本部分
                    text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                    system_instruction = "\n".join(text_parts)

            elif role == "user":
                parts = self._convert_content_to_parts(content)
                contents.append({"role": "user", "parts": parts})

            elif role == "assistant":
                if isinstance(content, str):
                    contents.append({
                        "role": "model",
                        "parts": [{"text": content}],
                    })

        # 构建 Gemini 请求体
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        # system instruction 处理：合并到第一个 user message 中
        # （代理网关可能不支持 systemInstruction 字段）
        if system_instruction and contents:
            first_parts = contents[0].get("parts", [])
            # 找到第一个 text part，将 system prompt 前置
            for i, part in enumerate(first_parts):
                if "text" in part:
                    first_parts[i]["text"] = (
                        f"[System Instructions]\n{system_instruction}\n\n"
                        f"[User Request]\n{part['text']}"
                    )
                    break
            else:
                # 没有 text part，插入一个
                first_parts.insert(0, {
                    "text": f"[System Instructions]\n{system_instruction}\n\n[User Request]"
                })

        # 调用 Gemini API
        url = f"{self.base_url}/v1/models/{model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error("Gemini API 调用失败 (HTTP %d): %s", e.code, error_body[:500])
            raise RuntimeError(f"Gemini API 错误 (HTTP {e.code}): {error_body[:200]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Gemini API 网络错误: {e}") from e

        # 解析响应
        candidates = result.get("candidates", [])
        if not candidates:
            error_info = result.get("error", {})
            if error_info:
                raise RuntimeError(f"Gemini API 返回错误: {error_info.get('message', result)}")
            raise RuntimeError(f"Gemini API 返回空响应: {json.dumps(result, ensure_ascii=False)[:300]}")

        # 提取文本
        text_parts = []
        for part in candidates[0].get("content", {}).get("parts", []):
            if "text" in part:
                text_parts.append(part["text"])

        response_text = "".join(text_parts)

        # 提取 token 用量
        usage_meta = result.get("usageMetadata", {})
        usage = Usage(
            prompt_tokens=usage_meta.get("promptTokenCount", 0),
            completion_tokens=usage_meta.get("candidatesTokenCount", 0),
            total_tokens=usage_meta.get("totalTokenCount", 0),
        )

        return ChatCompletionResponse(
            choices=[Choice(
                index=0,
                message=Message(role="assistant", content=response_text),
                finish_reason=candidates[0].get("finishReason", "STOP").lower(),
            )],
            usage=usage,
            model=result.get("modelVersion", model),
        )

    def _convert_content_to_parts(self, content: str | list) -> list[dict[str, Any]]:
        """将 OpenAI 格式的 content 转换为 Gemini parts 格式。

        支持：
        - 纯文本: "hello" → [{"text": "hello"}]
        - 多模态: [{"type": "text", ...}, {"type": "image_url", ...}]
          → [{"text": ...}, {"inline_data": {"mime_type": ..., "data": ...}}]
        """
        if isinstance(content, str):
            return [{"text": content}]

        parts: list[dict[str, Any]] = []

        for item in content:
            if not isinstance(item, dict):
                continue

            item_type = item.get("type", "")

            if item_type == "text":
                parts.append({"text": item.get("text", "")})

            elif item_type == "image_url":
                image_url_obj = item.get("image_url", {})
                url = image_url_obj.get("url", "")

                if url.startswith("data:"):
                    # data URL 格式: data:image/jpeg;base64,xxxxx
                    # 解析 mime_type 和 base64 数据
                    header, b64_data = url.split(",", 1)
                    mime_type = header.split(":")[1].split(";")[0]
                    parts.append({
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data,
                        }
                    })
                else:
                    # 外部 URL — Gemini 不直接支持，跳过并记录警告
                    logger.warning("Gemini 不支持外部图片 URL，跳过: %s", url[:100])

        return parts


class GeminiChat:
    """模拟 openai.OpenAI().chat 接口。"""

    def __init__(self, base_url: str, api_key: str):
        self.completions = GeminiChatCompletions(base_url, api_key)


class GeminiClient:
    """模拟 openai.OpenAI() 接口 — 实际调用 Gemini 原生 API（含 Vision 能力）。

    用法:
        client = GeminiClient(api_key="sk-xxx", base_url="http://proxy:5050")

        # 纯文本调用
        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "hello"}],
        )

        # Vision 多模态调用
        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "描述这张图片"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
                ]
            }],
        )
    """

    def __init__(self, api_key: str, base_url: str = "http://43.162.95.137:5050"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.chat = GeminiChat(self.base_url, self.api_key)


def is_proxy_gateway(base_url: str, api_key: str) -> bool:
    """判断是否应使用 Gemini 原生 API（代理网关模式）。"""
    if api_key.startswith("sk-"):
        return True
    if "/openai/" in base_url:
        return False
    return False


def create_ai_client(api_key: str, base_url: str):
    """根据 API key 和 base_url 自动选择客户端类型。

    Returns:
        GeminiClient 或 OpenAI 客户端（两者接口兼容）。
    """
    if is_proxy_gateway(base_url, api_key):
        logger.info("检测到代理网关，使用 Gemini 原生 API 客户端（含 Vision 能力）")
        return GeminiClient(api_key=api_key, base_url=base_url)
    else:
        logger.info("使用 OpenAI 兼容客户端")
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url)

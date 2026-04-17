"""Gemini 原生 API 客户端 — 提供与 OpenAI SDK chat.completions.create 兼容的接口。

当使用代理网关（sk- 开头的 key）时，不能使用 OpenAI 兼容格式，
需要走 Gemini 原生 generateContent API。

此模块封装了差异，让 knowledge_extractor.py 无需修改就能切换后端。
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
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ChatCompletionResponse:
        """调用 Gemini generateContent API，返回兼容 OpenAI 的结果。"""
        messages = messages or []

        # 转换 OpenAI messages 格式 → Gemini contents 格式
        system_instruction = None
        contents: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")

            if role == "system":
                system_instruction = text
            elif role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": text}],
                })
            elif role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": text}],
                })

        # 构建 Gemini 请求体
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        # system instruction 处理：将 system prompt 合并到 user message 中
        # 代理网关可能不支持 systemInstruction / system_instruction 字段
        if system_instruction and contents:
            # 将 system prompt 前置到第一个 user message 中
            first_user_content = contents[0].get("parts", [{}])[0].get("text", "")
            contents[0]["parts"][0]["text"] = (
                f"[System Instructions]\n{system_instruction}\n\n"
                f"[User Request]\n{first_user_content}"
            )

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


class GeminiChat:
    """模拟 openai.OpenAI().chat 接口。"""

    def __init__(self, base_url: str, api_key: str):
        self.completions = GeminiChatCompletions(base_url, api_key)


class GeminiClient:
    """模拟 openai.OpenAI() 接口 — 实际调用 Gemini 原生 API。

    用法:
        client = GeminiClient(api_key="sk-xxx", base_url="http://proxy:5050")
        response = client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[...],
        )
    """

    def __init__(self, api_key: str, base_url: str = "https://your-proxy-gateway.example.com"):
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
        logger.info("检测到代理网关，使用 Gemini 原生 API 客户端")
        return GeminiClient(api_key=api_key, base_url=base_url)
    else:
        logger.info("使用 OpenAI 兼容客户端")
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url)

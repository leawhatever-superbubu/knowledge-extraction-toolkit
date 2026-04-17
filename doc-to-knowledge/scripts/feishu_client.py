"""飞书开放平台 API 封装层 — doc-to-knowledge 专用。

合并了两项核心能力：
1. 读取 docx 文档 block（飞书在线文档）
2. 读写多维表格 Bitable 记录

共享同一份 tenant_access_token 认证逻辑，同一个飞书自建应用凭证。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://open.feishu.cn/open-apis"

# 飞书 API 调用间隔（避免触发限频，限制 3 次/秒）
API_CALL_INTERVAL = 0.4  # 秒


class FeishuClient:
    """飞书 API 客户端 — 同时支持 docx 文档读取 + 多维表格读写。"""

    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: str = ""
        self._token_expires_at: float = 0

    # ── 认证 ──────────────────────────────────────────────

    def _ensure_token(self) -> str:
        """获取或刷新 tenant_access_token。"""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data.get('msg', data)}")

        self._token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200)
        logger.info("已获取 tenant_access_token (有效期 %ss)", data.get("expire", 7200))
        return self._token

    def _headers(self, content_type: str = "application/json; charset=utf-8") -> dict[str, str]:
        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    # ═══════════════════════════════════════════════════════
    #  能力 A：读取飞书 docx 文档 block
    # ═══════════════════════════════════════════════════════

    def get_document_blocks(
        self,
        document_id: str,
        page_size: int = 500,
    ) -> list[dict[str, Any]]:
        """获取文档所有 block（分页查询到底）。

        Args:
            document_id: 飞书 docx 文档 ID（从 URL 中解析，如 XxXxXx）

        Returns:
            block 列表，每个 block 含 block_id、block_type、以及对应类型的内容字段。
        """
        url = f"{BASE_URL}/docx/v1/documents/{document_id}/blocks"
        params: dict[str, Any] = {"page_size": page_size}
        all_blocks: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise RuntimeError(f"获取文档块失败: {data.get('msg', data)}")

            items = data.get("data", {}).get("items", [])
            all_blocks.extend(items)

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data["data"].get("page_token")

        logger.info("已获取文档 %s 的 %d 个 block", document_id, len(all_blocks))
        return all_blocks

    def get_document_meta(self, document_id: str) -> dict[str, Any]:
        """获取文档元信息（标题等）。"""
        url = f"{BASE_URL}/docx/v1/documents/{document_id}"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"获取文档信息失败: {data.get('msg', data)}")

        return data.get("data", {}).get("document", {})

    # ═══════════════════════════════════════════════════════
    #  能力 B：读写飞书多维表格 Bitable
    # ═══════════════════════════════════════════════════════

    def search_records(
        self,
        app_token: str,
        table_id: str,
        view_id: str | None = None,
        filter_conditions: list[dict[str, Any]] | None = None,
        conjunction: str = "and",
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """查询多维表格记录（使用 search 接口，支持条件过滤）。"""
        url = f"{BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/search"
        params: dict[str, Any] = {"page_size": page_size}
        if view_id:
            params["view_id"] = view_id

        body: dict[str, Any] = {}
        if filter_conditions:
            body["filter"] = {
                "conjunction": conjunction,
                "conditions": filter_conditions,
            }

        all_records: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["page_token"] = page_token

            resp = requests.post(url, headers=self._headers(), params=params, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise RuntimeError(f"查询多维表格失败: {data.get('msg', data)}")

            items = data.get("data", {}).get("items", [])
            all_records.extend(items)
            logger.info("已获取 %d 条记录 (本批 %d 条)", len(all_records), len(items))

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data["data"].get("page_token")

        return all_records

    def create_record(
        self,
        app_token: str,
        table_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """新增一条多维表格记录。

        Returns:
            新建记录信息，含 record_id。
        """
        url = f"{BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        body = {"fields": fields}

        resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"创建记录失败: {data.get('msg', data)}")

        record = data.get("data", {}).get("record", {})
        logger.info("已创建记录 %s", record.get("record_id", "unknown"))
        return record

    def update_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """更新一条多维表格记录的字段值。"""
        url = f"{BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        body = {"fields": fields}

        resp = requests.put(url, headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"更新记录 {record_id} 失败: {data.get('msg', data)}")

        logger.info("已更新记录 %s", record_id)
        return data.get("data", {})

    def list_records(
        self,
        app_token: str,
        table_id: str,
        view_id: str | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """列出多维表格全部记录（无条件过滤）。"""
        url = f"{BASE_URL}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        params: dict[str, Any] = {"page_size": page_size}
        if view_id:
            params["view_id"] = view_id

        all_records: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            if page_token:
                params["page_token"] = page_token

            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                raise RuntimeError(f"列出多维表格记录失败: {data.get('msg', data)}")

            items = data.get("data", {}).get("items", [])
            all_records.extend(items)

            if not data.get("data", {}).get("has_more", False):
                break
            page_token = data["data"].get("page_token")

        return all_records

    # ═══════════════════════════════════════════════════════
    #  能力 C：下载飞书云盘文件（上传的 .docx 等）
    # ═══════════════════════════════════════════════════════

    def download_file(self, file_token: str, save_path: str) -> str:
        """下载飞书云盘中上传的文件到本地。

        Args:
            file_token: 文件 token
            save_path: 本地保存路径

        Returns:
            本地文件路径。
        """
        url = f"{BASE_URL}/drive/v1/files/{file_token}/download"
        resp = requests.get(url, headers=self._headers(content_type=""), timeout=60, stream=True)
        resp.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        import os
        size = os.path.getsize(save_path)
        logger.info("已下载文件 %s → %s (%d bytes)", file_token, save_path, size)
        return save_path

    def get_file_meta(self, file_token: str) -> dict[str, Any]:
        """获取飞书云盘文件元信息（名称、类型等）。"""
        url = f"{BASE_URL}/drive/v1/metas/batch_query"
        body = {
            "request_docs": [
                {"doc_token": file_token, "doc_type": "file"}
            ]
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"获取文件元信息失败: {data.get('msg', data)}")

        metas = data.get("data", {}).get("metas", [])
        if metas:
            return metas[0]
        return {}

    # ── 机器人消息 ────────────────────────────────────────

    def send_text_message(self, chat_id: str, text: str) -> dict[str, Any]:
        """通过机器人向群聊发送文本消息。"""
        url = f"{BASE_URL}/im/v1/messages"
        params = {"receive_id_type": "chat_id"}
        body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        resp = requests.post(url, headers=self._headers(), params=params, json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            logger.warning("发送消息失败: %s", data.get("msg", data))
        else:
            logger.info("已发送消息到群 %s", chat_id)
        return data


# ── 工具函数 ──────────────────────────────────────────────

def parse_doc_token(doc_url_or_token: str) -> str:
    """从飞书文档 URL 或纯 token 中解析出 document_id / file_token。

    支持的格式：
    - https://xxx.feishu.cn/docx/XxXxXx      → 飞书在线文档
    - https://xxx.feishu.cn/docx/XxXxXx?xxx   → 飞书在线文档（带参数）
    - https://xxx.feishu.cn/file/XxXxXx       → 飞书云盘上传文件
    - https://xxx.feishu.cn/file/XxXxXx?xxx   → 飞书云盘上传文件（带参数）
    - XxXxXx（纯 token）
    """
    s = doc_url_or_token.strip()
    if "/" in s:
        # URL 格式 — 支持 /docx/ 和 /file/ 两种路径
        parts = s.split("/")
        for i, part in enumerate(parts):
            if part in ("docx", "file") and i + 1 < len(parts):
                token = parts[i + 1].split("?")[0].split("#")[0]
                return token
        raise ValueError(f"无法从 URL 中解析 document_id: {s}")
    return s

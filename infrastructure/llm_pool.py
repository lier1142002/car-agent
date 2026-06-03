"""异步 LLM 连接池 — 基于 httpx AsyncClient."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import config

logger = logging.getLogger(__name__)


class LLMPool:
    """httpx 异步 LLM 连接池.

    单进程内复用同一个 AsyncClient，利用 HTTP/1.1 keep-alive
    避免每次请求都重新建立 TCP+TLS 连接。
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        pool_size: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._api_url = (api_url or config.llm_api_url).rstrip("/")
        self._api_key = api_key or config.llm_api_key
        pool_size = pool_size or config.llm_pool_size
        timeout = timeout or config.llm_pool_timeout

        self._client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=pool_size,
                max_connections=pool_size,
            ),
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        logger.info("LLMPool 已初始化: url=%s pool=%d", self._api_url, pool_size)

    async def close(self) -> None:
        """关闭连接池."""
        await self._client.aclose()
        logger.info("LLMPool 已关闭")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> str:
        """发送 chat completion 请求, 返回文本响应."""
        url = f"{self._api_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model or config.llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"] or ""

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """发送请求并以 JSON 解析响应."""
        import json as _json
        import re

        text = await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        try:
            return _json.loads(text.strip())
        except _json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return _json.loads(m.group(0))
                except _json.JSONDecodeError:
                    pass
            return {}

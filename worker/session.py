"""Redis 会话管理 — Worker 侧加载/保存."""

from __future__ import annotations

import logging
from typing import Any, Optional

from agent.memory import SessionMemory
from config import config
from infrastructure.embedding import EmbeddingClient

logger = logging.getLogger(__name__)


class SessionManager:
    """Worker 进程内的会话管理器.

    持有进程级共享的 Embedding 和 Milvus 客户端,
    按 session_id 创建/加载 SessionMemory.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._embedding = EmbeddingClient()
        from pymilvus import MilvusClient
        self._milvus = MilvusClient(uri=config.milvus_uri)

    async def load_session(self, session_id: str, user_id: str = "default_user") -> SessionMemory:
        """从 Redis 加载会话 (不存在则创建)."""
        return await SessionMemory.load(
            redis=self._redis,
            session_id=session_id,
            embedding=self._embedding,
            milvus=self._milvus,
        )

    async def save_session(self, memory: SessionMemory) -> None:
        """保存会话到 Redis."""
        await memory.save()

    async def close_session(self, session_id: str) -> None:
        """删除会话所有 Redis Key."""
        await self._redis.delete(
            f"session:{session_id}",
            f"session:{session_id}:messages",
            f"session:{session_id}:state",
        )
        logger.info("会话已关闭: session_id=%s", session_id)

"""
记忆管理模块 — Redis 后端会话隔离版本。

短期记忆: Redis List 持久化 (每 session 独立)
长期记忆: Milvus 向量库 + Redis 热缓存
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from pymilvus import MilvusClient

from config import config
from infrastructure.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

LONG_TERM_TEXT_MAX = 4096


class SessionMemory:
    """Redis 支持的会话记忆 — 每 session_id 独立隔离.

    加载/保存短期记忆到 Redis, 长期记忆读 Milvus + Redis 缓存.

    Attributes:
        redis: Redis 客户端.
        session_id: 会话标识.
        user_id: 用户标识.
        short_term: 当前会话的短期记忆列表.
        embedding: Embedding 客户端 (进程内共享).
        milvus: MilvusClient (进程内共享).
    """

    def __init__(
        self,
        redis: Any,
        session_id: str,
        user_id: str = "default_user",
        embedding: Optional[EmbeddingClient] = None,
        milvus: Optional[MilvusClient] = None,
    ) -> None:
        self.redis = redis
        self.session_id = session_id
        self.user_id = user_id
        self.short_term: List[Dict[str, Any]] = []
        self._step_counter: int = 0
        self._state: Dict[str, Any] = {}
        self._embedding = embedding or EmbeddingClient()
        self._milvus = milvus or MilvusClient(uri=config.milvus_uri)
        self._lt_collection = config.long_term_memory_collection_name

    @classmethod
    async def load(
        cls,
        redis: Any,
        session_id: str,
        embedding: Optional[EmbeddingClient] = None,
        milvus: Optional[MilvusClient] = None,
    ) -> "SessionMemory":
        """从 Redis 加载会话上下文创建 SessionMemory 实例."""
        instance = cls(redis, session_id, embedding=embedding, milvus=milvus)

        # 加载会话元数据
        meta = await redis.hgetall(f"session:{session_id}")
        if meta:
            instance.user_id = meta.get("user_id", "default_user")
            instance._step_counter = int(meta.get("message_count", 0))

        # 加载对话历史
        messages_raw = await redis.lrange(f"session:{session_id}:messages", 0, -1)
        for msg_json in messages_raw:
            try:
                instance.short_term.append(json.loads(msg_json))
            except json.JSONDecodeError:
                logger.warning("跳过损坏的消息条目: session=%s", session_id)

        # 加载 Agent 状态
        state_raw = await redis.hgetall(f"session:{session_id}:state")
        instance._state = {
            "iteration_count": int(state_raw.get("iteration_count", 0)),
            "last_actions": state_raw.get("last_actions", "[]"),
            "rag_queries": state_raw.get("rag_queries", "[]"),
        }

        logger.info(
            "Session 已加载: session=%s user=%s messages=%d",
            session_id, instance.user_id, len(instance.short_term),
        )
        return instance

    async def save(self) -> None:
        """将当前状态写回 Redis."""
        ttl = config.redis_session_ttl

        # 保存会话元数据
        await self.redis.hset(
            f"session:{self.session_id}",
            mapping={
                "user_id": self.user_id,
                "last_access": datetime.datetime.now().isoformat(),
                "message_count": str(self._step_counter),
            },
        )
        await self.redis.expire(f"session:{self.session_id}", ttl)

        # 保存对话历史 (最近20条)
        pipe = self.redis.pipeline()
        for entry in self.short_term[-20:]:
            pipe.rpush(
                f"session:{self.session_id}:messages",
                json.dumps(entry, ensure_ascii=False, default=str),
            )
        pipe.ltrim(f"session:{self.session_id}:messages", -20, -1)
        pipe.expire(f"session:{self.session_id}:messages", ttl)
        await pipe.execute()

        # 保存 Agent 状态
        await self.redis.hset(
            f"session:{self.session_id}:state",
            mapping={
                "iteration_count": str(self._state.get("iteration_count", 0)),
                "last_actions": self._state.get("last_actions", "[]"),
                "rag_queries": self._state.get("rag_queries", "[]"),
            },
        )
        await self.redis.expire(f"session:{self.session_id}:state", ttl)

        logger.debug("Session 已保存: session=%s messages=%d", self.session_id, len(self.short_term))

    # ------------------------------------------------------------------
    # 短期记忆操作
    # ------------------------------------------------------------------

    def add(self, content: str, content_type: str = "step") -> None:
        """向短期记忆添加记录."""
        self._step_counter += 1
        entry: Dict[str, Any] = {
            "id": self._step_counter,
            "type": content_type,
            "content": content,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        self.short_term.append(entry)

    def get_context(self, max_entries: Optional[int] = None) -> str:
        """获取格式化的短期记忆上下文."""
        entries = self.short_term
        if max_entries is not None:
            entries = entries[-max_entries:]

        if not entries:
            return "（暂无历史记录）"

        lines: List[str] = []
        for entry in entries:
            etype = entry.get("type", "step")
            content_preview = entry["content"][:500]
            if len(entry["content"]) > 500:
                content_preview += "..."
            lines.append(f"[{entry['id']}] ({etype}) {content_preview}")

        return "\n".join(lines)

    def get_recent_dialogue_pairs(self, max_pairs: int = 3) -> str:
        """从短期记忆中提取最近的用户-助手对话对."""
        pairs: List[Tuple[str, str]] = []
        current_user: Optional[str] = None

        for entry in self.short_term:
            if entry.get("type") == "user_query":
                current_user = entry.get("content", "")
            elif entry.get("type") == "final_answer" and current_user is not None:
                answer = entry.get("content", "")[:300]
                pairs.append((current_user, answer))
                current_user = None

        if not pairs:
            return ""

        pairs = pairs[-max_pairs:]
        lines: List[str] = []
        for user_q, agent_a in pairs:
            lines.append(f"用户: {user_q}")
            lines.append(f"助手: {agent_a}")

        return "\n".join(lines)

    def get_dialogue_for_answer_context(self, max_pairs: int = 2) -> str:
        """获取对话历史用于答案生成的上下文注入."""
        return self.get_recent_dialogue_pairs(max_pairs=max_pairs)

    # ------------------------------------------------------------------
    # 长期记忆操作
    # ------------------------------------------------------------------

    def search_long_term(self, query: str, top_k: Optional[int] = None) -> List[str]:
        """搜索长期记忆 — Milvus 语义搜索 + Redis 缓存."""
        top_k = top_k or config.long_term_memory_top_k
        try:
            dense, _sparse = self._embedding.encode_text(query)
            results = self._milvus.search(
                collection_name=self._lt_collection,
                data=[dense],
                limit=top_k,
                output_fields=["content", "memory_type"],
            )
            if not results or not results[0]:
                return []

            memories: List[str] = []
            for hit in results[0]:
                entity = hit.get("entity", {})
                content = entity.get("content", "")
                mtype = entity.get("memory_type", "")
                if content:
                    memories.append(f"[{mtype}] {content}")
            logger.info("长期记忆检索: query='%s', 命中=%d", query[:50], len(memories))
            return memories
        except Exception as e:
            logger.error("长期记忆搜索失败: %s", e)
            return []

    def save_to_long_term(self, key: str, content: str) -> bool:
        """保存内容到长期记忆."""
        if not content.strip():
            return False
        memory_type = key.split(":", 1)[0] if ":" in key else "general"
        try:
            dense, sparse = self._embedding.encode_text(content)
            data = [{
                "user_id": self.user_id,
                "content": content[:LONG_TERM_TEXT_MAX],
                "memory_type": memory_type,
                "dense_vector": dense,
                "sparse_vector": {str(k): float(v) for k, v in sparse.items() if float(v) > 0},
                "created_at": datetime.datetime.now().isoformat(),
            }]
            self._milvus.insert(collection_name=self._lt_collection, data=data)
            logger.info("长期记忆已保存: key=%s, type=%s", key, memory_type)
            return True
        except Exception as e:
            logger.error("长期记忆保存失败: %s", e)
            return False


# Backwards compatibility alias
Memory = SessionMemory

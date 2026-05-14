"""
记忆管理模块。

实现 Agent 的短期记忆（会话历史）和长期记忆接口。
短期记忆基于列表存储，超阈值时自动调用 LLM 压缩为摘要。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import config

logger = logging.getLogger(__name__)


class Memory:
    """Agent 记忆管理器。

    短期记忆存储当前会话的对话步骤和中间结果。
    长期记忆预留 Milvus 持久化接口。

    Attributes:
        short_term: 短期记忆条目列表，每项为 dict(key, content, timestamp)。
        threshold: 字符数压缩阈值。
        llm_client: LLM 客户端，用于生成摘要。
    """

    def __init__(self) -> None:
        """初始化记忆管理器。"""
        self.short_term: List[Dict[str, Any]] = []
        self.threshold = config.memory_compress_threshold
        self.llm_client = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )
        self._step_counter: int = 0
        logger.info(
            "Memory 已初始化: threshold=%d chars", self.threshold
        )

    def add(self, content: str, content_type: str = "step") -> None:
        """向短期记忆添加一条记录。

        Args:
            content: 记忆内容文本。
            content_type: 内容类型标签（如 'user_query', 'tool_result', 'answer'）。
        """
        import datetime

        self._step_counter += 1
        entry: Dict[str, Any] = {
            "id": self._step_counter,
            "type": content_type,
            "content": content,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        self.short_term.append(entry)
        logger.debug(
            "记忆添加 [%d]: type=%s, len=%d chars",
            self._step_counter,
            content_type,
            len(content),
        )

        # 检查是否需要压缩
        total_chars = sum(len(e["content"]) for e in self.short_term)
        if total_chars > self.threshold:
            logger.info("记忆总字符数 %d 超过阈值 %d，触发压缩", total_chars, self.threshold)
            self.compress()

    def get_context(self, max_entries: Optional[int] = None) -> str:
        """获取格式化的短期记忆上下文。

        Args:
            max_entries: 最多返回的条目数，默认全部。

        Returns:
            str: 格式化的上下文文本，供 LLM 使用。
        """
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

    def get_raw(self) -> List[Dict[str, Any]]:
        """获取原始短期记忆列表。

        Returns:
            List[Dict]: 记忆条目列表。
        """
        return list(self.short_term)

    def compress(self) -> None:
        """压缩短期记忆：调用 LLM 生成摘要替换旧条目。

        保留最近 3 条记录，其余合并为摘要。
        """
        if len(self.short_term) <= 3:
            return

        # 保留最近 3 条
        recent = self.short_term[-3:]
        to_compress = self.short_term[:-3]

        # 构建压缩提示
        content_text = "\n".join(
            f"[{e['id']}] {e['content'][:300]}" for e in to_compress
        )

        try:
            response = self.llm_client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "请将以下对话历史压缩为一段简洁的摘要（不超过200字），"
                            "保留关键信息：用户问题、工具调用、重要结果。"
                        ),
                    },
                    {"role": "user", "content": content_text},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            summary = response.choices[0].message.content or "（摘要生成失败）"
        except Exception as e:
            logger.error("记忆压缩失败: %s", e)
            summary = f"（压缩失败: {e}）"

        # 重建短期记忆
        self.short_term = [
            {
                "id": self._step_counter,
                "type": "summary",
                "content": summary,
                "timestamp": "",
            }
        ] + recent

        logger.info("记忆已压缩，压缩前%d条 -> 压缩后%d条", len(to_compress) + 3, len(self.short_term))

    def clear(self) -> None:
        """清空所有短期记忆。"""
        self.short_term.clear()
        self._step_counter = 0
        logger.info("短期记忆已清空")

    # ------------------------------------------------------------------
    # 长期记忆接口（预留）
    # ------------------------------------------------------------------

    def save_to_long_term(self, key: str, content: str) -> None:
        """保存内容到长期记忆（预留接口）。

        Args:
            key: 记忆键。
            content: 记忆内容。
        """
        logger.info("长期记忆保存请求: key=%s (接口预留)", key)
        # TODO: 实现 Milvus 持久化存储
        pass

    def search_long_term(self, query: str, top_k: int = 5) -> List[str]:
        """搜索长期记忆（预留接口）。

        Args:
            query: 搜索查询。
            top_k: 返回数量。

        Returns:
            List[str]: 空列表（接口预留）。
        """
        logger.info("长期记忆搜索请求: query=%s (接口预留)", query)
        # TODO: 实现 Milvus 语义搜索
        return []

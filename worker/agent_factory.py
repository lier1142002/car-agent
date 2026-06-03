"""AgentForRequest 工厂 — 每个请求创建一个独立 Agent 实例."""

from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

from agent.agent_core import AgentForRequest
from agent.memory import SessionMemory
from infrastructure.llm_pool import LLMPool
from config import config
from tools.calculator_tool import CalculatorTool
from tools.rag_tool import RAGTool
from tools.web_search_tool import WebSearchTool

logger = logging.getLogger(__name__)


class AgentFactory:
    """请求级 Agent 工厂.

    持有进程级共享资源 (LLMPool, RAGTool, etc.),
    为每个请求创建独立的 AgentForRequest 实例.
    """

    def __init__(self) -> None:
        self.llm_pool = LLMPool()
        self.sync_llm = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )
        self.rag_tool = RAGTool()
        self.web_search = WebSearchTool()
        self.calculator = CalculatorTool()
        logger.info("AgentFactory 已初始化 (共享 LLMPool + sync_llm + Tools)")

    def create(self, session: SessionMemory) -> AgentForRequest:
        """为给定 session 创建独立的 AgentForRequest."""
        agent = AgentForRequest(
            session=session,
            llm_pool=self.llm_pool,
            sync_llm=self.sync_llm,
            rag_tool=self.rag_tool,
            web_search=self.web_search,
            calculator=self.calculator,
        )
        return agent

    async def close(self) -> None:
        """关闭共享资源."""
        await self.llm_pool.close()
        logger.info("AgentFactory 已关闭")

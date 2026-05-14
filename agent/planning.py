"""
任务规划模块。

根据用户查询和当前记忆上下文，调用 LLM 生成结构化的 JSON Action List，
指导 Executor 调度工具执行。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import config

logger = logging.getLogger(__name__)

# 规划提示词路径
PLAN_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "plan_prompt.txt"


class PlanningModule:
    """任务规划器。

    核心职责:
    1. 意图识别：分析用户查询类别（规格查询/对比/计算/闲聊）
    2. 生成 Action List：调用 LLM 输出 JSON 格式的工具调用计划
    3. 解析验证：确保输出为合法的 Action 列表

    Attributes:
        llm_client: LLM 客户端。
        system_prompt: 加载的 Few-shot 系统提示词。
    """

    def __init__(self) -> None:
        """初始化规划模块，加载提示词。"""
        self.llm_client = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )
        self.system_prompt = self._load_plan_prompt()
        logger.info("PlanningModule 已初始化")

    def generate_action_plan(
        self,
        query: str,
        memory_context: str = "",
    ) -> List[Dict[str, str]]:
        """生成 Action List。

        结合用户查询和记忆上下文，调用 LLM 生成工具调用计划。

        Args:
            query: 用户原始查询。
            memory_context: 格式化的短期记忆上下文。

        Returns:
            List[Dict[str, str]]: Action 列表，每项包含 tool 和 query。
                - tool: 工具名称 (rag_tool / web_search / calculator_tool)
                - query: 传递给工具的查询参数
        """
        # 构建用户消息
        user_message = f"用户: {query}"
        if memory_context:
            user_message = f"历史上下文:\n{memory_context}\n\n{user_message}"

        try:
            response = self.llm_client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,  # 规划阶段使用确定性输出
                max_tokens=1024,
            )

            raw_output = response.choices[0].message.content or "[]"
            logger.debug("LLM 规划原始输出: %s", raw_output)

            # 解析 JSON
            actions = self._parse_action_list(raw_output)
            logger.info("规划完成: 共 %d 个 Action", len(actions))
            return actions

        except Exception as e:
            logger.error("规划生成失败: %s", e)
            # 降级：默认使用 RAG 工具
            return [{"tool": "rag_tool", "query": query}]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_action_list(raw: str) -> List[Dict[str, str]]:
        """从 LLM 输出中解析 JSON Action List。

        处理 LLM 可能返回的额外文本（如 markdown 代码块包装）。

        Args:
            raw: LLM 原始输出文本。

        Returns:
            List[Dict]: 解析后的 Action 列表。
        """
        # 尝试直接解析
        try:
            result = json.loads(raw.strip())
            if isinstance(result, list):
                return PlanningModule._validate_actions(result)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取 JSON
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if json_match:
            try:
                result = json.loads(json_match.group(1).strip())
                if isinstance(result, list):
                    return PlanningModule._validate_actions(result)
            except json.JSONDecodeError:
                pass

        # 尝试匹配 JSON 数组模式
        array_match = re.search(r"\[[\s\S]*\]", raw)
        if array_match:
            try:
                result = json.loads(array_match.group(0))
                if isinstance(result, list):
                    return PlanningModule._validate_actions(result)
            except json.JSONDecodeError:
                pass

        logger.warning("无法解析 Action List JSON，返回空列表")
        return []

    @staticmethod
    def _validate_actions(
        actions: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """验证并清理 Action 列表。

        确保每个 Action 有 tool 和 query 字段。

        Args:
            actions: 待验证的 Action 列表。

        Returns:
            List[Dict]: 验证通过的 Action 列表。
        """
        valid: List[Dict[str, str]] = []
        for action in actions:
            tool = action.get("tool", "")
            query = action.get("query", "")
            if tool and query:
                valid.append({"tool": str(tool), "query": str(query)})
        return valid

    @staticmethod
    def _load_plan_prompt() -> str:
        """加载规划提示词文件。

        Returns:
            str: 提示词文本。
        """
        if PLAN_PROMPT_PATH.exists():
            return PLAN_PROMPT_PATH.read_text(encoding="utf-8")
        logger.warning("规划提示词文件不存在: %s，使用默认提示词", PLAN_PROMPT_PATH)
        return "你是一个任务规划器。根据用户查询生成 JSON 格式的 Action List。"

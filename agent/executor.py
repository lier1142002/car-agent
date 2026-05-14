"""
执行器模块。

接收 Planning 生成的 Action List，通过工具注册表动态调度工具，
串行执行并将结果反馈到 Memory。
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List

from tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class Executor:
    """任务执行器。

    维护任务队列（deque），按顺序执行 Action List。
    通过工具注册表（字典）根据名称动态查找工具实例。

    Attributes:
        tool_registry: 工具名 -> 工具实例的映射字典。
        task_queue: 待执行的任务队列。
    """

    def __init__(self) -> None:
        """初始化执行器，创建空注册表和任务队列。"""
        self.tool_registry: Dict[str, BaseTool] = {}
        self.task_queue: deque = deque()
        logger.info("Executor 已初始化")

    def register_tool(self, tool: BaseTool) -> None:
        """注册工具到注册表。

        Args:
            tool: 工具实例（需继承 BaseTool）。
        """
        self.tool_registry[tool.name] = tool
        logger.info("工具已注册: %s", tool.name)

    def register_tools(self, tools: List[BaseTool]) -> None:
        """批量注册工具。

        Args:
            tools: 工具实例列表。
        """
        for tool in tools:
            self.register_tool(tool)

    def get_tool(self, name: str) -> BaseTool:
        """按名称获取工具实例。

        Args:
            name: 工具名称。

        Returns:
            BaseTool: 工具实例。

        Raises:
            KeyError: 工具未注册时抛出。
        """
        if name not in self.tool_registry:
            raise KeyError(
                f"工具 '{name}' 未注册。已注册的工具: {list(self.tool_registry.keys())}"
            )
        return self.tool_registry[name]

    def execute(
        self,
        actions: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """串行执行 Action List。

        对每个 Action，从注册表查找对应工具并调用 run 方法，
        收集所有结果并返回。

        Args:
            actions: Action 列表，每项包含 tool 和 query。

        Returns:
            List[Dict[str, Any]]: 执行结果列表，与 actions 顺序对应。
                每个结果包含 tool, query, status, result, metadata。
        """
        if not actions:
            logger.info("Action List 为空，跳过执行")
            return []

        # 填充任务队列
        self.task_queue = deque(actions)

        results: List[Dict[str, Any]] = []

        while self.task_queue:
            action = self.task_queue.popleft()
            tool_name = action.get("tool", "")
            query = action.get("query", "")

            logger.info("执行 Action: tool=%s, query='%s'", tool_name, query[:80])

            try:
                tool = self.get_tool(tool_name)
                tool_result = tool.run(query)

                result = {
                    "tool": tool_name,
                    "query": query,
                    "status": tool_result.get("status", "unknown"),
                    "result": tool_result.get("result", ""),
                    "metadata": tool_result.get("metadata", {}),
                }
                logger.info(
                    "Action 完成: tool=%s, status=%s",
                    tool_name,
                    result["status"],
                )

            except KeyError as e:
                logger.error("工具未找到: %s", e)
                result = {
                    "tool": tool_name,
                    "query": query,
                    "status": "error",
                    "result": f"工具未注册: {tool_name}",
                    "metadata": {},
                }
            except Exception as e:
                logger.error("工具执行异常: %s - %s", tool_name, e)
                result = {
                    "tool": tool_name,
                    "query": query,
                    "status": "error",
                    "result": f"执行异常: {str(e)}",
                    "metadata": {},
                }

            results.append(result)

        logger.info("所有 Action 执行完毕，共 %d 个结果", len(results))
        return results

    def get_tool_names(self) -> List[str]:
        """获取已注册的工具名称列表。

        Returns:
            List[str]: 工具名称列表。
        """
        return list(self.tool_registry.keys())

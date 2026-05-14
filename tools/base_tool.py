"""
工具抽象基类模块。

所有工具必须继承 BaseTool 并实现 run 方法，
确保统一的调用接口和可序列化的返回格式。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """工具抽象基类。

    每个工具需提供 name 和 description 属性，
    并实现 run(query, **kwargs) -> Dict 方法。

    Attributes:
        name: 工具唯一名称，用于注册表和日志标识。
        description: 工具功能描述，供 LLM 规划时参考。
    """

    def __init__(self) -> None:
        self._name: str = self.__class__.__name__
        self._description: str = ""

    @property
    def name(self) -> str:
        """工具名称。"""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def description(self) -> str:
        """工具描述。"""
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        self._description = value

    @abstractmethod
    def run(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        """执行工具核心逻辑。

        Args:
            query: 传递给工具的查询字符串。
            **kwargs: 工具特定的额外参数。

        Returns:
            Dict[str, Any]: 包含执行结果、状态和元数据的字典。
                - status: "success" 或 "error"
                - result: 主要输出内容
                - metadata: 辅助信息（来源、耗时等）
        """
        ...

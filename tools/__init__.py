"""
工具组件层：RAG 检索、Web 搜索、计算器等工具。

通过 TOOL_REGISTRY 字典实现工具名到实例的动态映射，
供 Executor 在执行时按名称查找和调用。
"""

from tools.base_tool import BaseTool
from tools.rag_tool import RAGTool
from tools.web_search_tool import WebSearchTool
from tools.calculator_tool import CalculatorTool

__all__ = ["BaseTool", "RAGTool", "WebSearchTool", "CalculatorTool"]

"""
计算器工具模块。

提供安全的数学表达式求值功能，用于汽车销售场景中的
贷款计算、价格对比、税费估算等。
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict

from tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class CalculatorTool(BaseTool):
    """安全计算器工具。

    使用受限的 eval 环境（仅允许数学运算和白名单函数），
    对数学表达式求值并返回结果。

    Attributes:
        name: "calculator_tool"
        description: 工具功能描述。
    """

    def __init__(self) -> None:
        """初始化计算器工具。"""
        super().__init__()
        self.name = "calculator_tool"
        self.description = (
            "执行数学计算，支持 +、-、*、/、%、** 及 math 模块函数"
            "（sqrt, ceil, floor, log 等），用于贷款、税费计算"
        )

        # 安全的执行命名空间，仅暴露数学函数
        self._safe_namespace: Dict[str, Any] = {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
            "sqrt": math.sqrt,
            "ceil": math.ceil,
            "floor": math.floor,
            "log": math.log,
            "log10": math.log10,
            "pi": math.pi,
            "e": math.e,
            "int": int,
            "float": float,
        }

    def run(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        """执行数学表达式计算。

        支持格式:
        - 纯表达式: "100000 * 0.7 / 36"
        - 带描述: "星辰ES9售价 * 0.7 / 36"

        Args:
            query: 数学表达式字符串。
            **kwargs: 额外参数（未使用）。

        Returns:
            Dict[str, Any]:
                - status: "success" 或 "error"
                - result: 计算结果（数值或错误信息）
                - metadata: 包含 expression 和 result 的元数据。
        """
        # 尝试从查询中提取可计算的表达式
        expression = self._extract_expression(query)

        if not expression:
            return {
                "status": "error",
                "result": "未能从输入中提取可计算的数学表达式",
                "metadata": {"query": query},
            }

        logger.info("计算表达式: %s", expression)

        try:
            result = self._safe_eval(expression)
            logger.info("计算结果: %s = %s", expression, result)
            return {
                "status": "success",
                "result": result,
                "metadata": {
                    "expression": expression,
                    "result": result,
                },
            }
        except Exception as e:
            logger.error("计算失败: %s", e)
            return {
                "status": "error",
                "result": f"计算错误: {str(e)}",
                "metadata": {"expression": expression},
            }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_expression(query: str) -> str:
        """从查询字符串中提取数学表达式。

        优先提取纯数字和运算符组成的部分。
        如果包含中文描述，尝试移除描述部分。

        Args:
            query: 用户查询字符串。

        Returns:
            str: 提取的表达式。
        """
        query = query.strip()

        # 如果整体看起来就像表达式（以数字或括号开头），直接使用
        if re.match(r"^[\d\(\.\-\+]", query):
            return query

        # 尝试找到包含数字和运算符的最长子串
        math_pattern = r"[\d\s\+\-\*\/\%\(\)\.\,\^eEpPiI]+"
        matches = re.findall(math_pattern, query)
        if matches:
            # 取最长的匹配
            return max(matches, key=len).strip()

        return query

    def _safe_eval(self, expression: str) -> float:
        """在受限命名空间中安全求值。

        Args:
            expression: 数学表达式字符串。

        Returns:
            float: 计算结果。

        Raises:
            ValueError: 表达式包含不安全操作时抛出。
        """
        # 安全检查：禁止潜在危险的内置函数
        forbidden = {"__", "import", "exec", "eval", "open", "os.", "sys.", "subprocess"}
        expr_lower = expression.lower()
        for keyword in forbidden:
            if keyword in expr_lower:
                raise ValueError(f"表达式包含不安全关键字: {keyword}")

        # 替换中文运算符
        expression = (
            expression.replace("×", "*")
            .replace("÷", "/")
            .replace("x", "*")
            .replace("X", "*")
        )

        # 在安全命名空间中求值
        result = eval(expression, {"__builtins__": {}}, self._safe_namespace)
        return round(result, 4) if isinstance(result, float) else result

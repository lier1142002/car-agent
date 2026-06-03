"""多车型对比编排器."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from engine.rule_engine import RuleEngine
from infrastructure.llm_pool import LLMPool

logger = logging.getLogger(__name__)


class Comparator:
    """多车型横向对比 — 规则提取 + LLM 对比总结."""

    def __init__(self, llm_pool: LLMPool) -> None:
        self._llm = llm_pool
        self._rules = RuleEngine()

    async def compare(
        self,
        vehicle_data: Dict[str, str],
        aspects: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """执行多车型对比."""
        # 1. 规则引擎提取标准化参数
        structured = self._rules.extract_multi(vehicle_data, aspects)

        # 2. 构建对比上下文
        context_parts = []
        for vehicle, text in vehicle_data.items():
            context_parts.append(f"=== {vehicle} ===\n{text[:1500]}")
        context_text = "\n\n".join(context_parts)

        aspect_list = aspects or list(self._rules.PARAM_RULES.keys())

        # 3. LLM 生成对比总结
        try:
            summary = await self._llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个专业的汽车对比评测编辑。请对以下车型进行横向对比分析。\n"
                            f"对比维度: {', '.join(aspect_list)}\n"
                            "输出结构化的 Markdown 对比报告, 包含:\n"
                            "1. 各维度逐一对比表格\n"
                            "2. 综合优劣势分析\n"
                            "3. 不同需求场景的推荐"
                        ),
                    },
                    {"role": "user", "content": f"车型信息:\n{context_text}\n\n请生成对比报告:"},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
        except Exception as e:
            logger.error("LLM 对比生成失败: %s", e)
            summary = "对比生成失败，请参考下方的结构化参数对比。"

        return {
            "structured_params": structured,
            "llm_summary": summary,
            "vehicle_count": len(vehicle_data),
        }

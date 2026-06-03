"""智能推荐打分器 — LLM 多维度评分."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.llm_pool import LLMPool

logger = logging.getLogger(__name__)

DEFAULT_SCORE_DIMENSIONS = {
    "性价比": 0.25,
    "安全性": 0.20,
    "空间舒适": 0.15,
    "智能化": 0.15,
    "品牌售后": 0.10,
    "能耗经济": 0.15,
}


class Scorer:
    """基于 LLM 的多维度车型打分器."""

    def __init__(self, llm_pool: LLMPool) -> None:
        self._llm = llm_pool

    async def score_vehicle(
        self,
        vehicle_name: str,
        vehicle_info: str,
        user_context: Optional[Dict[str, Any]] = None,
        dimensions: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """对单个车型进行多维度打分."""
        dims = dimensions or DEFAULT_SCORE_DIMENSIONS
        dim_names = list(dims.keys())

        system_prompt = (
            "你是一个专业的汽车评测评分专家。请对给定车型按以下维度分别打分(0-10分):\n"
            + "\n".join(f"- {d}" for d in dim_names)
            + "\n\n输出 JSON 格式: {\"scores\": [{\"dimension\": \"...\", \"score\": 8.5, \"reason\": \"...\"}]}"
        )

        user_prompt = f"车型: {vehicle_name}\n车型信息:\n{vehicle_info[:2000]}"
        if user_context:
            user_prompt += f"\n\n用户偏好: {user_context}"

        try:
            result = await self._llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )

            scores = result.get("scores", [])
            dim_scores: Dict[str, Dict[str, Any]] = {}
            total = 0.0

            for item in scores:
                dim = item.get("dimension", "")
                score = float(item.get("score", 0))
                reason = item.get("reason", "")
                weight = dims.get(dim, 0.0)
                dim_scores[dim] = {"score": score, "reason": reason, "weight": weight}
                total += score * weight

            return {
                "vehicle": vehicle_name,
                "total_score": round(total, 2),
                "dimensions": dim_scores,
            }
        except Exception as e:
            logger.error("打分失败: vehicle=%s error=%s", vehicle_name, e)
            return {
                "vehicle": vehicle_name,
                "total_score": 0.0,
                "dimensions": {},
                "error": str(e),
            }

    async def score_multi(
        self,
        vehicles: Dict[str, str],
        user_context: Optional[Dict[str, Any]] = None,
        dimensions: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """对多个车型并行打分, 按总分降序排列."""
        import asyncio

        tasks = [
            self.score_vehicle(name, info, user_context, dimensions)
            for name, info in vehicles.items()
        ]
        results = await asyncio.gather(*tasks)
        results.sort(key=lambda r: r["total_score"], reverse=True)
        logger.info("多车型打分完成: vehicles=%d", len(results))
        return results

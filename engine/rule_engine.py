"""车型参数规则引擎 — 从非结构化文本中提取标准化参数."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class RuleEngine:
    """基于规则的车型参数提取器.

    从 RAG 检索到的文本中按正则 + 关键字匹配提取标准化参数.
    LLM 不可用时作为降级方案直接返回结构化数据.
    """

    # 参数提取规则: {参数名: [匹配模式列表]}
    PARAM_RULES: Dict[str, List[str]] = {
        "价格": [r"(\d+\.?\d*)\s*万", r"售价[：:]\s*(\d+\.?\d*)", r"指导价[：:]\s*(\d+\.?\d*)"],
        "续航": [r"续航[：:]\s*(\d+)", r"(\d+)\s*公里", r"NEDC[：:]?\s*(\d+)"],
        "功率": [r"(\d+)\s*kW", r"最大功率[：:]\s*(\d+)", r"(\d+)\s*千瓦"],
        "加速": [r"0?[-\s]*100[公km]*[里/小时]*[：:]*\s*(\d+\.?\d*)\s*秒", r"百公里加速[：:]\s*(\d+\.?\d*)"],
        "电池": [r"(\d+\.?\d*)\s*kWh", r"电池容量[：:]\s*(\d+\.?\d*)"],
        "智驾": [r"(L\d+)[级别]*自动驾驶", r"智驾[：:]\s*(.+)", r"智能驾驶[：:]\s*(.+?)[\n，]"],
        "尺寸": [r"(\d{4})\s*[×xX]\s*(\d{4})\s*[×xX]\s*(\d{4})"],
    }

    def extract(self, text: str, aspects: Optional[List[str]] = None) -> Dict[str, Any]:
        """从文本中提取指定维度的参数."""
        target = aspects or list(self.PARAM_RULES.keys())
        result: Dict[str, List[str]] = {}

        for aspect in target:
            patterns = self.PARAM_RULES.get(aspect, [])
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, text, re.IGNORECASE)
                for f in found:
                    if isinstance(f, tuple):
                        matches.append(" × ".join(f))
                    else:
                        matches.append(str(f))
            if matches:
                result[aspect] = matches[:3]

        return result

    def extract_multi(
        self,
        texts: Dict[str, str],
        aspects: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """从多车型文本中批量提取参数."""
        return {
            vehicle: self.extract(text, aspects)
            for vehicle, text in texts.items()
        }

"""
反思与迭代控制模块。

对当前回答进行质量评估，判断是否需要补充信息，
生成补充 Action List 驱动迭代优化。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from config import config

logger = logging.getLogger(__name__)

# 反思提示词路径
REFLECTION_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "reflection_prompt.txt"


class ReflectionModule:
    """反思评估器。

    核心职责:
    1. 评估当前回答的完整性、准确性和实用性
    2. 判断是否需要追加工具调用以补充信息
    3. 控制迭代次数，防止无限循环

    Attributes:
        llm_client: LLM 客户端。
        system_prompt: 反思提示词。
        max_iterations: 最大迭代次数。
        quality_threshold: 质量阈值（0~1）。
        iteration_count: 当前已迭代次数。
    """

    def __init__(self) -> None:
        """初始化反思模块。"""
        self.llm_client = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )
        self.system_prompt = self._load_reflection_prompt()
        self.max_iterations = config.reflection_max_iterations
        self.quality_threshold = config.reflection_quality_threshold
        self.iteration_count: int = 0
        logger.info(
            "ReflectionModule 已初始化: max_iter=%d, threshold=%.1f",
            self.max_iterations,
            self.quality_threshold,
        )

    def evaluate_and_refine(
        self,
        query: str,
        current_answer: str,
        memory_context: str = "",
    ) -> Tuple[bool, List[Dict[str, str]]]:
        """评估回答质量并决定是否继续迭代。

        Args:
            query: 用户原始问题。
            current_answer: 当前生成的回答文本。
            memory_context: 记忆上下文。

        Returns:
            Tuple[bool, List[Dict]]:
                - should_continue: 是否需要继续迭代。
                - new_actions: 补充的 Action List。
        """
        self.iteration_count += 1

        # 达到最大迭代次数，强制终止
        if self.iteration_count > self.max_iterations:
            logger.info(
                "已达到最大迭代次数 %d，强制终止迭代",
                self.max_iterations,
            )
            return False, []

        # 构建评估请求
        eval_message = (
            f"用户问题: {query}\n\n"
            f"当前回答: {current_answer}\n\n"
            f"已迭代次数: {self.iteration_count}/{self.max_iterations}"
        )
        if memory_context:
            eval_message = f"历史上下文:\n{memory_context}\n\n{eval_message}"

        try:
            response = self.llm_client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": eval_message},
                ],
                temperature=0.0,
                max_tokens=1024,
            )

            raw_output = response.choices[0].message.content or "{}"
            logger.debug("反思评估原始输出: %s", raw_output)

            # 解析评估结果
            eval_result = self._parse_evaluation(raw_output)

            score = eval_result.get("score", 0.0)
            needs_iteration = eval_result.get("needs_iteration", False)
            suggested_actions = eval_result.get("suggested_actions", [])

            # 达到质量阈值，终止迭代
            if score >= self.quality_threshold:
                logger.info("回答质量分数 %.2f >= 阈值 %.2f，终止迭代", score, self.quality_threshold)
                return False, []

            # 达到最大迭代次数，终止
            if self.iteration_count >= self.max_iterations:
                logger.info("已达最大迭代次数，终止迭代")
                return False, []

            # 需要迭代但没有建议，终止
            if needs_iteration and not suggested_actions:
                logger.warning("评估建议迭代但未提供 Action，终止迭代")
                return False, []

            logger.info(
                "需要第 %d 次迭代: score=%.2f, 建议 %d 个新 Action",
                self.iteration_count,
                score,
                len(suggested_actions),
            )
            return needs_iteration, suggested_actions

        except Exception as e:
            logger.error("反思评估失败: %s", e)
            return False, []

    def reset(self) -> None:
        """重置迭代计数器。"""
        self.iteration_count = 0
        logger.info("迭代计数器已重置")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_evaluation(raw: str) -> Dict[str, Any]:
        """解析 LLM 评估输出。

        Args:
            raw: LLM 原始输出。

        Returns:
            Dict: 解析后的评估数据。
        """
        default: Dict[str, Any] = {
            "score": 0.0,
            "needs_iteration": False,
            "missing_aspects": [],
            "suggested_actions": [],
            "feedback": "",
        }

        # 尝试直接解析
        try:
            result = json.loads(raw.strip())
            default.update(result)
            return default
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块提取
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if json_match:
            try:
                result = json.loads(json_match.group(1).strip())
                default.update(result)
                return default
            except json.JSONDecodeError:
                pass

        logger.warning("无法解析评估 JSON，返回默认值")
        return default

    @staticmethod
    def _load_reflection_prompt() -> str:
        """加载反思提示词文件。

        Returns:
            str: 提示词文本。
        """
        if REFLECTION_PROMPT_PATH.exists():
            return REFLECTION_PROMPT_PATH.read_text(encoding="utf-8")
        logger.warning("反思提示词文件不存在: %s，使用默认", REFLECTION_PROMPT_PATH)
        return "你是一个质量评估专家。评估回答质量并输出 JSON。"

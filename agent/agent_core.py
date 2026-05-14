"""
Agent 核心主循环模块。

整合 Planning、Memory、Executor、Reflection 四大模块，
实现完整的「规划 → 执行 → 生成答案 → 反思迭代」工作流。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from openai import OpenAI

from agent.executor import Executor
from agent.memory import Memory
from agent.planning import PlanningModule
from agent.reflection import ReflectionModule
from config import config
from tools.calculator_tool import CalculatorTool
from tools.rag_tool import RAGTool
from tools.web_search_tool import WebSearchTool

logger = logging.getLogger(__name__)


class AutoSalesAgent:
    """汽车销售培训 AI Agent 主类。

    整合四大核心模块并提供扁平的调用接口 run_query()，
    方便后续通过 REST API / WebSocket 与前端集成。

    工作流程:
    1. Planning: 分析查询 -> 生成 Action List
    2. Executor: 按 Action List 调度工具执行
    3. 聚合工具结果，调用 LLM 生成初步答案
    4. Reflection: 评估答案质量
       - 达标: 输出最终答案
       - 不足: 生成补充 Action -> 回到步骤 2

    Attributes:
        planning: 规划模块。
        memory: 记忆模块。
        executor: 执行器。
        reflection: 反思模块。
        rag_tool: RAG 检索工具。
        web_search: 联网搜索工具。
        calculator: 计算器工具。
        llm_client: LLM 客户端（用于答案生成）。
    """

    def __init__(self) -> None:
        """初始化 Agent 及其所有子模块和工具。"""
        # 核心模块
        self.planning = PlanningModule()
        self.memory = Memory()
        self.executor = Executor()
        self.reflection = ReflectionModule()

        # 工具实例
        self.rag_tool = RAGTool()
        self.web_search = WebSearchTool()
        self.calculator = CalculatorTool()

        # 注册工具到执行器
        self.executor.register_tools([
            self.rag_tool,
            self.web_search,
            self.calculator,
        ])

        # LLM 客户端（用于最终答案生成和闲聊）
        self.llm_client = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )

        logger.info("AutoSalesAgent 初始化完成，已注册工具: %s", self.executor.get_tool_names())

    # ------------------------------------------------------------------
    # 主动态接口
    # ------------------------------------------------------------------

    def run_query(self, user_input: str) -> str:
        """处理用户查询的主入口。

        完整的 Agent 工作流:
        Plan -> Execute -> Generate Answer -> Reflect -> (loop) -> Final Answer

        Args:
            user_input: 用户自然语言查询。

        Returns:
            str: Agent 最终回答文本。
        """
        logger.info("=" * 60)
        logger.info("收到用户查询: %s", user_input)

        # 1. 存储用户查询到记忆
        self.memory.add(user_input, content_type="user_query")

        # 2. 规划阶段
        memory_ctx = self.memory.get_context(max_entries=10)
        actions = self.planning.generate_action_plan(user_input, memory_ctx)

        if not actions:
            # 空 Action List，直接闲聊回复
            return self._chat_reply(user_input)

        # 3. 执行阶段
        exec_results = self.executor.execute(actions)

        # 4. 存储执行结果
        for result in exec_results:
            self.memory.add(
                f"[{result['tool']}] {result['result'][:500]}",
                content_type="tool_result",
            )

        # 5. 生成初步答案
        current_answer = self._generate_answer(user_input, exec_results)

        # 6. 反思迭代
        self.reflection.reset()
        for _ in range(config.reflection_max_iterations):
            should_continue, new_actions = self.reflection.evaluate_and_refine(
                query=user_input,
                current_answer=current_answer,
                memory_context=self.memory.get_context(),
            )

            if not should_continue or not new_actions:
                break

            # 执行补充 Actions
            logger.info("--- 迭代补充 ---")
            supplement_results = self.executor.execute(new_actions)

            for result in supplement_results:
                self.memory.add(
                    f"[补充-{result['tool']}] {result['result'][:500]}",
                    content_type="tool_result",
                )

            # 合并结果重新生成答案
            all_results = exec_results + supplement_results
            current_answer = self._generate_answer(user_input, all_results)

        # 7. 存储最终答案
        self.memory.add(current_answer, content_type="final_answer")

        logger.info("最终答案: %d chars", len(current_answer))
        logger.info("=" * 60)
        return current_answer

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _generate_answer(
        self,
        query: str,
        exec_results: List[Dict[str, Any]],
    ) -> str:
        """根据工具执行结果调用 LLM 生成自然语言答案。

        Args:
            query: 用户原始查询。
            exec_results: 所有工具执行结果。

        Returns:
            str: 生成的回答文本。
        """
        # 构建上下文
        context_parts: List[str] = []
        for i, result in enumerate(exec_results, start=1):
            tool_name = result.get("tool", "unknown")
            tool_result = result.get("result", "")
            if tool_result:
                context_parts.append(f"[来源{i} - {tool_name}]\n{tool_result}")

        context_text = "\n\n".join(context_parts) if context_parts else "无参考信息"

        system_prompt = (
            "你是一位专业的汽车销售培训顾问。请基于提供的参考信息回答用户问题。"
            "要求:\n"
            "1. 综合所有来源信息给出完整回答\n"
            "2. 使用 [来源N] 标注信息出处\n"
            "3. 专业、准确、有销售指导价值\n"
            "4. 无法确认的信息请明确说明"
        )

        try:
            response = self.llm_client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"参考信息:\n{context_text}\n\n"
                            f"用户问题: {query}\n\n"
                            "请生成专业回答:"
                        ),
                    },
                ],
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
            )
            return response.choices[0].message.content or "抱歉，暂时无法生成回答。"
        except Exception as e:
            logger.error("答案生成失败: %s", e)
            # 降级：直接拼接工具结果
            return f"（LLM 调用失败，以下为检索到的原始信息）\n\n{context_text}"

    def _chat_reply(self, user_input: str) -> str:
        """处理闲聊类查询（空 Action List 时）。

        Args:
            user_input: 用户消息。

        Returns:
            str: 闲聊回复。
        """
        try:
            response = self.llm_client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一位友好的汽车销售培训助手。"
                            "你可以帮助用户了解汽车产品知识、销售技巧和行业信息。"
                        ),
                    },
                    {"role": "user", "content": user_input},
                ],
                temperature=0.7,
                max_tokens=512,
            )
            return response.choices[0].message.content or "您好！有什么可以帮您的？"
        except Exception:
            return "您好！我是汽车销售培训助手，请问有什么可以帮您的？"

    def index_knowledge_base(self, doc_path: str) -> int:
        """索引知识库文档。

        Args:
            doc_path: PDF 文档路径。

        Returns:
            int: 索引的文本块数量。
        """
        return self.rag_tool.index_documents(doc_path)

    def get_state(self) -> Dict[str, Any]:
        """获取 Agent 内部状态（用于序列化/持久化）。

        Returns:
            Dict: Agent 状态数据。
        """
        return {
            "memory": self.memory.get_raw(),
            "tools": self.executor.get_tool_names(),
            "rag_indexed": self.rag_tool.is_indexed,
            "iteration_count": self.reflection.iteration_count,
        }

    def clear_session(self) -> None:
        """清空会话状态（记忆和迭代计数）。"""
        self.memory.clear()
        self.reflection.reset()
        logger.info("会话状态已清空")

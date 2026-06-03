"""
Agent 核心主循环模块。

整合 Planning、Memory、Executor、Reflection 四大模块，
实现完整的「规划 → 执行 → 生成答案 → 反思迭代」工作流。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Generator, List, Optional, Tuple

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

        # 2. 查询改写（基于历史对话消除代词歧义）
        rewritten_query = self.memory.rewrite_query_with_history(user_input)

        # 3. 检索长期记忆
        long_term_context = self.memory.search_long_term(rewritten_query)

        # 4. 规划阶段（使用改写后的查询 + 长期记忆 + 短期记忆）
        memory_ctx = self.memory.get_context(max_entries=10)
        if long_term_context:
            lt_text = "长期记忆（用户偏好/历史信息）:\n" + "\n".join(f"- {m}" for m in long_term_context)
            memory_ctx = lt_text + "\n\n" + memory_ctx
        actions = self.planning.generate_action_plan(rewritten_query, memory_ctx)

        if not actions:
            reply = self._chat_reply(user_input)
            self.memory.add(reply, content_type="final_answer")
            self.memory.extract_and_save_preferences(user_input, reply)
            return reply

        # 5. 执行阶段
        exec_results = self.executor.execute(actions)

        # 6. 存储执行结果
        for result in exec_results:
            self.memory.add(
                f"[{result['tool']}] {result['result'][:500]}",
                content_type="tool_result",
            )

        # 7. 生成初步答案（注入对话历史 + 长期记忆）
        filtered_results = self._filter_redundant_results(
            self._compress_contexts(rewritten_query, exec_results)
        )
        current_answer = self._generate_answer(
            rewritten_query, filtered_results,
            dialogue_context=self.memory.get_dialogue_for_answer_context(),
            long_term_context=long_term_context,
        )

        # 6. 反思迭代
        self.reflection.reset()
        for _ in range(config.reflection_max_iterations):
            should_continue, new_actions = self.reflection.evaluate_and_refine(
                query=rewritten_query,
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
            filtered_all = self._filter_redundant_results(
                self._compress_contexts(rewritten_query, all_results)
            )
            current_answer = self._generate_answer(
                rewritten_query, filtered_all,
                dialogue_context=self.memory.get_dialogue_for_answer_context(),
                long_term_context=long_term_context,
            )

        # 7. 存储最终答案
        self.memory.add(current_answer, content_type="final_answer")

        # 8. 提取并保存用户偏好到长期记忆
        self.memory.extract_and_save_preferences(user_input, current_answer)

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
        dialogue_context: str = "",
        long_term_context: Optional[List[str]] = None,
    ) -> str:
        """根据工具执行结果调用 LLM 生成自然语言答案。

        Args:
            query: 用户查询（可能是改写后的）。
            exec_results: 所有工具执行结果。
            dialogue_context: 近期对话历史，用于多轮对话。
            long_term_context: 长期记忆中检索到的用户偏好。

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
            "4. 无法确认的信息请明确说明\n"
            "5. 如果是多轮对话，自然引用前文提到的信息"
        )

        # 注入对话历史
        if dialogue_context:
            system_prompt += (
                f"\n\n近期对话历史（请参考上下文保持回答连贯）:\n{dialogue_context}"
            )

        # 注入长期记忆（用户偏好）
        if long_term_context:
            lt_text = "\n".join(f"- {m}" for m in long_term_context)
            system_prompt += (
                f"\n\n已知用户偏好/信息（可据此个性化回答）:\n{lt_text}"
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
            answer = response.choices[0].message.content or "抱歉，暂时无法生成回答。"
            # 生成侧优化: 引用真实性校验
            verified_answer, _ = self._verify_citations(answer, exec_results, query)
            return verified_answer
        except Exception as e:
            logger.error("答案生成失败: %s", e, exc_info=True)
            # 降级：直接拼接工具结果
            return f"（LLM 调用失败，以下为检索到的原始信息）\n\n{context_text}"

    # ------------------------------------------------------------------
    # 生成侧优化: 上下文压缩 / 冗余过滤 / 引用校验
    # ------------------------------------------------------------------

    def _compress_contexts(
        self,
        query: str,
        exec_results: List[Dict[str, Any]],
        max_chars: int = 800,
    ) -> List[Dict[str, Any]]:
        """对过长的工具结果进行 LLM 压缩，保留与 query 相关的部分。

        Args:
            query: 用户查询。
            exec_results: 原始工具执行结果。
            max_chars: 触发压缩的字符数阈值。

        Returns:
            List[Dict]: 压缩后的结果列表（新列表，不修改原数据）。
        """
        compressed: List[Dict[str, Any]] = []
        for result in exec_results:
            original = result.get("result", "")
            if not original or len(original) <= max_chars:
                compressed.append(result)
                continue

            # 过长结果调用 LLM 压缩
            try:
                response = self.llm_client.chat.completions.create(
                    model=config.llm_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是一个信息压缩器。从给定文本中提取与用户查询直接相关的信息。"
                                "保留关键事实、数字、参数，删除无关内容。"
                                "压缩后的内容应保持原意，长度控制在400字以内。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"用户查询: {query}\n\n"
                                f"原始文本 ({len(original)} 字符):\n{original[:3000]}\n\n"
                                "请提取与查询相关的核心信息:"
                            ),
                        },
                    ],
                    temperature=0.0,
                    max_tokens=512,
                )
                compressed_text = response.choices[0].message.content or original[:max_chars]
                new_result = dict(result)
                new_result["result"] = compressed_text
                new_result["metadata"] = dict(result.get("metadata", {}))
                new_result["metadata"]["compressed"] = True
                compressed.append(new_result)
                logger.info(
                    "上下文压缩: %s %d -> %d chars",
                    result.get("tool", "?"), len(original), len(compressed_text),
                )
            except Exception as e:
                logger.error("上下文压缩失败: %s", e)
                compressed.append(result)

        return compressed

    def _filter_redundant_results(
        self,
        exec_results: List[Dict[str, Any]],
        similarity_threshold: float = 0.75,
    ) -> List[Dict[str, Any]]:
        """过滤冗余工具结果，移除内容高度重叠的条目。

        使用 token-Jaccard 相似度检测重复，保留更长的结果。

        Args:
            exec_results: 工具执行结果列表。
            similarity_threshold: 相似度阈值，超过此值视为冗余。

        Returns:
            List[Dict]: 去重后的结果列表。
        """
        if len(exec_results) <= 1:
            return exec_results

        def _tokenize(text: str) -> set:
            # 按中文字符和空白分词
            tokens = set()
            for part in re.split(r"[\s，。！？、；：""（）\n]+", text):
                part = part.strip()
                if part:
                    # 对中文按2-gram切分
                    chars = list(part)
                    for i in range(len(chars)):
                        tokens.add(chars[i])
                        if i < len(chars) - 1:
                            tokens.add(chars[i] + chars[i + 1])
            return tokens

        results_with_tokens: List[Tuple[int, set, Dict[str, Any]]] = []
        for idx, result in enumerate(exec_results):
            text = result.get("result", "")
            results_with_tokens.append((idx, _tokenize(text), result))

        keep: List[Dict[str, Any]] = []
        suppressed: set = set()

        for idx, tokens, result in results_with_tokens:
            if idx in suppressed:
                continue
            keep.append(result)
            # 与后面所有结果比较
            for jdx, other_tokens, _other in results_with_tokens:
                if jdx <= idx or jdx in suppressed:
                    continue
                if not tokens or not other_tokens:
                    continue
                intersection = len(tokens & other_tokens)
                union = len(tokens | other_tokens)
                jaccard = intersection / union if union > 0 else 0.0
                if jaccard >= similarity_threshold:
                    # 标记较短者为冗余
                    this_len = len(result.get("result", ""))
                    other_len = len(_other[2].get("result", ""))
                    if this_len >= other_len:
                        suppressed.add(jdx)
                    else:
                        suppressed.add(idx)
                        keep.pop()  # 撤销刚加入的
                        break

        if len(suppressed) > 0:
            logger.info("冗余过滤: %d -> %d 条 (移除%d条冗余)", len(exec_results), len(keep), len(suppressed))
        return keep

    def _verify_citations(
        self,
        answer: str,
        exec_results: List[Dict[str, Any]],
        query: str,
    ) -> Tuple[str, bool]:
        """校验回答中的 [来源N] 引用是否真实有据。

        提取每个带引用的句子，对照来源文本验证是否被支持。
        一旦发现捏造会追加警告并返回。

        Args:
            answer: LLM 生成的回答文本。
            exec_results: 工具执行结果（含来源文本）。
            query: 用户查询。

        Returns:
            Tuple[str, bool]: (可能带警告的回答, 是否通过校验)。
        """
        # 提取带 [来源N] 标记的片段
        citation_pattern = re.findall(r"\[来源(\d+)\]", answer)
        if not citation_pattern:
            return answer, True

        # 构建来源索引
        source_map: Dict[int, str] = {}
        for i, result in enumerate(exec_results, start=1):
            text = result.get("result", "")
            if text:
                source_map[i] = text[:1500]

        # 对每句含引用的文字抽样校验（最多3句）
        sentences = re.split(r"[。！？\n]", answer)
        cited_sentences = [s for s in sentences if re.search(r"\[来源\d+\]", s)]
        if not cited_sentences:
            return answer, True

        violations: List[str] = []
        checked = 0
        for sentence in cited_sentences[:3]:
            refs = re.findall(r"\[来源(\d+)\]", sentence)
            source_texts: List[str] = []
            for ref in refs:
                src = source_map.get(int(ref), "")
                if src:
                    source_texts.append(src)

            if not source_texts:
                continue

            combined_sources = "\n---\n".join(source_texts)
            checked += 1

            try:
                response = self.llm_client.chat.completions.create(
                    model=config.llm_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是事实核查员。判断'陈述句'中的主张是否能从'来源文本'中推断出来。"
                                "只关注事实是否被来源支持，不考虑表述细节差异。"
                                "输出 JSON: {\"supported\": true/false, \"reason\": \"简短理由\"}"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"来源文本:\n{combined_sources}\n\n"
                                f"陈述句: {sentence}\n\n"
                                "该陈述能否从来源文本中推断出来？输出JSON:"
                            ),
                        },
                    ],
                    temperature=0.0,
                    max_tokens=128,
                )
                raw = response.choices[0].message.content or "{}"
                result = self._parse_json(raw)
                if not result.get("supported", True):
                    violations.append(
                        f"[来源{','.join(refs)}] {sentence[:80]}... — {result.get('reason', '未证实')}"
                    )
            except Exception as e:
                logger.error("引用校验失败: %s", e)

        if violations:
            warning = (
                "\n\n⚠️ 引用真实性提醒（以下陈述在来源中未找到充分依据）:\n"
                + "\n".join(f"- {v}" for v in violations)
            )
            logger.warning("引用校验: 发现 %d 处存疑引用/%d 处检查", len(violations), checked)
            return answer + warning, False

        logger.info("引用校验: %d 处引用检查通过", checked)
        return answer, True

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        """从 LLM 输出中解析 JSON 对象。"""
        import json as _json
        try:
            return _json.loads(raw.strip())
        except _json.JSONDecodeError:
            pass
        m = re.search(r"\{[^{}]*\}", raw)
        if m:
            try:
                return _json.loads(m.group(0))
            except _json.JSONDecodeError:
                pass
        return {}

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

    def _generate_answer_stream(
        self,
        query: str,
        exec_results: List[Dict[str, Any]],
        dialogue_context: str = "",
        long_term_context: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        """流式版本：逐 token yield LLM 生成的回答文本。

        Args:
            query: 用户查询（可能是改写后的）。
            exec_results: 所有工具执行结果。
            dialogue_context: 近期对话历史，用于多轮对话。
            long_term_context: 长期记忆中检索到的用户偏好。

        Yields:
            str: 每次 yield 一个文本 token。
        """
        # (压缩/过滤由调用方在外部完成，保证流式首 token 低延迟)
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
            "4. 无法确认的信息请明确说明\n"
            "5. 如果是多轮对话，自然引用前文提到的信息"
        )

        # 注入对话历史
        if dialogue_context:
            system_prompt += (
                f"\n\n近期对话历史（请参考上下文保持回答连贯）:\n{dialogue_context}"
            )

        # 注入长期记忆（用户偏好）
        if long_term_context:
            lt_text = "\n".join(f"- {m}" for m in long_term_context)
            system_prompt += (
                f"\n\n已知用户偏好/信息（可据此个性化回答）:\n{lt_text}"
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
                stream=True,
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            logger.error("流式答案生成失败: %s", e, exc_info=True)
            # 降级：非流式调用
            fallback = self._generate_answer(query, exec_results)
            yield fallback

    def _chat_reply_stream(self, user_input: str) -> Generator[str, None, None]:
        """流式版本闲聊回复。

        Args:
            user_input: 用户消息。

        Yields:
            str: 每次 yield 一个文本 token。
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
                stream=True,
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception:
            fallback = self._chat_reply(user_input)
            yield fallback

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


class AgentForRequest:
    """请求级 Agent — 无全局状态, 每次请求独立创建/销毁.

    使用外部注入的 LLMPool (异步连接池) 和 SessionMemory (Redis 后端),
    避免 AutoSalesAgent 的全局单例问题.

    Attributes:
        session: SessionMemory (从 Redis 加载).
        llm_pool: 异步 LLM 连接池.
        planning: 规划模块.
        reflection: 反思模块.
        executor: 执行器.
    """

    def __init__(
        self,
        session: "SessionMemory",       # type: ignore[name-defined] # noqa: F821
        llm_pool: "LLMPool",            # type: ignore[name-defined] # noqa: F821
        sync_llm: Optional[Any] = None,
        rag_tool: Any = None,
        web_search: Any = None,
        calculator: Any = None,
    ) -> None:
        from agent.memory import SessionMemory  # noqa: F811
        from infrastructure.llm_pool import LLMPool  # noqa: F811

        self.session = session
        self.llm_pool = llm_pool
        self.memory = session  # 统一接口别名

        # 同步 LLM 客户端 (OpenAI-compatible) — 用于 planning/reflection 及辅助方法
        self.llm_client = sync_llm

        # 核心模块 — 使用同步客户端 (planning/reflection 内部调用 chat.completions.create)
        self.planning = PlanningModule(llm_client=sync_llm)
        self.executor = Executor()
        self.reflection = ReflectionModule(llm_client=sync_llm)

        # 工具
        self.rag_tool = rag_tool
        self.web_search = web_search
        self.calculator = calculator

        if self.rag_tool and self.web_search and self.calculator:
            self.executor.register_tools([
                self.rag_tool, self.web_search, self.calculator,
            ])

    async def run_query(self, user_input: str) -> str:
        """异步执行完整 Agent 工作流."""
        logger.info("=" * 60)
        logger.info("[AgentForRequest] session=%s query=%s", self.session.session_id, user_input[:80])

        # 1. 存储用户查询
        self.session.add(user_input, content_type="user_query")

        # 2. 检索长期记忆
        long_term_context = self.session.search_long_term(user_input)

        # 3. 规划
        memory_ctx = self.session.get_context(max_entries=10)
        if long_term_context:
            lt_text = "长期记忆:\n" + "\n".join(f"- {m}" for m in long_term_context)
            memory_ctx = lt_text + "\n\n" + memory_ctx
        actions = self.planning.generate_action_plan(user_input, memory_ctx)

        if not actions:
            reply = await self._chat_reply(user_input)
            self.session.add(reply, content_type="final_answer")
            return reply

        # 4. 执行
        exec_results = self.executor.execute(actions)
        for result in exec_results:
            self.session.add(
                f"[{result['tool']}] {result['result'][:500]}",
                content_type="tool_result",
            )

        # 5. 生成答案
        filtered_results = self._filter_redundant_results(
            self._compress_contexts(user_input, exec_results)
        )
        current_answer = await self._generate_answer(
            user_input, filtered_results,
            dialogue_context=self.session.get_dialogue_for_answer_context(),
            long_term_context=long_term_context,
        )

        # 6. 反思迭代
        self.reflection.reset()
        for _ in range(config.reflection_max_iterations):
            should_continue, new_actions = self.reflection.evaluate_and_refine(
                query=user_input,
                current_answer=current_answer,
                memory_context=self.session.get_context(),
            )
            if not should_continue or not new_actions:
                break

            supplement_results = self.executor.execute(new_actions)
            for result in supplement_results:
                self.session.add(
                    f"[补充-{result['tool']}] {result['result'][:500]}",
                    content_type="tool_result",
                )
            all_results = exec_results + supplement_results
            filtered_all = self._filter_redundant_results(
                self._compress_contexts(user_input, all_results)
            )
            current_answer = await self._generate_answer(
                user_input, filtered_all,
                dialogue_context=self.session.get_dialogue_for_answer_context(),
                long_term_context=long_term_context,
            )

        # 7. 保存
        self.session.add(current_answer, content_type="final_answer")
        return current_answer

    async def _generate_answer(
        self,
        query: str,
        exec_results: List[Dict[str, Any]],
        dialogue_context: str = "",
        long_term_context: Optional[List[str]] = None,
    ) -> str:
        """异步生成答案 (使用 LLMPool)."""
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
            "4. 无法确认的信息请明确说明\n"
            "5. 如果是多轮对话，自然引用前文提到的信息"
        )
        if dialogue_context:
            system_prompt += f"\n\n近期对话历史:\n{dialogue_context}"
        if long_term_context:
            lt_text = "\n".join(f"- {m}" for m in long_term_context)
            system_prompt += f"\n\n已知用户偏好:\n{lt_text}"

        try:
            answer = await self.llm_pool.chat(
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
            return answer
        except Exception as e:
            logger.error("答案生成失败: %s", e)
            return f"（LLM 调用失败，以下为检索到的原始信息）\n\n{context_text}"

    async def _chat_reply(self, user_input: str) -> str:
        """闲聊回复."""
        try:
            return await self.llm_pool.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位友好的汽车销售培训助手。",
                    },
                    {"role": "user", "content": user_input},
                ],
                temperature=0.7,
                max_tokens=512,
            )
        except Exception:
            return "您好！我是汽车销售培训助手，请问有什么可以帮您的？"

    # 复用 AutoSalesAgent 的辅助方法
    _compress_contexts = AutoSalesAgent._compress_contexts
    _filter_redundant_results = AutoSalesAgent._filter_redundant_results
    _verify_citations = AutoSalesAgent._verify_citations
    _parse_json = AutoSalesAgent._parse_json

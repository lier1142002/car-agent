"""
RAG 评测核心指标计算模块。

覆盖检索质量和生成质量两个维度：
- 检索: Context Relevance, Context Recall, MRR, NDCG
- 生成: Faithfulness (幻觉检测), Answer Relevance

支持两种评估模式:
1. LLM-as-a-Judge: 需要 API 调用，精度高，适合定性指标
2. 确定性计算: 基于标注数据集直接计算，适合 MRR/NDCG/Recall
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from config import config
from eval.prompts import (
    ANSWER_RELEVANCE,
    CONTEXT_RELEVANCE,
    FAITHFULNESS_CLAIM_EXTRACTION,
    FAITHFULNESS_ENTAILMENT,
)

logger = logging.getLogger(__name__)


class LLMJudge:
    """LLM-as-a-Judge 通用评估器。

    封装 LLM 调用、JSON 解析和重试逻辑，
    供 Faithfulness、Context Relevance 等指标复用。

    Attributes:
        client: OpenAI 兼容的 LLM 客户端。
        model: 模型名称（默认使用配置中的主模型）。
        max_retries: JSON 解析失败时的最大重试次数。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.client = OpenAI(
            api_key=api_key or config.llm_api_key,
            base_url=api_url or config.llm_api_url,
        )
        self.model = model or config.llm_model
        self.max_retries = 2

    def judge(
        self,
        prompt: str,
        system: str = "你是一个严格的质量评估专家。请始终以有效的 JSON 格式返回结果。",
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """调用 LLM 进行评估并解析 JSON 返回。

        Args:
            prompt: 评估提示词。
            system: 系统指令。
            temperature: 生成温度（评测应设为 0 以保持一致性）。

        Returns:
            Dict: 解析后的 JSON 评估结果。
        """
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=1024,
                )
                raw = response.choices[0].message.content or "{}"
                return self._parse_json(raw)
            except json.JSONDecodeError:
                logger.warning("JSON 解析失败 (尝试 %d/%d)", attempt + 1, self.max_retries)
                if attempt == self.max_retries:
                    return {}
            except Exception as e:
                logger.error("LLM 评估调用失败: %s", e)
                return {}
        return {}

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        """从 LLM 输出中提取 JSON 对象。"""
        raw = raw.strip()
        # 直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 从 markdown 代码块提取
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            return json.loads(match.group(1).strip())
        # 提取第一个 { } 包裹的 JSON
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return json.loads(match.group(0))
        raise json.JSONDecodeError("无法提取 JSON", raw, 0)


# ---------------------------------------------------------------------------
# 检索质量指标
# ---------------------------------------------------------------------------


def context_relevance(
    query: str,
    retrieved_chunks: List[str],
    judge: Optional[LLMJudge] = None,
) -> Dict[str, Any]:
    """评估检索上下文的相关性 (Context Relevance)。

    对每个检索到的文档块，使用 LLM 判断其是否与查询相关。
    得分 = 相关块数 / 总块数，范围 [0, 1]。

    Args:
        query: 用户查询文本。
        retrieved_chunks: 检索到的文档块文本列表。
        judge: LLM 评估器实例。

    Returns:
        Dict: {"score": float, "per_chunk": List[Dict], "relevant_count": int, "total_count": int}
    """
    if not retrieved_chunks:
        return {"score": 0.0, "per_chunk": [], "relevant_count": 0, "total_count": 0}

    if judge is None:
        judge = LLMJudge()

    per_chunk_results = []
    relevant_count = 0

    for i, chunk in enumerate(retrieved_chunks):
        prompt = CONTEXT_RELEVANCE.format(query=query, chunk=chunk[:1000])
        result = judge.judge(prompt)
        is_relevant = result.get("relevant", False)
        if is_relevant:
            relevant_count += 1
        per_chunk_results.append({
            "index": i,
            "relevant": is_relevant,
            "reason": result.get("reason", ""),
        })

    total = len(retrieved_chunks)
    score = relevant_count / total if total > 0 else 0.0

    return {
        "score": round(score, 4),
        "per_chunk": per_chunk_results,
        "relevant_count": relevant_count,
        "total_count": total,
    }


def context_recall(
    ground_truth_chunks: List[str],
    retrieved_chunks: List[str],
    fuzzy: bool = True,
) -> Dict[str, Any]:
    """计算上下文召回率 (Context Recall)。

    衡量标注的正样本文档中有多少被检索到。
    使用文本重叠度（Jaccard 或 token 重叠）做近似匹配。

    Args:
        ground_truth_chunks: 标注的正确答案来源文档块文本。
        retrieved_chunks: 检索到的文档块文本。
        fuzzy: 是否使用模糊匹配（token 重叠），否则使用完全匹配。

    Returns:
        Dict: {"score": float, "matched": int, "total_gt": int}
    """
    if not ground_truth_chunks:
        return {"score": 1.0, "matched": 0, "total_gt": 0}

    matched = 0
    match_details = []

    for gt in ground_truth_chunks:
        best_overlap = 0.0
        best_match_idx = -1

        for i, ret in enumerate(retrieved_chunks):
            overlap = _text_overlap(gt, ret) if fuzzy else (1.0 if gt.strip() == ret.strip() else 0.0)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match_idx = i

        is_matched = best_overlap >= 0.3  # 阈值可调
        if is_matched:
            matched += 1
        match_details.append({
            "gt_chunk_preview": gt[:100],
            "best_match_idx": best_match_idx,
            "overlap": round(best_overlap, 4),
            "matched": is_matched,
        })

    score = matched / len(ground_truth_chunks)
    return {
        "score": round(score, 4),
        "matched": matched,
        "total_gt": len(ground_truth_chunks),
        "details": match_details,
    }


def mrr(
    queries_retrieved: List[Tuple[str, List[str]]],
    ground_truth_chunks_map: Dict[str, List[str]],
    fuzzy: bool = True,
) -> Dict[str, Any]:
    """计算 Mean Reciprocal Rank (MRR)。

    MRR = (1/N) * Σ(1/rank_i)
    其中 rank_i 是第一个相关文档在检索结果中的排名位置（从 1 开始）。

    Args:
        queries_retrieved: [(query, [retrieved_chunk_text, ...]), ...]
        ground_truth_chunks_map: {query: [gt_chunk_text, ...]}
        fuzzy: 是否使用模糊匹配。

    Returns:
        Dict: {"score": float, "per_query": List[Dict]}
    """
    per_query = []
    reciprocal_ranks = []

    for query, retrieved in queries_retrieved:
        gt_chunks = ground_truth_chunks_map.get(query, [])
        if not gt_chunks or not retrieved:
            per_query.append({"query": query, "rr": 0.0, "first_relevant_rank": None})
            reciprocal_ranks.append(0.0)
            continue

        first_rank = None
        for rank, ret_chunk in enumerate(retrieved, start=1):
            # 检查是否与任一 ground truth 匹配
            for gt in gt_chunks:
                overlap = _text_overlap(gt, ret_chunk) if fuzzy else (1.0 if gt.strip() == ret_chunk.strip() else 0.0)
                if overlap >= 0.3:
                    first_rank = rank
                    break
            if first_rank is not None:
                break

        rr = 1.0 / first_rank if first_rank else 0.0
        reciprocal_ranks.append(rr)
        per_query.append({
            "query": query[:100],
            "rr": round(rr, 4),
            "first_relevant_rank": first_rank,
        })

    score = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0
    return {"score": round(score, 4), "per_query": per_query}


def ndcg(
    queries_retrieved: List[Tuple[str, List[str]]],
    ground_truth_chunks_map: Dict[str, List[str]],
    k: int = 5,
    fuzzy: bool = True,
) -> Dict[str, Any]:
    """计算 Normalized Discounted Cumulative Gain (NDCG@k)。

    使用二值相关性标签（1=相关，0=不相关），
    DCG = Σ(rel_i / log2(i+1))，IDCG 为理想排序下的 DCG。

    Args:
        queries_retrieved: [(query, [retrieved_chunk_text, ...]), ...]
        ground_truth_chunks_map: {query: [gt_chunk_text, ...]}
        k: 截断位置。
        fuzzy: 是否使用模糊匹配。

    Returns:
        Dict: {"score": float, "per_query": List[Dict]}
    """
    per_query = []
    ndcg_scores = []

    for query, retrieved in queries_retrieved:
        gt_chunks = ground_truth_chunks_map.get(query, [])
        if not gt_chunks or not retrieved:
            per_query.append({"query": query, f"ndcg@{k}": 0.0})
            ndcg_scores.append(0.0)
            continue

        # 计算相关性 labels（二值：1 或 0）
        retrieved_k = retrieved[:k]
        relevance = []
        for ret_chunk in retrieved_k:
            is_rel = any(
                _text_overlap(gt, ret_chunk) >= 0.3 for gt in gt_chunks
            )
            relevance.append(1 if is_rel else 0)

        # DCG
        dcg = 0.0
        for i, rel in enumerate(relevance, start=1):
            dcg += rel / math.log2(i + 1)

        # IDCG（理想情况：所有相关文档排在最前面）
        ideal_rel = sorted(relevance, reverse=True)
        idcg = 0.0
        for i, rel in enumerate(ideal_rel, start=1):
            idcg += rel / math.log2(i + 1)

        ndcg_val = dcg / idcg if idcg > 0 else 0.0
        ndcg_scores.append(ndcg_val)
        per_query.append({
            "query": query[:100],
            f"ndcg@{k}": round(ndcg_val, 4),
            "dcg": round(dcg, 4),
            "idcg": round(idcg, 4),
            "relevance": relevance,
        })

    score = sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0
    return {"score": round(score, 4), "per_query": per_query}


# ---------------------------------------------------------------------------
# 生成质量指标
# ---------------------------------------------------------------------------


def faithfulness(
    answer: str,
    context_chunks: List[str],
    judge: Optional[LLMJudge] = None,
) -> Dict[str, Any]:
    """评估答案忠实度 (Faithfulness / 幻觉检测)。

    分两步:
    1. 从生成回答中提取所有事实性陈述 (claims)
    2. 对每个 claim，检查是否能从检索上下文中推断出来

    Faithfulness = supported_claims / total_claims

    Args:
        answer: 生成的回答文本。
        context_chunks: 用于生成回答的检索上下文块列表。
        judge: LLM 评估器实例。

    Returns:
        Dict: {"score": float, "total_claims": int, "supported": int,
               "contradicted": int, "unsupported": int, "per_claim": List[Dict]}
    """
    if judge is None:
        judge = LLMJudge()

    # Step 1: 提取 claims
    extraction_prompt = FAITHFULNESS_CLAIM_EXTRACTION.format(answer=answer)
    extraction_result = judge.judge(extraction_prompt)
    claims = extraction_result.get("claims", [])

    if not claims:
        return {
            "score": 1.0,
            "total_claims": 0,
            "supported": 0,
            "contradicted": 0,
            "unsupported": 0,
            "per_claim": [],
        }

    # Step 2: 逐条核查每条 claim
    context_text = "\n\n---\n\n".join(
        f"[{i+1}] {chunk}" for i, chunk in enumerate(context_chunks)
    )

    supported = 0
    contradicted = 0
    unsupported = 0
    per_claim = []

    for claim in claims:
        entailment_prompt = FAITHFULNESS_ENTAILMENT.format(
            context=context_text[:6000],  # 截断以控制 token 消耗
            claim=claim,
        )
        result = judge.judge(entailment_prompt)
        verdict = result.get("verdict", "unsupported")

        if verdict == "supported":
            supported += 1
        elif verdict == "contradicted":
            contradicted += 1
        else:
            unsupported += 1

        per_claim.append({
            "claim": claim,
            "verdict": verdict,
            "reason": result.get("reason", ""),
        })

    total = len(claims)
    score = supported / total if total > 0 else 1.0

    return {
        "score": round(score, 4),
        "total_claims": total,
        "supported": supported,
        "contradicted": contradicted,
        "unsupported": unsupported,
        "hallucination_rate": round(1.0 - score, 4),
        "per_claim": per_claim,
    }


def answer_relevance(
    query: str,
    answer: str,
    judge: Optional[LLMJudge] = None,
) -> Dict[str, Any]:
    """评估回答相关性 (Answer Relevance)。

    使用 LLM 对回答与问题的相关程度进行 1-5 评分，
    归一化到 [0, 1] 区间。

    Args:
        query: 用户查询文本。
        answer: 生成的回答文本。
        judge: LLM 评估器实例。

    Returns:
        Dict: {"score": float, "raw_score": int, "reason": str}
    """
    if judge is None:
        judge = LLMJudge()

    prompt = ANSWER_RELEVANCE.format(query=query, answer=answer)
    result = judge.judge(prompt)

    raw_score = result.get("score", 1)
    # 归一化：1-5 → 0-1
    normalized = (raw_score - 1) / 4 if isinstance(raw_score, (int, float)) else 0.0

    return {
        "score": round(max(0.0, min(1.0, normalized)), 4),
        "raw_score": raw_score,
        "reason": result.get("reason", ""),
    }


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------


def _text_overlap(a: str, b: str) -> float:
    """计算两个文本的 token 级 Jaccard 相似度。

    用于模糊匹配检索结果与 ground truth 文本块。

    Args:
        a: 文本 A。
        b: 文本 B。

    Returns:
        float: Jaccard 相似度 [0, 1]。
    """
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _tokenize_for_recall(text: str) -> List[str]:
    """将文本按常见分隔符分词（用于中文混合文本的召回匹配）。"""
    import re as _re
    # 中文字符单独切分，英文按空格
    tokens = []
    for part in _re.split(r"(\s+)", text):
        # 对非空白部分，中文字符单独切出
        sub_parts = _re.findall(r"[一-鿿]|[^一-鿿\s]+", part)
        tokens.extend(sp for sp in sub_parts if sp.strip())
    return tokens

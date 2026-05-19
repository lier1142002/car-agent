"""
RAG 评测运行器模块。

提供批量和参数扫描评测能力，协调检索管道、
指标计算和结果聚合，输出结构化评测报告。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from eval.dataset import EvalSample, GoldenDataset
from eval.metrics import (
    LLMJudge,
    answer_relevance,
    context_recall,
    context_relevance,
    faithfulness,
    mrr,
    ndcg,
)

logger = logging.getLogger(__name__)

# 混合检索权重扫描默认范围
DEFAULT_WEIGHT_SWEEP = [
    (1.0, 0.3),
    (1.0, 0.5),
    (1.0, 0.7),
    (1.0, 1.0),
    (0.5, 1.0),
    (0.7, 1.0),
]


@dataclass
class SampleResult:
    """单条样本的完整评测结果。"""

    query: str
    ground_truth: str
    retrieved_chunks: List[str] = field(default_factory=list)
    retrieved_scores: List[float] = field(default_factory=list)
    generated_answer: str = ""

    # 检索指标
    context_relevance_score: float = 0.0
    context_recall_score: float = 0.0
    mrr_value: float = 0.0
    ndcg_value: float = 0.0

    # 生成指标
    faithfulness_score: float = 0.0
    hallucination_rate: float = 0.0
    answer_relevance_score: float = 0.0

    # 性能
    retrieval_latency_ms: float = 0.0
    generation_latency_ms: float = 0.0

    # 详细信息
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "ground_truth": self.ground_truth,
            "retrieved_chunks": self.retrieved_chunks,
            "retrieved_scores": self.retrieved_scores,
            "generated_answer": self.generated_answer,
            "context_relevance": self.context_relevance_score,
            "context_recall": self.context_recall_score,
            "mrr": self.mrr_value,
            "ndcg": self.ndcg_value,
            "faithfulness": self.faithfulness_score,
            "hallucination_rate": self.hallucination_rate,
            "answer_relevance": self.answer_relevance_score,
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "generation_latency_ms": self.generation_latency_ms,
            "details": self.details,
        }


@dataclass
class EvalReport:
    """批次评测聚合报告。"""

    dataset_name: str
    total_samples: int
    retrieval_mode: str
    config: Dict[str, Any] = field(default_factory=dict)

    # 检索质量聚合
    avg_context_relevance: float = 0.0
    avg_context_recall: float = 0.0
    avg_mrr: float = 0.0
    avg_ndcg: float = 0.0

    # 生成质量聚合
    avg_faithfulness: float = 0.0
    avg_hallucination_rate: float = 0.0
    avg_answer_relevance: float = 0.0

    # 性能聚合
    avg_retrieval_latency_ms: float = 0.0
    avg_generation_latency_ms: float = 0.0
    p95_retrieval_latency_ms: float = 0.0
    p95_generation_latency_ms: float = 0.0

    # 明细
    per_sample: List[SampleResult] = field(default_factory=list)
    failed_samples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "total_samples": self.total_samples,
            "retrieval_mode": self.retrieval_mode,
            "config": self.config,
            "retrieval_quality": {
                "context_relevance": self.avg_context_relevance,
                "context_recall": self.avg_context_recall,
                "mrr": self.avg_mrr,
                "ndcg": self.avg_ndcg,
            },
            "generation_quality": {
                "faithfulness": self.avg_faithfulness,
                "hallucination_rate": self.avg_hallucination_rate,
                "answer_relevance": self.avg_answer_relevance,
            },
            "performance": {
                "avg_retrieval_latency_ms": self.avg_retrieval_latency_ms,
                "avg_generation_latency_ms": self.avg_generation_latency_ms,
                "p95_retrieval_latency_ms": self.p95_retrieval_latency_ms,
                "p95_generation_latency_ms": self.p95_generation_latency_ms,
            },
            "failed_samples": self.failed_samples,
            "per_sample": [s.to_dict() for s in self.per_sample],
        }


class EvalRunner:
    """RAG 评测批量运行器。

    协调检索管道和评估指标，对数据集中的每条样本
    执行检索→生成→评估的全流程，并输出聚合报告。

    使用方式:
        from tools.rag_tool import RAGTool
        from eval.dataset import GoldenDataset
        from eval.runner import EvalRunner

        rag = RAGTool()
        rag.index_documents("product.pdf")

        ds = GoldenDataset.load("eval/datasets/my_dataset.json")
        runner = EvalRunner(rag)
        report = runner.run(ds, retrieval_mode="hybrid", generate_answers=True)
        print(f"Faithfulness: {report.avg_faithfulness:.2%}")

    Attributes:
        rag_tool: RAG 工具实例（提供检索和生成能力）。
        judge: LLM-as-a-Judge 评估器。
        top_k: 检索返回数量。
    """

    def __init__(
        self,
        rag_tool: Any,  # RAGTool 实例（避免硬导入，支持 mock）
        judge: Optional[LLMJudge] = None,
        top_k: int = 5,
    ) -> None:
        self.rag_tool = rag_tool
        self.judge = judge or LLMJudge()
        self.top_k = top_k

    # ------------------------------------------------------------------
    # 主评测接口
    # ------------------------------------------------------------------

    def run(
        self,
        dataset: GoldenDataset,
        retrieval_mode: str = "hybrid",
        generate_answers: bool = True,
        retrieval_metrics_only: bool = False,
        dense_weight: float = 1.0,
        sparse_weight: float = 0.7,
    ) -> EvalReport:
        """对数据集执行批量评测。

        Args:
            dataset: 黄金评测数据集。
            retrieval_mode: 检索模式 ("dense" / "sparse" / "hybrid")。
            generate_answers: 是否调用 LLM 生成回答（关闭则只评检索质量）。
            retrieval_metrics_only: 仅在检索结果上计算指标，不执行 LLM-as-a-Judge。
            dense_weight: 混合检索中的稠密权重。
            sparse_weight: 混合检索中的稀疏权重。

        Returns:
            EvalReport: 聚合评测报告。
        """
        logger.info(
            "开始 RAG 评测: dataset=%s, samples=%d, mode=%s",
            dataset.name,
            len(dataset),
            retrieval_mode,
        )

        per_sample: List[SampleResult] = []
        failed: List[str] = []

        for i, sample in enumerate(dataset):
            logger.info("评测进度: %d/%d - %s", i + 1, len(dataset), sample.query[:60])
            try:
                result = self._evaluate_sample(
                    sample,
                    retrieval_mode=retrieval_mode,
                    generate_answers=generate_answers,
                    retrieval_metrics_only=retrieval_metrics_only,
                    dense_weight=dense_weight,
                    sparse_weight=sparse_weight,
                )
                per_sample.append(result)
            except Exception as e:
                logger.error("样本评测失败: %s - %s", sample.query[:60], e)
                failed.append(sample.query)

        report = self._aggregate(
            dataset=dataset,
            per_sample=per_sample,
            failed=failed,
            retrieval_mode=retrieval_mode,
            config={
                "dense_weight": dense_weight,
                "sparse_weight": sparse_weight,
                "top_k": self.top_k,
                "generate_answers": generate_answers,
            },
        )
        logger.info("评测完成: Faithfulness=%.3f, Recall=%.3f", report.avg_faithfulness, report.avg_context_recall)
        return report

    def sweep_weights(
        self,
        dataset: GoldenDataset,
        weight_configs: Optional[List[Tuple[float, float]]] = None,
        generate_answers: bool = False,
    ) -> List[EvalReport]:
        """混合检索权重扫描评测。

        对多组 (dense_weight, sparse_weight) 组合分别评测，
        用于找到最优的权重配比。

        Args:
            dataset: 评测数据集。
            weight_configs: 权重组合列表，默认使用预定义范围。
            generate_answers: 是否生成回答（扫描通常关闭以加速）。

        Returns:
            List[EvalReport]: 每组权重的评测报告。
        """
        configs = weight_configs or DEFAULT_WEIGHT_SWEEP
        reports: List[EvalReport] = []

        for dw, sw in configs:
            logger.info("--- 权重扫描: dense=%.1f, sparse=%.1f ---", dw, sw)
            report = self.run(
                dataset,
                retrieval_mode="hybrid",
                generate_answers=generate_answers,
                dense_weight=dw,
                sparse_weight=sw,
            )
            reports.append(report)

        return reports

    # ------------------------------------------------------------------
    # 单样本评测
    # ------------------------------------------------------------------

    def _evaluate_sample(
        self,
        sample: EvalSample,
        retrieval_mode: str,
        generate_answers: bool,
        retrieval_metrics_only: bool,
        dense_weight: float,
        sparse_weight: float,
    ) -> SampleResult:
        """评测单条样本的完整流程。"""
        result = SampleResult(
            query=sample.query,
            ground_truth=sample.ground_truth,
        )

        # ---- Step 1: 检索 ----
        t0 = time.perf_counter()
        docs = self._retrieve(
            sample.query,
            mode=retrieval_mode,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
        )
        result.retrieval_latency_ms = (time.perf_counter() - t0) * 1000

        retrieved_texts = [d["text"] for d in docs]
        retrieved_scores = [d.get("score", 0.0) for d in docs]
        result.retrieved_chunks = retrieved_texts
        result.retrieved_scores = retrieved_scores

        # ---- Step 2: 检索质量指标（确定性计算，不需要 LLM） ----
        # Context Recall
        if sample.relevant_chunks:
            recall_result = context_recall(
                sample.relevant_chunks,
                retrieved_texts,
            )
            result.context_recall_score = recall_result["score"]
            result.details["context_recall"] = recall_result

        # Context Relevance (LLM)
        if not retrieval_metrics_only and retrieved_texts:
            rel_result = context_relevance(
                sample.query,
                retrieved_texts,
                judge=self.judge,
            )
            result.context_relevance_score = rel_result["score"]
            result.details["context_relevance"] = rel_result

        # ---- Step 3: 生成回答 ----
        if generate_answers and docs:
            t0 = time.perf_counter()
            answer = self.rag_tool.generate_answer(sample.query, docs)
            result.generation_latency_ms = (time.perf_counter() - t0) * 1000
            result.generated_answer = answer

            # ---- Step 4: 生成质量指标 ----
            if not retrieval_metrics_only and answer:
                # Faithfulness
                faith_result = faithfulness(
                    answer,
                    retrieved_texts,
                    judge=self.judge,
                )
                result.faithfulness_score = faith_result["score"]
                result.hallucination_rate = faith_result.get("hallucination_rate", 0.0)
                result.details["faithfulness"] = faith_result

                # Answer Relevance
                ans_rel_result = answer_relevance(
                    sample.query,
                    answer,
                    judge=self.judge,
                )
                result.answer_relevance_score = ans_rel_result["score"]
                result.details["answer_relevance"] = ans_rel_result

        return result

    def _retrieve(
        self,
        query: str,
        mode: str,
        dense_weight: float,
        sparse_weight: float,
    ) -> List[Dict[str, Any]]:
        """根据模式执行检索。

        Args:
            query: 查询文本。
            mode: "dense" / "sparse" / "hybrid"。
            dense_weight: 混合检索稠密权重。
            sparse_weight: 混合检索稀疏权重。

        Returns:
            List[Dict]: 检索结果。
        """
        if mode == "dense":
            dense, _ = self.rag_tool.embedding.encode_text(query)
            return self.rag_tool.vector_db.search_dense(dense, top_k=self.top_k)
        elif mode == "sparse":
            _, sparse = self.rag_tool.embedding.encode_text(query)
            return self.rag_tool.vector_db.search_sparse(sparse, top_k=self.top_k)
        else:  # hybrid
            return self.rag_tool.hybrid_retrieve(query, top_k=self.top_k)
            # 注意: hybrid_retrieve 内部使用 config 中的权重，
            # 如需重载权重，需直接调用 vector_db.hybrid_search

    # ------------------------------------------------------------------
    # 聚合计算
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        dataset: GoldenDataset,
        per_sample: List[SampleResult],
        failed: List[str],
        retrieval_mode: str,
        config: Dict[str, Any],
    ) -> EvalReport:
        """聚合所有样本的评测结果为最终报告。"""
        n = len(per_sample)
        if n == 0:
            return EvalReport(
                dataset_name=dataset.name,
                total_samples=0,
                retrieval_mode=retrieval_mode,
                config=config,
            )

        def _safe_mean(values: List[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        def _percentile(values: List[float], p: float) -> float:
            if not values:
                return 0.0
            sorted_vals = sorted(values)
            k = (len(sorted_vals) - 1) * p / 100
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return sorted_vals[int(k)]
            return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)

        import math

        report = EvalReport(
            dataset_name=dataset.name,
            total_samples=n,
            retrieval_mode=retrieval_mode,
            config=config,
            per_sample=per_sample,
            failed_samples=failed,
        )

        # 检索质量聚合
        report.avg_context_relevance = round(
            _safe_mean([s.context_relevance_score for s in per_sample]), 4
        )
        report.avg_context_recall = round(
            _safe_mean([s.context_recall_score for s in per_sample]), 4
        )

        # 全局 MRR 和 NDCG 需要重新计算（跨所有 query）
        queries_results = [
            (s.query, s.retrieved_chunks) for s in per_sample
        ]
        gt_chunks_map = {
            s.query: [s.ground_truth] for s in per_sample
        }
        # 同时使用 relevant_chunks 丰富 ground truth
        for s in per_sample:
            dataset_sample = next(
                (ds for ds in dataset if ds.query == s.query), None
            )
            if dataset_sample and dataset_sample.relevant_chunks:
                gt_chunks_map[s.query] = dataset_sample.relevant_chunks

        mrr_result = mrr(queries_results, gt_chunks_map)
        ndcg_result = ndcg(queries_results, gt_chunks_map, k=self.top_k)
        report.avg_mrr = round(mrr_result["score"], 4)
        report.avg_ndcg = round(ndcg_result["score"], 4)

        # 生成质量聚合
        report.avg_faithfulness = round(
            _safe_mean([s.faithfulness_score for s in per_sample]), 4
        )
        report.avg_hallucination_rate = round(
            _safe_mean([s.hallucination_rate for s in per_sample]), 4
        )
        report.avg_answer_relevance = round(
            _safe_mean([s.answer_relevance_score for s in per_sample]), 4
        )

        # 性能聚合
        report.avg_retrieval_latency_ms = round(
            _safe_mean([s.retrieval_latency_ms for s in per_sample]), 2
        )
        report.avg_generation_latency_ms = round(
            _safe_mean([s.generation_latency_ms for s in per_sample]), 2
        )
        report.p95_retrieval_latency_ms = round(
            _percentile([s.retrieval_latency_ms for s in per_sample], 95), 2
        )
        report.p95_generation_latency_ms = round(
            _percentile([s.generation_latency_ms for s in per_sample], 95), 2
        )

        return report

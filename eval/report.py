"""
评测结果报告模块。

将 EvalReport 输出为多种格式:
- JSON: 完整结构化数据，适合程序化分析
- CSV: 表格形式，适合 Excel/Google Sheets
- CLI Table: 终端友好的文本表格，适合快速查看
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from eval.runner import EvalReport

logger = logging.getLogger(__name__)

DEFAULT_REPORT_DIR = Path(__file__).parent / "reports"


def save_report_json(
    report: EvalReport,
    filepath: Optional[Path] = None,
) -> Path:
    """将评测报告保存为 JSON 文件。

    Args:
        report: 评测报告。
        filepath: 输出路径（默认自动生成时间戳文件名）。

    Returns:
        Path: 实际保存路径。
    """
    filepath = filepath or _generate_filename(report, "json")
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("JSON 报告已保存: %s", filepath)
    return filepath


def save_report_csv(
    report: EvalReport,
    filepath: Optional[Path] = None,
    include_details: bool = False,
) -> Path:
    """将评测报告保存为 CSV 文件。

    每行代表一条样本的评测结果，方便在 Excel 中分析。

    Args:
        report: 评测报告。
        filepath: 输出路径（默认自动生成）。
        include_details: 是否包含详细结果列。

    Returns:
        Path: 实际保存路径。
    """
    filepath = filepath or _generate_filename(report, "csv")
    filepath.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "query",
        "ground_truth",
        "context_relevance",
        "context_recall",
        "mrr",
        "ndcg",
        "faithfulness",
        "hallucination_rate",
        "answer_relevance",
        "retrieval_latency_ms",
        "generation_latency_ms",
    ]
    if include_details:
        fieldnames.extend([
            "retrieved_chunks_count",
            "generated_answer_preview",
        ])

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for s in report.per_sample:
            row = {
                "query": s.query,
                "ground_truth": s.ground_truth[:200],
                "context_relevance": s.context_relevance_score,
                "context_recall": s.context_recall_score,
                "mrr": s.mrr_value,
                "ndcg": s.ndcg_value,
                "faithfulness": s.faithfulness_score,
                "hallucination_rate": s.hallucination_rate,
                "answer_relevance": s.answer_relevance_score,
                "retrieval_latency_ms": round(s.retrieval_latency_ms, 2),
                "generation_latency_ms": round(s.generation_latency_ms, 2),
            }
            if include_details:
                row["retrieved_chunks_count"] = len(s.retrieved_chunks)
                row["generated_answer_preview"] = s.generated_answer[:150]
            writer.writerow(row)

    # 写入汇总行
    with open(filepath, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([])
        writer.writerow(["=== 汇总统计 ===", "", "", "", "", "", "", "", "", "", ""])
        writer.writerow([
            "指标", "avg_context_relevance", "avg_context_recall", "avg_mrr",
            "avg_ndcg", "avg_faithfulness", "avg_hallucination_rate",
            "avg_answer_relevance", "avg_retrieval_latency_ms",
            "avg_generation_latency_ms", "",
        ])
        writer.writerow([
            "平均值",
            report.avg_context_relevance,
            report.avg_context_recall,
            report.avg_mrr,
            report.avg_ndcg,
            report.avg_faithfulness,
            report.avg_hallucination_rate,
            report.avg_answer_relevance,
            report.avg_retrieval_latency_ms,
            report.avg_generation_latency_ms,
            "",
        ])

    logger.info("CSV 报告已保存: %s", filepath)
    return filepath


def print_report_table(report: EvalReport, file=sys.stdout) -> None:
    """在终端打印格式化的评测摘要表格。

    使用 Unicode 框线字符绘制表格，适合在 CLI 中快速查看结果。

    Args:
        report: 评测报告。
        file: 输出流（默认 stdout）。
    """
    print("\n" + "=" * 70, file=file)
    print(f"  RAG 评测报告: {report.dataset_name}", file=file)
    print(f"  检索模式: {report.retrieval_mode}  |  配置: {report.config}", file=file)
    print(f"  样本数: {report.total_samples}  |  失败数: {len(report.failed_samples)}", file=file)
    print("=" * 70, file=file)

    # 检索质量
    print("\n  ┌─────────────────────────────────────────────────┐", file=file)
    print(  "  │           检索质量 (Retrieval Quality)          │", file=file)
    print(  "  ├──────────────────────┬──────────────────────────┤", file=file)
    print(f"  │ Context Relevance    │ {_bar(report.avg_context_relevance)} {report.avg_context_relevance:.2%} │", file=file)
    print(f"  │ Context Recall       │ {_bar(report.avg_context_recall)} {report.avg_context_recall:.2%} │", file=file)
    print(f"  │ MRR                  │ {_bar(report.avg_mrr)} {report.avg_mrr:.2%} │", file=file)
    print(f"  │ NDCG@{report.config.get('top_k', 5)}              │ {_bar(report.avg_ndcg)} {report.avg_ndcg:.2%} │", file=file)
    print(  "  └──────────────────────┴──────────────────────────┘", file=file)

    # 生成质量
    print("\n  ┌─────────────────────────────────────────────────┐", file=file)
    print(  "  │          生成质量 (Generation Quality)           │", file=file)
    print(  "  ├──────────────────────┬──────────────────────────┤", file=file)
    print(f"  │ Faithfulness         │ {_bar(report.avg_faithfulness)} {report.avg_faithfulness:.2%} │", file=file)
    print(f"  │ Hallucination Rate   │ {_bar(report.avg_hallucination_rate, reverse=True)} {report.avg_hallucination_rate:.2%} │", file=file)
    print(f"  │ Answer Relevance     │ {_bar(report.avg_answer_relevance)} {report.avg_answer_relevance:.2%} │", file=file)
    print(  "  └──────────────────────┴──────────────────────────┘", file=file)

    # 性能
    print("\n  ┌─────────────────────────────────────────────────┐", file=file)
    print(  "  │              性能 (Performance)                  │", file=file)
    print(  "  ├──────────────────────┬──────────────────────────┤", file=file)
    print(f"  │ 检索延迟 (avg)       │ {report.avg_retrieval_latency_ms:.1f} ms", file=file)
    print(f"  │ 检索延迟 (P95)       │ {report.p95_retrieval_latency_ms:.1f} ms", file=file)
    print(f"  │ 生成延迟 (avg)       │ {report.avg_generation_latency_ms:.1f} ms", file=file)
    print(f"  │ 生成延迟 (P95)       │ {report.p95_generation_latency_ms:.1f} ms", file=file)
    print(  "  └──────────────────────┴──────────────────────────┘", file=file)

    # 失败样本
    if report.failed_samples:
        print(f"\n  ⚠ 失败样本数: {len(report.failed_samples)}", file=file)
        for q in report.failed_samples[:5]:
            print(f"    - {q[:80]}", file=file)

    print("\n" + "=" * 70, file=file)


def print_weight_sweep_table(reports: List[EvalReport], file=sys.stdout) -> None:
    """打印权重扫描对比表。

    将多组 (dense_weight, sparse_weight) 的评测结果
    并排展示，便于对比选优。

    Args:
        reports: 多组权重的评测报告列表。
        file: 输出流。
    """
    print("\n" + "=" * 90, file=file)
    print("  混合检索权重扫描对比", file=file)
    print("=" * 90, file=file)

    header = (
        f"  {'Dense':>6}  {'Sparse':>6}  "
        f"{'Recall':>8}  {'Relevance':>10}  {'MRR':>7}  {'NDCG':>7}  "
        f"{'Faith':>7}  {'Halluc':>7}"
    )
    print(header, file=file)
    print("  " + "-" * 80, file=file)

    for r in reports:
        dw = r.config.get("dense_weight", 1.0)
        sw = r.config.get("sparse_weight", 0.7)
        print(
            f"  {dw:>6.1f}  {sw:>6.1f}  "
            f"{r.avg_context_recall:>8.2%}  {r.avg_context_relevance:>10.2%}  "
            f"{r.avg_mrr:>7.2%}  {r.avg_ndcg:>7.2%}  "
            f"{r.avg_faithfulness:>7.2%}  {r.avg_hallucination_rate:>7.2%}",
            file=file,
        )

    print("=" * 90, file=file)

    # 标注最优
    if reports:
        best_recall = max(reports, key=lambda r: r.avg_context_recall)
        best_mrr = max(reports, key=lambda r: r.avg_mrr)
        best_faith = max(reports, key=lambda r: r.avg_faithfulness)
        print(f"  最佳 Recall: dense={best_recall.config['dense_weight']}, sparse={best_recall.config['sparse_weight']}", file=file)
        print(f"  最佳 MRR:    dense={best_mrr.config['dense_weight']}, sparse={best_mrr.config['sparse_weight']}", file=file)
        print(f"  最佳 Faith:  dense={best_faith.config['dense_weight']}, sparse={best_faith.config['sparse_weight']}", file=file)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _bar(value: float, width: int = 10, reverse: bool = False) -> str:
    """生成进度条字符串。"""
    clamped = max(0.0, min(1.0, value))
    if reverse:
        clamped = 1.0 - clamped
    filled = int(clamped * width)
    return "█" * filled + "░" * (width - filled)


def _generate_filename(report: EvalReport, ext: str) -> Path:
    """生成带时间戳的报告文件名。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_REPORT_DIR / f"{report.dataset_name}_{report.retrieval_mode}_{ts}.{ext}"

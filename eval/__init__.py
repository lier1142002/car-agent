"""
AutoSalesAgent RAG 评测模块。

提供完整的本地 RAG 评测方案，包括:
- metrics: 检索质量 & 生成质量指标计算
- dataset: Golden Dataset 构建与管理
- runner: 批量评测运行器
- report: 结果报告输出 (JSON/CSV/CLI)

典型使用流程:
    from tools.rag_tool import RAGTool
    from eval.dataset import GoldenDataset
    from eval.runner import EvalRunner
    from eval.report import print_report_table, save_report_json

    # 1. 初始化 RAG 工具并索引文档
    rag = RAGTool()
    rag.index_documents("data/product.pdf")

    # 2. 加载评测数据集
    ds = GoldenDataset.load("eval/datasets/auto_sales_eval_v1.0.json")

    # 3. 运行评测
    runner = EvalRunner(rag)
    report = runner.run(ds, retrieval_mode="hybrid")

    # 4. 查看结果
    print_report_table(report)
    save_report_json(report)
"""

from eval.dataset import DatasetGenerator, EvalSample, GoldenDataset
from eval.metrics import (
    LLMJudge,
    answer_relevance,
    context_recall,
    context_relevance,
    faithfulness,
    mrr,
    ndcg,
)
from eval.report import (
    print_report_table,
    print_weight_sweep_table,
    save_report_csv,
    save_report_json,
)
from eval.runner import EvalReport, EvalRunner, SampleResult

__all__ = [
    # 指标
    "context_relevance",
    "context_recall",
    "mrr",
    "ndcg",
    "faithfulness",
    "answer_relevance",
    "LLMJudge",
    # 数据
    "EvalSample",
    "GoldenDataset",
    "DatasetGenerator",
    # 运行器
    "EvalRunner",
    "EvalReport",
    "SampleResult",
    # 报告
    "save_report_json",
    "save_report_csv",
    "print_report_table",
    "print_weight_sweep_table",
]

"""
Golden Dataset 构建与加载模块。

提供:
1. GoldenDataset: 标注评测数据集的数据结构
2. DatasetGenerator: 利用 LLM 从 PDF 文档自动生成 QA 评测对
3. 数据集导入/导出 (JSON) 工具函数
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import config
from eval.prompts import QA_PAIR_GENERATION, DATASET_QUALITY_REVIEW

logger = logging.getLogger(__name__)

# 默认评测数据集路径
DEFAULT_DATASET_DIR = Path(__file__).parent / "datasets"


@dataclass
class EvalSample:
    """单条评测样本。

    Attributes:
        query: 用户查询文本。
        ground_truth: 标准答案（人工或 LLM 生成）。
        relevant_chunk_ids: 标注的相关文档块 ID 列表（可选）。
        relevant_chunks: 标注的相关文档块文本列表（用于召回率计算）。
        question_type: 问题类型（factual/comparative/sales_scenario）。
        difficulty: 难度（easy/medium/hard）。
        metadata: 额外元数据。
    """

    query: str
    ground_truth: str
    relevant_chunk_ids: List[int] = field(default_factory=list)
    relevant_chunks: List[str] = field(default_factory=list)
    question_type: str = "factual"
    difficulty: str = "medium"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "ground_truth": self.ground_truth,
            "relevant_chunk_ids": self.relevant_chunk_ids,
            "relevant_chunks": self.relevant_chunks,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalSample":
        return cls(
            query=data["query"],
            ground_truth=data["ground_truth"],
            relevant_chunk_ids=data.get("relevant_chunk_ids", []),
            relevant_chunks=data.get("relevant_chunks", []),
            question_type=data.get("question_type", "factual"),
            difficulty=data.get("difficulty", "medium"),
            metadata=data.get("metadata", {}),
        )


class GoldenDataset:
    """汽车销售 RAG 评测黄金数据集。

    管理评测样本的加载、保存、过滤和统计分析。

    Attributes:
        samples: EvalSample 列表。
        name: 数据集名称。
        version: 数据集版本号。
    """

    def __init__(
        self,
        samples: Optional[List[EvalSample]] = None,
        name: str = "auto_sales_eval",
        version: str = "1.0",
    ) -> None:
        self.samples: List[EvalSample] = samples or []
        self.name = name
        self.version = version

    def __len__(self) -> int:
        return len(self.samples)

    def __iter__(self):
        return iter(self.samples)

    def __getitem__(self, idx: int) -> EvalSample:
        return self.samples[idx]

    # ------------------------------------------------------------------
    # 过滤与统计
    # ------------------------------------------------------------------

    def filter_by_type(self, q_type: str) -> "GoldenDataset":
        """按问题类型过滤。"""
        return GoldenDataset(
            [s for s in self.samples if s.question_type == q_type],
            name=self.name,
            version=self.version,
        )

    def filter_by_difficulty(self, difficulty: str) -> "GoldenDataset":
        """按难度过滤。"""
        return GoldenDataset(
            [s for s in self.samples if s.difficulty == difficulty],
            name=self.name,
            version=self.version,
        )

    def summary(self) -> Dict[str, Any]:
        """返回数据集统计摘要。"""
        type_counts: Dict[str, int] = {}
        diff_counts: Dict[str, int] = {}
        for s in self.samples:
            type_counts[s.question_type] = type_counts.get(s.question_type, 0) + 1
            diff_counts[s.difficulty] = diff_counts.get(s.difficulty, 0) + 1
        return {
            "name": self.name,
            "version": self.version,
            "total_samples": len(self.samples),
            "by_type": type_counts,
            "by_difficulty": diff_counts,
            "avg_query_length": round(
                sum(len(s.query) for s in self.samples) / max(len(self.samples), 1),
                1,
            ),
        }

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "samples": [s.to_dict() for s in self.samples],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoldenDataset":
        samples = [EvalSample.from_dict(s) for s in data.get("samples", [])]
        return cls(
            samples=samples,
            name=data.get("name", "auto_sales_eval"),
            version=data.get("version", "1.0"),
        )

    def save(self, filepath: Optional[Path] = None) -> Path:
        """保存数据集到 JSON 文件。"""
        filepath = Path(filepath) if filepath else DEFAULT_DATASET_DIR / f"{self.name}_v{self.version}.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("数据集已保存: %s (%d 条)", filepath, len(self.samples))
        return filepath

    @classmethod
    def load(cls, filepath: Path) -> "GoldenDataset":
        """从 JSON 文件加载数据集。"""
        filepath = Path(filepath)
        data = json.loads(filepath.read_text(encoding="utf-8"))
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# 自动化数据集生成器
# ---------------------------------------------------------------------------


class DatasetGenerator:
    """基于文档内容自动生成 RAG 评测数据集的工具。

    工作流:
    1. 解析 PDF → 获取文本块
    2. 对每个块调用 LLM 生成 QA 对
    3. 质量审核（可选）
    4. 汇总为 GoldenDataset

    Attributes:
        llm_client: LLM 客户端。
        model: 模型名称。
        samples_per_chunk: 每个文档块生成的 QA 对数。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        samples_per_chunk: int = 2,
    ) -> None:
        self.llm_client = OpenAI(
            api_key=api_key or config.llm_api_key,
            base_url=api_url or config.llm_api_url,
        )
        self.model = model or config.llm_model
        self.samples_per_chunk = samples_per_chunk

    def generate_from_chunks(
        self,
        chunks: List[str],
        quality_review: bool = False,
        max_chunks: Optional[int] = None,
    ) -> GoldenDataset:
        """从文档块列表生成评测数据集。

        Args:
            chunks: 文档文本块列表。
            quality_review: 是否启用 LLM 质量审核（更慢但质量更高）。
            max_chunks: 最大处理的块数（用于控制数据集规模）。

        Returns:
            GoldenDataset: 生成的评测数据集。
        """
        # 随机采样 chunk 以覆盖不同内容区域
        if max_chunks and len(chunks) > max_chunks:
            sampled = random.sample(chunks, max_chunks)
        else:
            sampled = chunks

        samples: List[EvalSample] = []
        seen_queries: set = set()

        for i, chunk in enumerate(sampled):
            if len(chunk.strip()) < 50:
                continue  # 跳过太短的块

            logger.info("生成 QA 对: chunk %d/%d", i + 1, len(sampled))

            qa_pairs = self._generate_qa_pairs(chunk)

            for qa in qa_pairs:
                query = qa.get("query", "").strip()
                ground_truth = qa.get("ground_truth", "").strip()

                # 去重
                if query in seen_queries:
                    continue
                seen_queries.add(query)

                if not query or not ground_truth:
                    continue

                # 质量审核
                if quality_review:
                    passed = self._review_sample(query, ground_truth, chunk)
                    if not passed:
                        continue

                samples.append(EvalSample(
                    query=query,
                    ground_truth=ground_truth,
                    relevant_chunks=[chunk],
                    question_type=qa.get("type", "factual"),
                    difficulty=qa.get("difficulty", "medium"),
                    metadata={
                        "source_chunk_index": i,
                        "key_points": qa.get("key_points", []),
                    },
                ))

        logger.info("数据集生成完成: %d 条样本", len(samples))
        return GoldenDataset(samples=samples)

    def _generate_qa_pairs(self, chunk: str) -> List[Dict[str, Any]]:
        """对单个文档块生成 QA 对。"""
        from eval.metrics import LLMJudge
        judge = LLMJudge(
            api_key=config.llm_api_key,
            api_url=config.llm_api_url,
            model=self.model,
        )
        prompt = QA_PAIR_GENERATION.format(
            chunk=chunk[:3000],
            num_pairs=self.samples_per_chunk,
        )
        result = judge.judge(prompt)
        # judge.judge 期望返回 dict，但这里可能返回 list
        if isinstance(result, dict):
            # 可能是 {"qa_pairs": [...]} 或直接是数组包装
            if "qa_pairs" in result:
                return result["qa_pairs"]
            # 可能 JSON 被嵌套在某个 key 下
            for val in result.values():
                if isinstance(val, list):
                    return val
        if isinstance(result, list):
            return result
        return []

    def _review_sample(self, query: str, ground_truth: str, chunk: str) -> bool:
        """LLM 质量审核单条样本。"""
        from eval.metrics import LLMJudge
        judge = LLMJudge(
            api_key=config.llm_api_key,
            api_url=config.llm_api_url,
            model=self.model,
        )
        prompt = DATASET_QUALITY_REVIEW.format(
            query=query,
            ground_truth=ground_truth,
            relevant_chunks=chunk[:1000],
        )
        result = judge.judge(prompt)
        return result.get("pass", True)


# ---------------------------------------------------------------------------
# 手工标注辅助
# ---------------------------------------------------------------------------


def merge_datasets(datasets: List[GoldenDataset]) -> GoldenDataset:
    """合并多个数据集（自动去重 query）。"""
    seen: set = set()
    merged: List[EvalSample] = []
    for ds in datasets:
        for s in ds.samples:
            if s.query not in seen:
                seen.add(s.query)
                merged.append(s)
    return GoldenDataset(samples=merged)


def split_dataset(
    dataset: GoldenDataset,
    train_ratio: float = 0.7,
    seed: int = 42,
) -> Tuple[GoldenDataset, GoldenDataset]:
    """将数据集随机拆分为训练集和测试集。

    训练集可用于调优检索参数（如混合权重），测试集用于最终评测。

    Args:
        dataset: 原始数据集。
        train_ratio: 训练集比例。
        seed: 随机种子。

    Returns:
        (train_dataset, test_dataset)
    """
    random.seed(seed)
    samples = list(dataset.samples)
    random.shuffle(samples)
    split_idx = int(len(samples) * train_ratio)
    train = GoldenDataset(samples=samples[:split_idx], name=f"{dataset.name}_train")
    test = GoldenDataset(samples=samples[split_idx:], name=f"{dataset.name}_test")
    return train, test

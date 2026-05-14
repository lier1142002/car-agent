"""
Embedding 客户端模块。

通过阿里千问（或 OpenAI 兼容）Embedding API 生成文本向量，
返回稠密向量和稀疏向量表示。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from openai import OpenAI

from config import config

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Embedding API 客户端。

    调用兼容 OpenAI 格式的 Embedding API 生成文本的稠密向量，
    并通过 top-k 阈值转换模拟稀疏向量表示。

    Attributes:
        client: OpenAI 兼容客户端实例。
        model: Embedding 模型名称。
        dim: 输出稠密向量维度。
    """

    def __init__(self) -> None:
        """初始化 Embedding 客户端。

        使用 config 中的 API 地址、密钥和模型名创建 OpenAI 兼容客户端。
        """
        self.client = OpenAI(
            api_key=config.embedding_api_key,
            base_url=config.embedding_api_url,
        )
        self.model = config.embedding_model
        self.dim = config.embedding_dim
        logger.info(
            "EmbeddingClient 已初始化: model=%s, dim=%d, url=%s",
            self.model,
            self.dim,
            config.embedding_api_url,
        )

    def encode_text(self, text: str) -> Tuple[List[float], Dict[str, float]]:
        """将文本编码为稠密向量和稀疏向量。

        稠密向量直接来自 API 返回的 embedding。
        稀疏向量通过稠密向量的 top-k 阈值转换模拟：
        取绝对值最大的前 k 个维度及其值，其余视为零。

        Args:
            text: 待编码的文本字符串。

        Returns:
            Tuple[List[float], Dict[str, float]]:
                - dense_vector: 稠密向量（浮点列表）。
                - sparse_dict: 稀疏向量字典，key 为维度索引（字符串），value 为权重。
        """
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            dense_vector: List[float] = response.data[0].embedding
            logger.debug("成功生成稠密向量，维度=%d", len(dense_vector))

            # 将稠密向量转换为稀疏表示：取绝对值 top-k 维度
            sparse_dict = self._dense_to_sparse(dense_vector, top_k=50)

            return dense_vector, sparse_dict

        except Exception as e:
            logger.error("Embedding API 调用失败: %s", e)
            raise RuntimeError(f"Embedding API 调用失败: {e}") from e

    def encode_batch(
        self, texts: List[str]
    ) -> Tuple[List[List[float]], List[Dict[str, float]]]:
        """批量编码文本。

        Args:
            texts: 文本字符串列表。

        Returns:
            Tuple: 包含稠密向量列表和稀疏向量字典列表。
        """
        dense_list: List[List[float]] = []
        sparse_list: List[Dict[str, float]] = []

        for text in texts:
            dense, sparse = self.encode_text(text)
            dense_list.append(dense)
            sparse_list.append(sparse)

        logger.info("批量编码完成: %d 条文本", len(texts))
        return dense_list, sparse_list

    @staticmethod
    def _dense_to_sparse(
        dense_vector: List[float], top_k: int = 50
    ) -> Dict[str, float]:
        """将稠密向量转换为稀疏表示。

        通过选取绝对值最大的 top_k 个维度来实现。

        Args:
            dense_vector: 稠密向量（浮点列表）。
            top_k: 保留的维度数量。

        Returns:
            Dict[str, float]: key 为维度索引字符串，value 为权重。
        """
        # 获取绝对值最大的 top_k 个维度的索引
        indexed = [(i, abs(v)) for i, v in enumerate(dense_vector)]
        indexed.sort(key=lambda x: x[1], reverse=True)
        top_indices = indexed[:top_k]

        return {str(idx): dense_vector[idx] for idx, _ in top_indices}

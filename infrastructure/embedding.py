"""
Embedding 客户端模块。

支持多种 Embedding 提供商（本地 BGE-M3、千问、DeepSeek），
通过工厂模式运行时切换，对上层调用者透明。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple

import numpy as np
from openai import OpenAI

from config import config

logger = logging.getLogger(__name__)


class BaseEmbeddingProvider(ABC):
    """Embedding 提供商的抽象基类。"""

    @abstractmethod
    def encode_text(self, text: str) -> Tuple[List[float], Dict[str, float]]:
        """将文本编码为稠密向量和稀疏向量。"""

    @abstractmethod
    def encode_batch(
        self, texts: List[str]
    ) -> Tuple[List[List[float]], List[Dict[str, float]]]:
        """批量编码文本。"""

    @staticmethod
    def _dense_to_sparse(
        dense_vector: List[float], top_k: int = 50
    ) -> Dict[str, float]:
        """将稠密向量转换为稀疏表示（top-k 绝对值维度）。"""
        indexed = [(i, abs(v)) for i, v in enumerate(dense_vector)]
        indexed.sort(key=lambda x: x[1], reverse=True)
        top_indices = indexed[:top_k]
        return {str(idx): dense_vector[idx] for idx, _ in top_indices}


class QwenEmbeddingProvider(BaseEmbeddingProvider):
    """千问 Embedding API（text-embedding-v3）。"""

    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=config.embedding_api_key,
            base_url=config.embedding_api_url,
        )
        self.model = config.embedding_model
        self.dim = config.embedding_dim
        logger.info("千问 Embedding 已初始化: model=%s, dim=%d", self.model, self.dim)

    def encode_text(self, text: str) -> Tuple[List[float], Dict[str, float]]:
        try:
            response = self.client.embeddings.create(
                model=self.model, input=text
            )
            dense: List[float] = response.data[0].embedding
            sparse = self._dense_to_sparse(dense)
            return dense, sparse
        except Exception as e:
            logger.error("千问 Embedding 调用失败: %s", e)
            raise RuntimeError(f"千问 Embedding 调用失败: {e}") from e

    def encode_batch(
        self, texts: List[str]
    ) -> Tuple[List[List[float]], List[Dict[str, float]]]:
        dense_list, sparse_list = [], []
        for text in texts:
            d, s = self.encode_text(text)
            dense_list.append(d)
            sparse_list.append(s)
        logger.info("千问批量编码完成: %d 条", len(texts))
        return dense_list, sparse_list


class DeepSeekEmbeddingProvider(BaseEmbeddingProvider):
    """DeepSeek Embedding API（OpenAI 兼容接口）。"""

    def __init__(self) -> None:
        # deepseek_api_key 优先，但跳过占位符值
        dsk = config.deepseek_api_key
        api_key = dsk if (dsk and "your-" not in dsk) else config.embedding_api_key
        self.client = OpenAI(
            api_key=api_key,
            base_url=config.deepseek_api_url,
        )
        self.model = config.deepseek_embedding_model
        self.dim = 1536  # DeepSeek embedding 默认维度
        logger.info("DeepSeek Embedding 已初始化: model=%s", self.model)

    def encode_text(self, text: str) -> Tuple[List[float], Dict[str, float]]:
        try:
            response = self.client.embeddings.create(
                model=self.model, input=text
            )
            dense: List[float] = response.data[0].embedding
            sparse = self._dense_to_sparse(dense)
            return dense, sparse
        except Exception as e:
            logger.error("DeepSeek Embedding 调用失败: %s", e)
            raise RuntimeError(f"DeepSeek Embedding 调用失败: {e}") from e

    def encode_batch(
        self, texts: List[str]
    ) -> Tuple[List[List[float]], List[Dict[str, float]]]:
        dense_list, sparse_list = [], []
        for text in texts:
            d, s = self.encode_text(text)
            dense_list.append(d)
            sparse_list.append(s)
        logger.info("DeepSeek 批量编码完成: %d 条", len(texts))
        return dense_list, sparse_list


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    """本地 BGE-M3 Embedding 模型（via sentence-transformers）。

    首次初始化会自动下载模型（~2GB），后续使用缓存。
    BGE-M3 输出 1024 维稠密向量，支持稀疏词汇权重。
    """

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._st_model = SentenceTransformer(
            config.local_embedding_model,
            device=config.local_embedding_device,
        )
        self.dim = config.local_embedding_dim
        logger.info(
            "本地 BGE-M3 Embedding 已初始化: model=%s, dim=%d, device=%s",
            config.local_embedding_model,
            self.dim,
            config.local_embedding_device,
        )

    def encode_text(self, text: str) -> Tuple[List[float], Dict[str, float]]:
        try:
            # BGE-M3 返回 normalize 后的稠密向量
            dense: List[float] = self._st_model.encode(
                text, normalize_embeddings=True
            ).tolist()
            sparse = self._dense_to_sparse(dense)
            return dense, sparse
        except Exception as e:
            logger.error("BGE-M3 Embedding 调用失败: %s", e)
            raise RuntimeError(f"BGE-M3 Embedding 调用失败: {e}") from e

    def encode_batch(
        self, texts: List[str]
    ) -> Tuple[List[List[float]], List[Dict[str, float]]]:
        try:
            dense_all: np.ndarray = self._st_model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            )
            dense_list: List[List[float]] = dense_all.tolist()
            sparse_list = [self._dense_to_sparse(d) for d in dense_list]
            logger.info("BGE-M3 批量编码完成: %d 条", len(texts))
            return dense_list, sparse_list
        except Exception as e:
            logger.error("BGE-M3 批量编码失败: %s", e)
            raise RuntimeError(f"BGE-M3 批量编码失败: {e}") from e


class EmbeddingClient:
    """Embedding 外观类。

    根据 config.embedding_provider 动态选择底层提供商，
    支持运行时通过 switch_provider() 切换。

    Attributes:
        provider: 当前激活的 Embedding 提供商实例。
        provider_name: 当前提供商名称（"local" / "qwen" / "deepseek"）。
    """

    def __init__(self) -> None:
        self.provider_name: str = ""
        self.provider: BaseEmbeddingProvider = self._create_provider(
            config.embedding_provider
        )

    def _create_provider(self, name: str) -> BaseEmbeddingProvider:
        """工厂方法：根据名称创建对应的 provider 实例。"""
        self.provider_name = name
        if name == "qwen":
            return QwenEmbeddingProvider()
        if name == "deepseek":
            return DeepSeekEmbeddingProvider()
        if name == "local":
            return LocalEmbeddingProvider()
        return LocalEmbeddingProvider()

    def switch_provider(self, name: str) -> None:
        """运行时切换到指定提供商。

        Args:
            name: "local" / "qwen" / "deepseek"。
        """
        if name == self.provider_name:
            return
        self.provider = self._create_provider(name)
        logger.info("Embedding 提供商已切换为: %s", name)

    def encode_text(self, text: str) -> Tuple[List[float], Dict[str, float]]:
        return self.provider.encode_text(text)

    def encode_batch(
        self, texts: List[str]
    ) -> Tuple[List[List[float]], List[Dict[str, float]]]:
        return self.provider.encode_batch(texts)

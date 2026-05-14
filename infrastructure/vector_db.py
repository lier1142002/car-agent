"""
Milvus 向量数据库模块。

管理本地 Milvus 连接、Collection 创建、索引构建，
提供稠密检索、稀疏检索和加权混合检索功能。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pymilvus import (
    AnnSearchRequest,
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusClient,
    WeightedRanker,
    connections,
)

from config import config

logger = logging.getLogger(__name__)


class VectorDB:
    """Milvus 向量数据库封装。

    管理 auto_sales_knowledge Collection，支持:
    - 双向量存储（稠密 + 稀疏）
    - SPARSE_INVERTED_INDEX 和 AUTOINDEX 索引
    - 稠密/稀疏/混合检索

    Attributes:
        uri: Milvus 数据库文件路径。
        collection_name: Collection 名称。
        client: MilvusClient 实例。
        collection: PyMilvus Collection 对象。
    """

    def __init__(self) -> None:
        """初始化 Milvus 连接并确保 Collection 存在。"""
        self.uri = config.milvus_uri
        self.collection_name = config.milvus_collection_name
        self.dim = config.embedding_dim

        # 建立连接
        connections.connect(uri=self.uri)
        self.client = MilvusClient(uri=self.uri)

        # 创建或加载 Collection
        self.collection = self._get_or_create_collection()
        logger.info(
            "VectorDB 已初始化: uri=%s, collection=%s",
            self.uri,
            self.collection_name,
        )

    # ------------------------------------------------------------------
    # Collection 管理
    # ------------------------------------------------------------------

    def _get_or_create_collection(self) -> Collection:
        """获取已有 Collection 或创建新的。

        Returns:
            Collection: Milvus Collection 对象。
        """
        if self.client.has_collection(self.collection_name):
            logger.info("Collection '%s' 已存在，直接加载", self.collection_name)
            return Collection(self.collection_name)

        logger.info("创建新 Collection: %s", self.collection_name)
        return self._create_collection()

    def _create_collection(self) -> Collection:
        """创建 Collection 并建立索引。

        定义 Schema:
        - id: INT64 主键（auto_id=True）
        - text: VARCHAR(512) 原始文本
        - sparse_vector: SPARSE_FLOAT_VECTOR 稀疏向量
        - dense_vector: FLOAT_VECTOR 稠密向量

        Returns:
            Collection: 新创建的 Collection。
        """
        schema = CollectionSchema(
            fields=[
                FieldSchema(
                    name="id",
                    dtype=DataType.INT64,
                    is_primary=True,
                    auto_id=True,
                ),
                FieldSchema(
                    name="text",
                    dtype=DataType.VARCHAR,
                    max_length=512,
                ),
                FieldSchema(
                    name="sparse_vector",
                    dtype=DataType.SPARSE_FLOAT_VECTOR,
                ),
                FieldSchema(
                    name="dense_vector",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=self.dim,
                ),
            ],
            description="汽车销售知识库向量存储",
            enable_dynamic_field=False,
        )

        collection = Collection(
            name=self.collection_name,
            schema=schema,
        )

        # 建立索引
        self._build_indexes(collection)
        return collection

    def _build_indexes(self, collection: Collection) -> None:
        """为稀疏和稠密向量字段建立索引。

        Args:
            collection: Milvus Collection 对象。
        """
        # 稀疏向量索引：SPARSE_INVERTED_INDEX
        sparse_index_params = {
            "index_type": "SPARSE_INVERTED_INDEX",
            "metric_type": "IP",  # Inner Product
        }
        collection.create_index(
            field_name="sparse_vector",
            index_params=sparse_index_params,
        )

        # 稠密向量索引：AUTOINDEX
        dense_index_params = {
            "index_type": "AUTOINDEX",
            "metric_type": "COSINE",
        }
        collection.create_index(
            field_name="dense_vector",
            index_params=dense_index_params,
        )

        collection.load()
        logger.info(
            "Collection '%s' 索引已建立并加载到内存",
            self.collection_name,
        )

    def reset_collection(self) -> None:
        """删除并重建 Collection（用于清空数据重新索引）。"""
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)
            logger.info("已删除 Collection: %s", self.collection_name)
        self.collection = self._create_collection()

    # ------------------------------------------------------------------
    # 数据操作
    # ------------------------------------------------------------------

    def insert(
        self,
        texts: List[str],
        dense_vectors: List[List[float]],
        sparse_vectors: List[Dict[str, float]],
    ) -> int:
        """批量插入文本和向量到 Collection。

        Args:
            texts: 文本列表。
            dense_vectors: 稠密向量列表。
            sparse_vectors: 稀疏向量字典列表。

        Returns:
            int: 插入的数据行数。
        """
        if not texts:
            logger.warning("插入数据为空，跳过")
            return 0

        data: List[Dict[str, Any]] = []
        for text, dense, sparse in zip(texts, dense_vectors, sparse_vectors):
            data.append({
                "text": text[:512],  # 截断到 VARCHAR 最大长度
                "dense_vector": dense,
                "sparse_vector": sparse,
            })

        result = self.collection.insert(data)
        self.collection.flush()
        insert_count = result.insert_count
        logger.info("成功插入 %d 条数据", insert_count)
        return insert_count

    # ------------------------------------------------------------------
    # 检索方法
    # ------------------------------------------------------------------

    def search_dense(
        self,
        query_vector: List[float],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """稠密向量检索（余弦相似度）。

        Args:
            query_vector: 查询稠密向量。
            top_k: 返回数量，默认使用配置值。

        Returns:
            List[Dict]: 检索结果，每项包含 id, text, score。
        """
        top_k = top_k or config.top_k

        results = self.collection.search(
            data=[query_vector],
            anns_field="dense_vector",
            param={"metric_type": "COSINE"},
            limit=top_k,
            output_fields=["id", "text"],
        )

        return self._format_results(results)

    def search_sparse(
        self,
        query_sparse: Dict[str, float],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """稀疏向量检索（内积）。

        Args:
            query_sparse: 查询稀疏向量字典。
            top_k: 返回数量，默认使用配置值。

        Returns:
            List[Dict]: 检索结果，每项包含 id, text, score。
        """
        top_k = top_k or config.top_k

        results = self.collection.search(
            data=[query_sparse],
            anns_field="sparse_vector",
            param={"metric_type": "IP"},
            limit=top_k,
            output_fields=["id", "text"],
        )

        return self._format_results(results)

    def hybrid_search(
        self,
        query_dense: List[float],
        query_sparse: Dict[str, float],
        top_k: Optional[int] = None,
        dense_weight: Optional[float] = None,
        sparse_weight: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """混合检索：加权融合稠密和稀疏检索结果。

        使用 Milvus WeightedRanker 进行加权重排序。

        Args:
            query_dense: 查询稠密向量。
            query_sparse: 查询稀疏向量字典。
            top_k: 返回数量。
            dense_weight: 稠密检索权重。
            sparse_weight: 稀疏检索权重。

        Returns:
            List[Dict]: 混合检索结果。
        """
        top_k = top_k or config.top_k
        dense_weight = dense_weight if dense_weight is not None else config.dense_weight
        sparse_weight = sparse_weight if sparse_weight is not None else config.sparse_weight

        ranker = WeightedRanker(dense_weight, sparse_weight)

        dense_req = AnnSearchRequest(
            data=[query_dense],
            anns_field="dense_vector",
            param={"metric_type": "COSINE"},
            limit=top_k,
        )
        sparse_req = AnnSearchRequest(
            data=[query_sparse],
            anns_field="sparse_vector",
            param={"metric_type": "IP"},
            limit=top_k,
        )

        results = self.collection.hybrid_search(
            reqs=[dense_req, sparse_req],
            rerank=ranker,
            limit=top_k,
            output_fields=["id", "text"],
        )

        return self._format_results(results)

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _format_results(
        raw_results: List[Any],
    ) -> List[Dict[str, Any]]:
        """将 Milvus 原始检索结果格式化为统一结构。

        Args:
            raw_results: Milvus search/hybrid_search 的原始返回。

        Returns:
            List[Dict]: 统一格式的结果列表。
        """
        formatted: List[Dict[str, Any]] = []

        # 处理嵌套列表结构
        if raw_results and isinstance(raw_results[0], list):
            hits = raw_results[0]
        else:
            hits = raw_results

        for hit in hits:
            formatted.append({
                "id": getattr(hit, "id", hit.get("id", "")),
                "text": getattr(
                    hit, "entity", hit
                ).get("text", ""),
                "score": getattr(hit, "distance", hit.get("distance", 0.0)),
            })

        return formatted

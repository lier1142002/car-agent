"""
基础设施层：向量数据库、Embedding 客户端、文档解析器。
"""

from infrastructure.embedding import EmbeddingClient
from infrastructure.vector_db import VectorDB
from infrastructure.doc_parser import DocParser

__all__ = ["EmbeddingClient", "VectorDB", "DocParser"]

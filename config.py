"""
AutoSalesAgent 全局配置模块。

所有 LLM、Embedding、数据库、检索参数均在此集中管理。
通过环境变量或直接修改本文件来配置 API 密钥和服务地址。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """AutoSalesAgent 全局配置数据类。

    支持通过环境变量覆盖敏感信息（API Key），其余参数使用默认值。
    """

    # =========================================================================
    # LLM API 配置（阿里千问 / OpenAI 兼容接口）
    # =========================================================================
    llm_api_url: str = field(
        default_factory=lambda: os.getenv(
            "LLM_API_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    )
    llm_api_key: str = field(
        default_factory=lambda: os.getenv(
            "LLM_API_KEY",
            "sk-80ba4c1f4c774ab7afcf4275a294f125",  # 替换为你的千问 API Key
        )
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "qwen-plus")
    )
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048

    # =========================================================================
    # Embedding API 配置（阿里千问 embedding / OpenAI 兼容接口）
    # =========================================================================
    embedding_api_url: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_API_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    )
    embedding_api_key: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_API_KEY",
            "sk-80ba4c1f4c774ab7afcf4275a294f125",  # 替换为你的千问 API Key
        )
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    )
    embedding_dim: int = 1024  # 千问 text-embedding-v3 输出维度
    embedding_provider: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "qwen")
    )  # "qwen" 或 "deepseek"

    # =========================================================================
    # DeepSeek Embedding 配置（OpenAI 兼容接口）
    # =========================================================================
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv(
            "DEEPSEEK_API_KEY",
            "sk-your-deepseek-api-key-here",
        )
    )
    deepseek_api_url: str = field(
        default_factory=lambda: os.getenv(
            "DEEPSEEK_API_URL",
            "https://api.deepseek.com/v1",
        )
    )
    deepseek_embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "DEEPSEEK_EMBEDDING_MODEL",
            "text-embedding-v1",
        )
    )

    # =========================================================================
    # Milvus 向量数据库配置
    # =========================================================================
    milvus_uri: str = "http://localhost:19530"
    milvus_collection_name: str = "auto_sales_knowledge"

    # =========================================================================
    # 混合检索参数
    # =========================================================================
    dense_weight: float = 1.0
    sparse_weight: float = 0.7
    top_k: int = 5

    # =========================================================================
    # 记忆模块参数
    # =========================================================================
    memory_compress_threshold: int = 2000  # 字符数阈值，超过后触发压缩
    memory_max_messages: int = 20

    # =========================================================================
    # 反思模块参数
    # =========================================================================
    reflection_max_iterations: int = 3
    reflection_quality_threshold: float = 0.8

    # =========================================================================
    # Web 搜索配置
    # =========================================================================
    serpapi_key: str = field(
        default_factory=lambda: os.getenv(
            "SERPAPI_API_KEY",
            "your-serpapi-key-here",  # 替换为你的 SerpAPI Key
        )
    )
    web_crawler_threads: int = 8
    web_crawler_timeout: int = 10

    # =========================================================================
    # 文档解析配置
    # =========================================================================
    llamaparse_api_key: str = field(
        default_factory=lambda: os.getenv(
            "LLAMAPARSE_API_KEY",
            "llx-beWd4mDMnsf1ElZXHU9AaN6dBMUrrkEYfxDPCe4cYBxGjje8",  # 替换为你的 LlamaParse Key
        )
    )
    chunk_max_tokens: int = 300
    chunk_overlap_tokens: int = 50

    # =========================================================================
    # 日志配置
    # =========================================================================
    log_level: str = "INFO"
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    def validate(self) -> bool:
        """检查关键配置是否已填写（非占位符值）。

        Returns:
            bool: 关键配置均非占位符时返回 True。
        """
        warnings: list[str] = []
        if "your-qwen-api-key" in self.llm_api_key:
            warnings.append("LLM_API_KEY 仍为占位符，请替换为真实 API Key")
        if "your-serpapi-key" in self.serpapi_key:
            warnings.append("SERPAPI_API_KEY 仍为占位符")
        if "your-llamaparse-key" in self.llamaparse_api_key:
            warnings.append("LLAMAPARSE_API_KEY 仍为占位符")
        if warnings:
            import logging
            logger = logging.getLogger(__name__)
            for w in warnings:
                logger.warning(w)
            return False
        return True

    def update_from_dict(self, data: dict) -> list[str]:
        """运行时部分更新配置（不持久化到文件）。

        Args:
            data: 包含要更新字段的字典，仅更新传入的 key。

        Returns:
            list[str]: 已更新的字段名列表。
        """
        import logging
        logger = logging.getLogger(__name__)
        allowed_keys = {
            "llm_api_key", "llm_api_url", "llm_model",
            "embedding_api_key", "embedding_api_url", "embedding_model",
            "embedding_provider",
            "deepseek_api_key", "deepseek_api_url", "deepseek_embedding_model",
            "serpapi_key", "llamaparse_api_key",
        }
        updated: list[str] = []
        for key, value in data.items():
            if key in allowed_keys and hasattr(self, key):
                setattr(self, key, value)
                updated.append(key)
                logger.info("配置更新: %s", key)
        return updated


# 全局配置单例
config = Config()

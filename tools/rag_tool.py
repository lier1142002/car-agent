"""
RAG 知识库检索工具模块。

整合文档解析、向量化、混合检索和 LLM 问答，
为汽车销售场景提供基于本地知识库的智能回答。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import config
from infrastructure.doc_parser import DocParser
from infrastructure.embedding import EmbeddingClient
from infrastructure.vector_db import VectorDB
from tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

# RAG Prompt 模板路径
RAG_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "rag_prompt.txt"


class RAGTool(BaseTool):
    """本地知识库检索增强生成工具。

    功能:
    1. index_documents: 解析 PDF -> 切块 -> 向量化 -> 存入 Milvus
    2. hybrid_retrieve: 混合向量检索
    3. generate_answer: 基于检索结果调用 LLM 生成带引用的回答
    4. run: 一体化查询接口

    Attributes:
        vector_db: Milvus 向量数据库实例。
        embedding: Embedding 客户端。
        doc_parser: 文档解析器。
        llm_client: LLM 客户端（用于生成回答）。
    """

    def __init__(self) -> None:
        """初始化 RAG 工具，连接 Milvus 和 Embedding 服务。"""
        super().__init__()
        self.name = "rag_tool"
        self.description = (
            "检索本地汽车产品知识库，获取车型参数、配置、价格、技术规格等信息"
        )

        self.vector_db = VectorDB()
        self.embedding = EmbeddingClient()
        self.doc_parser = DocParser()
        self.llm_client = OpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_url,
        )
        self._indexed: bool = False
        logger.info("RAGTool 已初始化")

    @property
    def is_indexed(self) -> bool:
        """知识库是否已索引。"""
        return self._indexed

    # ------------------------------------------------------------------
    # 文档索引
    # ------------------------------------------------------------------

    def index_documents(self, doc_path: str) -> int:
        """索引文档：解析、切块、向量化、存入数据库。

        Args:
            doc_path: PDF 文档文件路径。

        Returns:
            int: 索引的文本块数量。
        """
        logger.info("开始索引文档: %s", doc_path)

        # 1. 解析 PDF
        pages = self.doc_parser.parse_pdf(doc_path)
        full_text = "\n\n".join(pages)

        # 2. 智能切块
        chunks = self.doc_parser.chunk_text(full_text)
        logger.info("文档切分为 %d 个块", len(chunks))

        # 3. 批量向量化
        dense_vectors, sparse_vectors = self.embedding.encode_batch(chunks)

        # 4. 插入 Milvus（如果已有数据则重建）
        if self._indexed:
            self.vector_db.reset_collection()
        else:
            self._indexed = True

        count = self.vector_db.insert(chunks, dense_vectors, sparse_vectors)
        logger.info("文档索引完成: 共 %d 条", count)
        return count

    # ------------------------------------------------------------------
    # 检索与问答
    # ------------------------------------------------------------------

    def hybrid_retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """执行混合检索。

        Args:
            query: 用户查询文本。
            top_k: 返回文档数量。

        Returns:
            List[Dict]: 检索结果，每项包含 text 和 score。
        """
        dense, sparse = self.embedding.encode_text(query)
        results = self.vector_db.hybrid_search(dense, sparse, top_k=top_k)
        logger.info("混合检索完成: query='%s', 命中 %d 条", query[:50], len(results))
        return results

    def generate_answer(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> str:
        """基于检索上下文调用 LLM 生成回答。

        Args:
            query: 用户查询。
            context_docs: 检索到的文档列表。

        Returns:
            str: 带引用编号的回答文本。
        """
        # 构建上下文文本（带编号）
        context_parts: List[str] = []
        for i, doc in enumerate(context_docs, start=1):
            context_parts.append(f"[{i}] {doc['text']}")
        context_text = "\n\n".join(context_parts)

        # 加载提示词模板
        prompt_template = self._load_prompt_template()

        # 填充模板
        filled_prompt = prompt_template.format(
            context=context_text,
            query=query,
        )

        # 调用 LLM
        try:
            response = self.llm_client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {"role": "user", "content": filled_prompt},
                ],
                temperature=config.llm_temperature,
                max_tokens=config.llm_max_tokens,
            )
            answer = response.choices[0].message.content or "（未能生成回答）"
            logger.info("RAG 回答生成完成: %d chars", len(answer))
            return answer
        except Exception as e:
            logger.error("LLM 回答生成失败: %s", e)
            return f"回答生成失败: {e}\n\n基于检索结果，以下信息可能对您有帮助:\n{context_text}"

    def run(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        """执行 RAG 查询全流程。

        检索 -> 调用 LLM 生成回答 -> 返回结果。

        Args:
            query: 用户查询。
            **kwargs: 额外参数（支持 top_k）。

        Returns:
            Dict[str, Any]: 包含 answer 和 sources 的结果。
        """
        top_k = kwargs.get("top_k", None)

        try:
            # 检索
            docs = self.hybrid_retrieve(query, top_k=top_k)

            if not docs:
                return {
                    "status": "success",
                    "result": "抱歉，未在本地知识库中找到相关信息。",
                    "metadata": {"sources": [], "count": 0},
                }

            # 生成回答
            answer = self.generate_answer(query, docs)

            return {
                "status": "success",
                "result": answer,
                "metadata": {
                    "sources": [
                        {"text": d["text"][:200], "score": d.get("score", 0)}
                        for d in docs
                    ],
                    "count": len(docs),
                },
            }
        except Exception as e:
            logger.error("RAG 查询失败: %s", e)
            return {
                "status": "error",
                "result": f"RAG 查询出错: {str(e)}",
                "metadata": {},
            }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _load_prompt_template() -> str:
        """加载 RAG 提示词模板。

        Returns:
            str: 提示词模板内容。
        """
        if RAG_PROMPT_PATH.exists():
            return RAG_PROMPT_PATH.read_text(encoding="utf-8")
        # 默认模板
        return (
            "你是一位专业的汽车销售顾问。请根据以下资料回答问题。\n\n"
            "资料:\n{context}\n\n用户问题: {query}\n\n"
            "请基于资料回答，使用[1][2]标注引用来源。"
        )

"""
文档解析模块。

通过 LlamaParse API 解析 PDF 文件为 Markdown 文本，
并实现智能文本切块功能。
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from config import config

logger = logging.getLogger(__name__)


class DocParser:
    """文档解析器。

    使用 LlamaParse API 将 PDF 文件解析为 Markdown 格式文本，
    并提供基于标题层级、表格完整性和段落长度的智能切块功能。

    Attributes:
        api_key: LlamaParse API 密钥。
        chunk_max_tokens: 每个切块的最大 token 数。
        chunk_overlap_tokens: 相邻切块的重叠 token 数。
    """

    def __init__(self) -> None:
        """初始化文档解析器。"""
        self.api_key = config.llamaparse_api_key
        self.chunk_max_tokens = config.chunk_max_tokens
        self.chunk_overlap_tokens = config.chunk_overlap_tokens
        logger.info("DocParser 已初始化")

    def parse_pdf(self, file_path: str) -> List[str]:
        """解析 PDF 文件，返回 Markdown 文本段落列表。

        调用 LlamaParse API 进行解析，保留表格结构。

        Args:
            file_path: PDF 文件的绝对或相对路径。

        Returns:
            List[str]: Markdown 格式的文本段落列表。
        """
        try:
            from llama_parse import LlamaParse

            parser = LlamaParse(
                api_key=self.api_key,
                result_type="markdown",
                num_workers=4,
                verbose=False,
            )
            logger.info("开始解析 PDF: %s", file_path)

            documents = parser.load_data(file_path)
            pages: List[str] = [doc.text for doc in documents if doc.text]

            logger.info("PDF 解析完成，共 %d 页/段落", len(pages))
            return pages

        except ImportError:
            logger.error(
                "llama-parse 库未安装，请执行: pip install llama-parse"
            )
            raise
        except Exception as e:
            logger.error("PDF 解析失败: %s", e)
            raise RuntimeError(f"PDF 解析失败: {e}") from e

    def chunk_text(self, text: str, max_tokens: Optional[int] = None) -> List[str]:
        """将长文本智能切分为适合 Embedding 的块。

        切块策略:
        1. 优先按 Markdown 标题（##, ###）分割
        2. 保护表格完整性（表格块不拆分）
        3. 对过长段落按句边界二次切分
        4. 块之间保留一定重叠以维持上下文

        Args:
            text: 待切分的文本。
            max_tokens: 每块最大 token 数，默认使用配置值。

        Returns:
            List[str]: 文本块列表。
        """
        max_tokens = max_tokens or self.chunk_max_tokens
        # 粗略估计: 1 token ≈ 2 中文字符 ≈ 4 英文字符
        max_chars = max_tokens * 3

        # 将完整文本按双换行分段
        paragraphs = self._split_by_headings_and_paragraphs(text)
        chunks: List[str] = []
        current_chunk: str = ""

        for para in paragraphs:
            # 如果是表格块，优先保持完整
            if self._is_table_block(para):
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                chunks.append(para.strip())
                continue

            # 如果当前段落加入后未超出长度阈值，则合并
            if len(current_chunk) + len(para) <= max_chars:
                current_chunk += para + "\n\n"
            else:
                # 当前块已满，保存并开始新块
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # 如果单个段落就超长，按句子切分
                if len(para) > max_chars:
                    sub_chunks = self._split_long_paragraph(
                        para, max_chars, self.chunk_overlap_tokens * 3
                    )
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    current_chunk = para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        logger.info(
            "文本切块完成: 原文约%d字符 -> %d个块",
            len(text),
            len(chunks),
        )
        return chunks

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _split_by_headings_and_paragraphs(text: str) -> List[str]:
        """按标题和段落分割文本。

        Args:
            text: 原始文本。

        Returns:
            List[str]: 段落列表。
        """
        # 按 Markdown 标题分割
        heading_pattern = r"(?=^#{1,3}\s)"
        sections = re.split(heading_pattern, text, flags=re.MULTILINE)

        result: List[str] = []
        for section in sections:
            if not section.strip():
                continue
            # 每个 section 内部再按双换行分段落
            sub_paras = section.split("\n\n")
            for sp in sub_paras:
                sp = sp.strip()
                if sp:
                    result.append(sp)
        return result

    @staticmethod
    def _is_table_block(text: str) -> bool:
        """判断文本块是否包含 Markdown 表格。

        Args:
            text: 文本块。

        Returns:
            bool: 如果包含表格线则返回 True。
        """
        # 表格特征：包含 |---| 风格的分隔行
        lines = text.split("\n")
        pipe_count = sum(1 for line in lines if "|" in line)
        if pipe_count >= 3:
            return True
        # 也检查是否有表格分隔符行
        for line in lines:
            if re.match(r"^\|[\s\-:|]+\|$", line.strip()):
                return True
        return False

    @staticmethod
    def _split_long_paragraph(
        text: str, max_chars: int, overlap_chars: int
    ) -> List[str]:
        """对超长段落按句子边界切分。

        Args:
            text: 超长段落文本。
            max_chars: 每块最大字符数。
            overlap_chars: 重叠字符数。

        Returns:
            List[str]: 子块列表。
        """
        # 按句号、问号、感叹号等句子分隔符切分
        sentences = re.split(r"(?<=[。！？\.!\?])\s*", text)
        chunks: List[str] = []
        current: str = ""

        for sent in sentences:
            if len(current) + len(sent) <= max_chars:
                current += sent
            else:
                if current:
                    chunks.append(current.strip())
                # 考虑重叠
                overlap_text = current[-overlap_chars:] if len(current) > overlap_chars else current
                current = overlap_text + sent

        if current.strip():
            chunks.append(current.strip())

        return chunks

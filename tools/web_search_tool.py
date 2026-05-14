"""
联网搜索工具模块。

通过 SerpAPI 获取搜索结果摘要，多线程爬取详情页正文，
使用 ChromaDB 进行临时语义检索，返回带来源引用的结构化答案。
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import chromadb
import requests
from bs4 import BeautifulSoup

from config import config
from tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class WebCrawler:
    """多线程网页爬虫。

    使用 BeautifulSoup 提取页面正文，
    支持自定义 User-Agent 伪装和多线程并发抓取。

    Attributes:
        threads: 最大并发线程数。
        timeout: 单次请求超时秒数。
        user_agent: 请求头 User-Agent。
    """

    # macOS 和 Windows 的常用 User-Agent
    USER_AGENTS: List[str] = [
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.4 Safari/605.1.15"
        ),
    ]

    def __init__(
        self,
        threads: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """初始化爬虫。

        Args:
            threads: 并发线程数，默认使用配置值。
            timeout: 请求超时秒数，默认使用配置值。
        """
        self.threads = threads or config.web_crawler_threads
        self.timeout = timeout or config.web_crawler_timeout
        self.user_agent = self.USER_AGENTS[1]  # 默认 Windows UA
        logger.info("WebCrawler 已初始化: threads=%d, timeout=%d", self.threads, self.timeout)

    def crawl(self, url: str) -> Dict[str, Any]:
        """抓取单个 URL 的正文内容。

        Args:
            url: 目标网页 URL。

        Returns:
            Dict[str, Any]:
                - url: 原始 URL
                - title: 页面标题
                - text: 提取的正文文本
                - error: 错误信息（如有）
        """
        result: Dict[str, Any] = {
            "url": url,
            "title": "",
            "text": "",
            "error": None,
        }

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"

            soup = BeautifulSoup(resp.text, "html.parser")

            # 提取标题
            title_tag = soup.find("title")
            if title_tag:
                result["title"] = title_tag.get_text(strip=True)

            # 移除脚本和样式
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # 提取正文
            body = soup.find("body")
            if body:
                text = body.get_text(separator="\n", strip=True)
                # 清理多余空白
                text = re.sub(r"\n\s*\n", "\n\n", text)
                text = re.sub(r"[ \t]+", " ", text)
                result["text"] = text[:3000]  # 限制长度
            else:
                result["text"] = soup.get_text(separator="\n", strip=True)[:3000]

            logger.debug("爬取成功: %s -> %d chars", url, len(result["text"]))
        except Exception as e:
            result["error"] = str(e)
            logger.warning("爬取失败: %s - %s", url, e)

        return result

    def crawl_many(self, urls: List[str]) -> List[Dict[str, Any]]:
        """多线程爬取多个 URL。

        Args:
            urls: URL 列表。

        Returns:
            List[Dict]: 爬取结果列表。
        """
        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            future_map = {executor.submit(self.crawl, url): url for url in urls}
            for future in as_completed(future_map):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    url = future_map[future]
                    logger.error("并发爬取异常: %s - %s", url, e)
                    results.append({"url": url, "title": "", "text": "", "error": str(e)})

        logger.info("批量爬取完成: %d/%d 成功", sum(1 for r in results if not r["error"]), len(urls))
        return results


class WebSearchTool(BaseTool):
    """联网搜索工具。

    流程:
    1. SerpAPI 获取搜索结果摘要和 URL
    2. WebCrawler 多线程抓取详情
    3. 去重后存入临时 ChromaDB
    4. 语义检索返回最相关片段与来源

    Attributes:
        serpapi_key: SerpAPI 密钥。
        crawler: WebCrawler 实例。
        chroma_client: ChromaDB 客户端。
    """

    SERPAPI_URL = "https://serpapi.com/search"

    def __init__(self) -> None:
        """初始化搜索工具。"""
        super().__init__()
        self.name = "web_search"
        self.description = (
            "联网搜索最新汽车资讯、竞品对比、市场行情、政策信息"
        )
        self.serpapi_key = config.serpapi_key
        self.crawler = WebCrawler()
        self.chroma_client = chromadb.Client()
        logger.info("WebSearchTool 已初始化")

    def _search_serpapi(
        self, query: str, num_results: int = 10
    ) -> List[Dict[str, Any]]:
        """调用 SerpAPI 获取搜索结果。

        Args:
            query: 搜索查询。
            num_results: 期望的结果数量。

        Returns:
            List[Dict]: 搜索结果摘要列表。
        """
        params: Dict[str, Any] = {
            "q": query,
            "api_key": self.serpapi_key,
            "engine": "google",
            "num": num_results,
            "hl": "zh-CN",
            "gl": "cn",
        }

        try:
            resp = requests.get(self.SERPAPI_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            results: List[Dict[str, Any]] = []
            for item in data.get("organic_results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

            logger.info("SerpAPI 返回 %d 条结果", len(results))
            return results
        except Exception as e:
            logger.error("SerpAPI 搜索失败: %s", e)
            return []

    def _deduplicate(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """基于 URL 和内容哈希去重。

        Args:
            items: 待去重的条目列表。

        Returns:
            List[Dict]: 去重后的条目。
        """
        seen_urls: set = set()
        seen_hashes: set = set()
        unique: List[Dict[str, Any]] = []

        for item in items:
            url = item.get("url", "")
            text = item.get("text", "")

            if url and url in seen_urls:
                continue
            text_hash = hashlib.md5(text[:500].encode()).hexdigest()
            if text_hash in seen_hashes:
                continue

            if url:
                seen_urls.add(url)
            seen_hashes.add(text_hash)
            unique.append(item)

        logger.info("去重: %d -> %d 条", len(items), len(unique))
        return unique

    def run(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        """执行联网搜索全流程。

        Args:
            query: 搜索查询。
            **kwargs: 额外参数（支持 num_results）。

        Returns:
            Dict[str, Any]: 包含 answer 和 sources 的结果。
        """
        num_results = kwargs.get("num_results", 10)

        try:
            # 1. SerpAPI 搜索
            serp_results = self._search_serpapi(query, num_results)

            if not serp_results:
                return {
                    "status": "success",
                    "result": "未搜索到相关信息，请尝试更换搜索词。",
                    "metadata": {"sources": [], "count": 0},
                }

            # 2. 多线程爬取详情
            urls = [r["url"] for r in serp_results if r["url"]]
            crawl_results = self.crawler.crawl_many(urls)

            # 3. 合并摘要与详情
            combined: List[Dict[str, Any]] = []
            for sr in serp_results:
                matching = [
                    cr for cr in crawl_results if cr["url"] == sr["url"]
                ]
                body_text = matching[0]["text"] if matching else sr["snippet"]
                combined.append({
                    "title": sr["title"],
                    "url": sr["url"],
                    "text": f"{sr['snippet']}\n\n{body_text}",
                })

            # 4. 去重
            unique_docs = self._deduplicate(combined)

            # 5. 存入临时 ChromaDB（语义检索）
            collection_id = f"web_search_{uuid.uuid4().hex[:8]}"
            collection = self.chroma_client.create_collection(
                name=collection_id,
                metadata={"hnsw:space": "cosine"},
            )

            for i, doc in enumerate(unique_docs):
                collection.add(
                    ids=[f"doc_{i}"],
                    documents=[doc["text"][:1000]],
                    metadatas=[{"url": doc["url"], "title": doc["title"]}],
                )

            # 6. 语义检索
            chroma_results = collection.query(
                query_texts=[query],
                n_results=min(5, len(unique_docs)),
            )

            # 7. 格式化输出
            answer_parts: List[str] = []
            sources: List[Dict[str, str]] = []

            if chroma_results["ids"] and chroma_results["ids"][0]:
                for idx, doc_id in enumerate(chroma_results["ids"][0], start=1):
                    meta = chroma_results["metadatas"][0][idx - 1] if chroma_results["metadatas"] else {}
                    doc_text = (
                        chroma_results["documents"][0][idx - 1]
                        if chroma_results["documents"]
                        else ""
                    )
                    answer_parts.append(f"[{idx}] {meta.get('title', '无标题')}\n{doc_text[:500]}")
                    sources.append({
                        "title": meta.get("title", ""),
                        "url": meta.get("url", ""),
                    })

            answer = "\n\n".join(answer_parts) if answer_parts else "未找到相关内容。"
            final_answer = (
                f"**联网搜索结果** (查询: {query})\n\n{answer}\n\n"
                f"**来源:**\n" + "\n".join(f"- [{s['title']}]({s['url']})" for s in sources)
            )

            # 清理临时 Collection
            try:
                self.chroma_client.delete_collection(name=collection_id)
            except Exception:
                pass

            return {
                "status": "success",
                "result": final_answer,
                "metadata": {
                    "sources": sources,
                    "count": len(sources),
                },
            }

        except Exception as e:
            logger.error("Web 搜索失败: %s", e)
            return {
                "status": "error",
                "result": f"联网搜索出错: {str(e)}",
                "metadata": {},
            }

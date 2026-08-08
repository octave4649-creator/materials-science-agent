"""RAG 检索工具：Sci-Base local search，与 Sciverse web search 互补。

定位（对应教程「双数据源」）：Sciverse API 做 web search（在线语义证据），
本工具做 local search（Sci-Base 本地语料 BM25 检索），供 Agent 编排层与
补检索循环调用。

证据链强制（00-project-rules.md 4.1）：检索结果必须附带 EvidenceChain，
source="scibase"，doc_id 取 DOI/doc_id，保证结论可回溯。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.logging import AuditLogger
from src.rag.bm25_index import BM25Index, RagHit
from src.rag.scibase_indexer import DEFAULT_INDEX_PATH
from src.retrieval.evidence import EvidenceChain, EvidenceItem

# 对齐检索 Agent 的统一论文结构（retrieval_agent.Paper）
Paper = dict[str, Any]


@dataclass
class RagSearchResult:
    """一次 RAG 检索任务的输出。"""

    query: str  # 原始查询
    hits: list[RagHit] = field(default_factory=list)  # 命中清单（相关度降序）
    evidence: EvidenceChain = field(
        default_factory=lambda: EvidenceChain(conclusion="")
    )  # 检索证据链
    total_found: int = 0  # 命中总数
    degraded: bool = False  # 是否降级（索引缺失/加载失败）


class RagRetrievalTool:
    """Sci-Base 本地语料检索工具（Agent 可直接调用的检索工具）。"""

    def __init__(
        self,
        *,
        index_path: str | Path | None = None,
        logger: AuditLogger | None = None,
    ) -> None:
        """初始化。

        参数:
            index_path: BM25 索引路径（默认 data/cache/scibase/scibase_index.json）
            logger: 审计日志器（默认 rag_retrieval 专用）
        """
        self.index_path = Path(index_path) if index_path else DEFAULT_INDEX_PATH
        self.logger = logger or AuditLogger("rag_retrieval")
        self._index: BM25Index | None = None

    # ---------- 主入口 ----------

    def search(self, query: str, top_k: int = 5) -> RagSearchResult:
        """执行本地 RAG 检索：加载索引 → BM25 → 证据链打包。

        索引缺失/加载失败时降级返回空结果并留痕（不抛错，流水线不中断，
        对齐 exp 经验 26：LLM/外部依赖失败自动降级）。

        参数:
            query: 检索查询（自然语言）
            top_k: 返回命中上限

        返回:
            RagSearchResult（命中清单 + 证据链）。
        """
        self.logger.log(
            "rag_search", "success", input_summary={"query": query, "top_k": top_k}
        )
        result = RagSearchResult(query=query)
        result.evidence = EvidenceChain(conclusion=f"Sci-Base 本地检索：{query}")
        index = self._get_index()
        if index is None:
            result.degraded = True
            self.logger.log(
                "rag_index_missing",
                "degraded",
                output_summary={"index_path": str(self.index_path)},
            )
            return result
        hits = index.search(query, top_k=top_k)
        result.total_found = len(hits)
        result.hits = hits
        for hit in hits:
            result.evidence.add(
                EvidenceItem(
                    source="scibase",
                    doc_id=hit.doi or hit.doc_id,
                    text=hit.snippet[:500],
                    score=hit.score,
                )
            )
        self.logger.log(
            "rag_search_done",
            "success",
            input_summary={"query": query},
            output_summary={"n_hits": len(hits), "degraded": False},
        )
        return result

    # ---------- 检索结果 → 统一论文结构 ----------

    @staticmethod
    def to_papers(hits: list[RagHit]) -> list[Paper]:
        """RAG 命中 → 检索 Agent 统一论文结构（供编排层合并进 all_papers）。

        字段对齐 retrieval_agent.Paper：doc_id/title/doi/year/score/source/chunk。
        """
        papers: list[Paper] = []
        for hit in hits:
            papers.append(
                {
                    "doc_id": hit.doc_id,
                    "unique_id": hit.doi,
                    "title": hit.title,
                    "doi": hit.doi,
                    "year": hit.year,
                    "journal": None,
                    "authors": [],
                    "score": hit.score,
                    "citation_count": None,
                    "chunk": hit.snippet[:600],
                    "page_no": None,
                    "source": "scibase",
                }
            )
        return papers

    def search_papers(self, query: str, top_k: int = 5) -> list[Paper]:
        """便捷接口：检索并直接返回统一论文结构（Agent 工具签名友好）。"""
        result = self.search(query, top_k=top_k)
        return self.to_papers(result.hits)

    # ---------- 内部 ----------

    def _get_index(self) -> BM25Index | None:
        """懒加载索引；缺失/损坏返回 None（降级）。"""
        if self._index is not None:
            return self._index
        if not self.index_path.exists():
            return None
        try:
            self._index = BM25Index.load(self.index_path)
        except (OSError, ValueError, KeyError) as exc:
            self.logger.log(
                "rag_index_load_fail",
                "degraded",
                input_summary={"path": str(self.index_path)},
                error=str(exc)[:200],
            )
            self._index = None
        return self._index

    @property
    def available(self) -> bool:
        """索引是否可用（供编排层判断是否启用 local search）。"""
        return self._get_index() is not None

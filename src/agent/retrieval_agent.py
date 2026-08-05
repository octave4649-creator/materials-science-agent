"""检索 Agent：问题拆解 → 双通道检索 → 去重筛选 → 证据链打包。

架构（literature-agent 技能 2 节）：检索 Agent 是四 Agent 流水线第一环，
输出带证据链的候选文献清单 JSON，供抽取 Agent 使用。
MVP 阶段问题拆解用规则式（保证可复现、不依赖 LLM），复赛可升级 LLM 拆解。

证据链强制（00-project-rules.md 4.1）：任何输出必须附带 EvidenceChain。
"""
from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass, field
from typing import Any

from src.common.logging import AuditLogger
from src.retrieval.evidence import EvidenceChain, EvidenceItem
from src.retrieval.sciverse_client import SciverseClient, SciverseError

# 论文统一结构：语义 hit 与元数据 result 归一化后的最小字段集
Paper = dict[str, Any]

_TAG_RE = re.compile(r"<[^>]+>")


def _clean_title(title: str) -> str:
    """标题归一化：去 HTML 标签、小写、合并空白，用于去重比对。"""
    text = _TAG_RE.sub("", title or "")
    text = html.unescape(text).strip().lower()
    return re.sub(r"\s+", " ", text)


@dataclass
class RetrievalResult:
    """一次检索任务的输出。"""

    query: str  # 原始研究问题
    papers: list[Paper] = field(default_factory=list)  # 去重后的论文清单
    evidence: EvidenceChain = field(
        default_factory=lambda: EvidenceChain(conclusion="")
    )  # 检索证据链
    sub_queries: list[str] = field(default_factory=list)
    total_found: int = 0  # 检索去重前命中总数


class RetrievalAgent:
    """文献检索 Agent。"""

    def __init__(
        self, client: SciverseClient | None = None, logger: AuditLogger | None = None
    ) -> None:
        self.client = client or SciverseClient()
        self.logger = logger or AuditLogger("retrieval_agent")

    # ---------- 主入口 ----------

    async def run(
        self,
        question: str,
        top_k: int = 10,
        year_from: int | None = None,
        mode: str = "balanced",
    ) -> RetrievalResult:
        """执行一次完整检索：拆解 → 双通道 → 去重 → 证据链打包。"""
        self.logger.log("run_start", "success", input_summary={"question": question})
        result = RetrievalResult(query=question)
        result.evidence = EvidenceChain(conclusion=f"检索任务：{question}")

        # 1. 问题拆解
        sub_queries = self._decompose(question)
        result.sub_queries = sub_queries
        self.logger.log("decompose", "success", output_summary={"sub_queries": sub_queries})

        # 2. 双通道检索
        seen: set[str] = set()  # 去重集合
        for sq in sub_queries:
            try:
                semantic = await self.client.semantic_search(
                    query=sq, top_k=top_k, mode=mode
                )
                self._merge_hits(semantic, seen, result)
            except SciverseError as exc:
                # 语义通道失败不中断，降级走结构化通道并留痕
                self.logger.log(
                    "semantic_search",
                    "error",
                    input_summary={"query": sq},
                    error=str(exc),
                )

            try:
                papers = await self.client.search_papers(
                    query=sq, year_from=year_from, page_size=min(top_k, 50)
                )
                self._merge_papers(papers, seen, result)
            except SciverseError as exc:
                self.logger.log(
                    "search_papers",
                    "error",
                    input_summary={"query": sq},
                    error=str(exc),
                )

        result.total_found = len(seen)

        # 3. 排序：语义分优先，其次引用数
        result.papers.sort(
            key=lambda p: (
                p.get("score") is not None,
                p.get("score") or 0.0,
                p.get("citation_count") or 0,
            ),
            reverse=True,
        )
        self.logger.log(
            "run_done",
            "success",
            input_summary={"question": question},
            output_summary={"n_papers": len(result.papers), "total_found": result.total_found},
        )
        return result

    def run_sync(self, question: str, **kwargs: Any) -> RetrievalResult:
        """同步包装，方便脚本 / CLI 直接调用。"""
        return asyncio.run(self.run(question, **kwargs))

    # ---------- 内部逻辑 ----------

    def _decompose(self, question: str) -> list[str]:
        """研究问题拆解为可检索子问题（规则式 MVP）。

        规则：按中文/英文分号、句号拆句；每句去掉多余空白后作为独立查询。
        单句问题原样返回。
        """
        parts = re.split(r"[;；。]", question)
        queries = [p.strip() for p in parts if p.strip()]
        return queries or [question.strip()]

    def _merge_hits(
        self, semantic: dict[str, Any], seen: set[str], result: RetrievalResult
    ) -> None:
        """合并语义检索 hits（有证据片段，优先级高）。"""
        for hit in semantic.get("hits", []):
            paper = self._hit_to_paper(hit)
            key = self._dedupe_key(paper)
            if key in seen:
                continue
            seen.add(key)
            result.papers.append(paper)
            result.evidence.add(self._paper_to_evidence(paper))

    def _merge_papers(
        self, papers: dict[str, Any], seen: set[str], result: RetrievalResult
    ) -> None:
        """合并结构化检索 results（补充元数据：doi/unique_id/引用数）。"""
        for item in papers.get("results", []):
            paper = self._result_to_paper(item)
            key = self._dedupe_key(paper)
            if key in seen:
                continue
            seen.add(key)
            result.papers.append(paper)
            result.evidence.add(self._paper_to_evidence(paper))

    @staticmethod
    def _hit_to_paper(hit: dict[str, Any]) -> Paper:
        """语义 hit → 统一论文结构。"""
        authors = hit.get("author") or []
        if isinstance(authors, str):
            authors = [authors]
        return {
            "doc_id": hit.get("doc_id"),
            "unique_id": hit.get("unique_id"),
            "title": hit.get("title", ""),
            "doi": hit.get("doi"),
            "year": hit.get("publication_published_year"),
            "journal": hit.get("publication_venue_name_unified"),
            "authors": authors,
            "score": hit.get("score"),
            "citation_count": hit.get("citation_count"),
            "chunk": hit.get("chunk"),
            "page_no": hit.get("page_no"),
            "source": "semantic",
        }

    @staticmethod
    def _result_to_paper(item: dict[str, Any]) -> Paper:
        """元数据 result → 统一论文结构。"""
        authors = item.get("author") or []
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            authors = [a.get("name", "") for a in authors if isinstance(a, dict)]
        return {
            "doc_id": item.get("doc_id"),
            "unique_id": item.get("unique_id"),
            "title": item.get("title", ""),
            "doi": item.get("doi"),
            "year": item.get("publication_published_year"),
            "journal": item.get("publication_venue_name_unified"),
            "authors": authors,
            "score": None,
            "citation_count": item.get("citation_count"),
            "chunk": None,
            "page_no": None,
            "source": "papers",
        }

    @staticmethod
    def _dedupe_key(paper: Paper) -> str:
        """去重键：doc_id → unique_id → 归一化标题。"""
        if paper.get("doc_id"):
            return f"doc:{paper['doc_id']}"
        if paper.get("unique_id"):
            return f"uid:{paper['unique_id']}"
        return f"title:{_clean_title(paper.get('title', ''))}"

    @staticmethod
    def _paper_to_evidence(paper: Paper) -> EvidenceItem:
        """论文条目 → 证据项（doc_id 优先，缺省用 unique_id）。"""
        return EvidenceItem(
            source="sciverse",
            doc_id=paper.get("doc_id") or paper.get("unique_id") or paper.get("title", ""),
            text=(paper.get("chunk") or "")[:500],
            page=str(paper.get("page_no")) if paper.get("page_no") else None,
            score=paper.get("score"),
        )

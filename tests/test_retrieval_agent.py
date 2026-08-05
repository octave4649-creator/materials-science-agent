"""检索 Agent 单测：mock SciverseClient，验证拆解 / 去重 / 证据链 / 降级。"""
from __future__ import annotations

from typing import Any

import pytest

from src.agent.retrieval_agent import RetrievalAgent, _clean_title
from src.common.logging import AuditLogger
from src.retrieval.sciverse_client import SciverseError


class FakeSciverseClient:
    """可控替身：可注入语义 / 结构化结果，或抛出异常。"""

    def __init__(
        self,
        semantic_hits: list[dict[str, Any]] | None = None,
        paper_results: list[dict[str, Any]] | None = None,
        fail_semantic: bool = False,
    ) -> None:
        self.semantic_hits = semantic_hits or []
        self.paper_results = paper_results or []
        self.fail_semantic = fail_semantic

    async def semantic_search(
        self, query: str, top_k: int = 10, mode: str = "balanced"
    ) -> dict[str, Any]:
        if self.fail_semantic:
            raise SciverseError("模拟语义检索失败")
        return {"hits": self.semantic_hits}

    async def search_papers(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return {"results": self.paper_results}


def _agent(tmp_path, client: FakeSciverseClient) -> RetrievalAgent:
    return RetrievalAgent(client=client, logger=AuditLogger("test_retrieval", log_dir=tmp_path))


@pytest.mark.asyncio
async def test_run_dedupe_and_evidence(tmp_path) -> None:
    """语义与结构化命中同一论文（doc_id 相同）→ 去重为 1，证据链 1 条。"""
    client = FakeSciverseClient(
        semantic_hits=[
            {
                "doc_id": "d1",
                "title": "Ti<sub>3</sub> Alloy <b>Study</b>",
                "score": 0.9,
                "chunk": "chunk text",
                "page_no": 3,
                "citation_count": 10,
            }
        ],
        paper_results=[
            {"doc_id": "d1", "unique_id": "u1", "title": "ti3 alloy study", "citation_count": 35}
        ],
    )
    agent = _agent(tmp_path, client)
    result = await agent.run("热电材料研究")
    assert result.total_found == 1
    assert len(result.papers) == 1
    assert len(result.evidence.items) == 1
    # 语义优先：保留 doc_id 且含 chunk 证据片段
    assert result.papers[0]["doc_id"] == "d1"
    assert result.papers[0]["chunk"] == "chunk text"
    assert result.evidence.items[0].page == "3"


@pytest.mark.asyncio
async def test_run_dedupe_by_title_when_no_id(tmp_path) -> None:
    """无 doc_id/unique_id 时按归一化标题去重。"""
    client = FakeSciverseClient(
        semantic_hits=[
            {"title": "A<sub>2</sub>B <i>Study</i>", "score": 0.8},
            {"title": "a2b study", "score": 0.7},  # 同篇（归一化标题相同）
            {"title": "Unrelated Paper", "score": 0.6},
        ]
    )
    agent = _agent(tmp_path, client)
    result = await agent.run("问题")
    assert len(result.papers) == 2


@pytest.mark.asyncio
async def test_run_degrade_when_semantic_fails(tmp_path) -> None:
    """语义通道异常时降级走结构化通道，任务不中断。"""
    client = FakeSciverseClient(
        paper_results=[{"unique_id": "u1", "title": "Paper A", "citation_count": 5}],
        fail_semantic=True,
    )
    agent = _agent(tmp_path, client)
    result = await agent.run("问题")
    assert len(result.papers) == 1
    assert result.papers[0]["unique_id"] == "u1"


def test_decompose_question() -> None:
    """问题拆解：分号/句号拆分为子查询。"""
    import tempfile
    from pathlib import Path

    agent = _agent(Path(tempfile.mkdtemp()), FakeSciverseClient())
    assert agent._decompose("热电材料掺杂；提升zT") == ["热电材料掺杂", "提升zT"]
    assert agent._decompose("单一问题") == ["单一问题"]


def test_clean_title() -> None:
    """标题归一化：去 HTML 标签、小写、合并空白。"""
    assert _clean_title("Ti<sub>3</sub> Alloy <b>Study</b>") == "ti3 alloy study"
    assert _clean_title("  spaced   title  ") == "spaced title"

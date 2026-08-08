"""LangGraph 编排状态图单测。

用 Fake Agents 注入（exp 经验 30/75：外部依赖注入可 mock、按调用顺序返回），
覆盖：正常路径、检索不足补检、Gap 不足补抽取、HITL approve/reject、
循环上限、空检索降级。全部无网络。
"""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.types import Command

from src.agent.extraction_agent import ExtractionResult, ExtractionStats
from src.agent.gap_agent import GapResult
from src.agent.retrieval_agent import RetrievalResult
from src.extraction.knowledge_base import KnowledgeBase
from src.gap.schemas import GapCandidate, GapReport
from src.orchestration.graph import ResearchOrchestrator
from src.rag.bm25_index import BM25Index
from src.rag.rag_tool import RagRetrievalTool
from src.retrieval.evidence import EvidenceChain

# ---------- Fake Agents ----------


class FakeRetrievalAgent:
    """按调用顺序返回检索结果（补检索会再次调用）。"""

    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = list(results)
        self.calls = 0

    def run_sync(self, question: str, **kwargs: Any) -> RetrievalResult:
        self.calls += 1
        if self.results:
            res = self.results.pop(0)
            res.query = question
            return res
        return RetrievalResult(query=question)


class FakeExtractionAgent:
    """返回固定知识库（临时路径隔离落盘）。"""

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        self.calls = 0

    def run(self, retrieval_json: Any) -> ExtractionResult:
        self.calls += 1
        return ExtractionResult(
            knowledge_base=self.kb,
            stats=ExtractionStats(n_papers=len(retrieval_json.get('papers', []))),
        )


class FakeGapAgent:
    """按调用顺序返回 Gap 报告（补抽取后再次调用）。"""

    def __init__(self, reports: list[GapReport]) -> None:
        self.reports = list(reports)
        self.calls = 0

    def run_sync(self, **kwargs: Any) -> GapResult:
        self.calls += 1
        report = self.reports.pop(0) if self.reports else GapReport(domain='test')
        return GapResult(report=report)


class FakeReportAgent:
    """返回固定 marker。"""

    def __init__(self, marker: str = 'report-done') -> None:
        self.marker = marker

    def run(self, question: str | None = None, use_llm: bool = True) -> str:
        return self.marker


# ---------- 构造辅助 ----------


def _paper(doc_id: str, title: str = 'Paper') -> dict:
    return {
        'doc_id': doc_id,
        'unique_id': f'uid-{doc_id}',
        'title': title,
        'doi': f'10.x/{doc_id}',
        'source': 'semantic',
        'chunk': 'some evidence text about thermoelectric materials.',
    }


def _retrieval(n_papers: int, tag: str = 'q') -> RetrievalResult:
    papers = [_paper(f'{tag}-{i}') for i in range(n_papers)]
    return RetrievalResult(
        query=tag,
        papers=papers,
        evidence=EvidenceChain(conclusion='test'),
        sub_queries=['q1', 'q2'],
        total_found=n_papers,
    )


def _gaps(n: int) -> GapReport:
    return GapReport(
        domain='test',
        gaps=[
            GapCandidate(
                gap_type='未探索方向', statement=f'Gap statement {i}', formulas=['GeTe']
            )
            for i in range(n)
        ],
    )


def _kb(tmp_path) -> KnowledgeBase:
    return KnowledgeBase(path=tmp_path / 'kb.json')


def _orchestrator(
    tmp_path,
    retrieval_results: list[RetrievalResult],
    gap_reports: list[GapReport],
    report_marker: str = 'report-done',
    rag_tool: RagRetrievalTool | None = None,
) -> ResearchOrchestrator:
    return ResearchOrchestrator(
        retrieval_agent=FakeRetrievalAgent(retrieval_results),
        extraction_agent=FakeExtractionAgent(_kb(tmp_path)),
        gap_agent=FakeGapAgent(gap_reports),
        report_agent=FakeReportAgent(report_marker),
        rag_tool=rag_tool,
    )


def _rag_index(tmp_path) -> RagRetrievalTool:
    """构造并落盘一个迷你 Sci-Base BM25 索引（模拟本地语料命中）。"""
    idx = BM25Index()
    idx.build(
        [
            {
                'doc_id': 'rag-1', 'doi': '10.9/1',
                'title': 'GeTe thermoelectric alloys local corpus',
                'abstract': 'GeTe shows high thermoelectric figure of merit.',
            },
            {
                'doc_id': 'rag-2', 'doi': '10.9/2',
                'title': 'PbTe band engineering local corpus',
                'abstract': 'PbTe band gap tuning for thermoelectric efficiency.',
            },
        ]
    )
    path = tmp_path / 'rag_index.json'
    idx.save(path)
    return RagRetrievalTool(index_path=path)


def _state(question: str = 'q', **kw: Any) -> dict:
    s: dict[str, Any] = {
        'question': question,
        'domain': 'test',
        'top_k': 5,
        'year_from': None,
        'use_llm': False,
        'min_papers': 3,
        'min_gaps': 2,
        'max_retrieve_loops': 2,
        'max_gap_loops': 2,
        'all_papers': [],
        'n_retrieve_loops': 0,
        'n_gap_loops': 0,
        'errors': [],
    }
    s.update(kw)
    return s


def _config(tag: str | None = None) -> dict:
    return {'configurable': {'thread_id': tag or uuid.uuid4().hex[:12]}}


# ---------- 正常路径 ----------


def test_happy_path_reaches_report(tmp_path):
    """检索充足 + Gap 充足 + auto approve → 报告生成。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(5)],
        gap_reports=[_gaps(2)],
    )
    state = orch.run('q', auto_approve=True)
    assert state['report_paths']['marker'] == 'report-done'
    assert state['n_retrieve_loops'] == 0
    assert state['n_gap_loops'] == 0
    assert state['hitl_status'] == 'approved'
    assert len(state['all_papers']) == 5


# ---------- 检索不足补检 ----------


def test_retrieve_insufficient_triggers_more(tmp_path):
    """首轮不足 → 补检一轮后充足 → 进入抽取。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(1), _retrieval(5)],
        gap_reports=[_gaps(2)],
    )
    state = orch.run('q', auto_approve=True)
    assert orch.retrieval_agent.calls == 2  # 首轮 + 1 补检
    assert state['n_retrieve_loops'] == 1
    assert state['report_paths']['marker'] == 'report-done'


def test_retrieve_loop_reaches_cap(tmp_path):
    """一直不足 → 补检达到循环上限后仍继续到抽取（不无限循环）。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(1), _retrieval(1), _retrieval(1)],
        gap_reports=[_gaps(2)],
    )
    state = orch.run('q', auto_approve=True)
    assert orch.retrieval_agent.calls == 3  # 首轮 + max_retrieve_loops=2 轮
    assert state['n_retrieve_loops'] == 2
    assert state['report_paths']['marker'] == 'report-done'


# ---------- Gap 不足补抽取 ----------


def test_gap_insufficient_triggers_loop(tmp_path):
    """Gap 不足 → 补抽取（补检+重抽）后第二次 Gap 充足 → 通过。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(5), _retrieval(6)],
        gap_reports=[_gaps(0), _gaps(2)],
    )
    state = orch.run('q', auto_approve=True)
    assert orch.gap_agent.calls == 2
    assert state['n_gap_loops'] == 1
    assert state['report_paths']['marker'] == 'report-done'
    # 补抽取时补检累积文献
    assert len(state['all_papers']) >= 5


def test_gap_loop_reaches_cap(tmp_path):
    """Gap 一直不足 → 补抽取达循环上限后进入 HITL（不无限循环）。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(5), _retrieval(6), _retrieval(7)],
        gap_reports=[_gaps(0), _gaps(0), _gaps(0)],
    )
    state = orch.run('q', auto_approve=True)
    assert orch.gap_agent.calls == 3  # 首轮 + max_gap_loops=2 轮
    assert state['n_gap_loops'] == 2
    assert state['report_paths']['marker'] == 'report-done'  # 达上限仍走 HITL → approve


# ---------- HITL 人工审核 ----------


def test_hitl_pauses_and_approve(tmp_path):
    """auto_approve=False：invoke 停在 interrupt，resume approve 后到报告。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(5)],
        gap_reports=[_gaps(2)],
    )
    config = _config('hitl-approve')
    result = orch.graph.invoke(_state(), config)
    assert '__interrupt__' in result  # 停在人工审核节点
    payload = result['__interrupt__'][0].value
    assert payload['type'] == 'gap_review'
    assert payload['n_gaps'] == 2
    # 人工 approve
    result = orch.graph.invoke(Command(resume='approve'), config)
    assert result['hitl_status'] == 'approved'
    assert result['report_paths']['marker'] == 'report-done'


def test_hitl_reject_loops_back(tmp_path):
    """resume reject → 回 gap_loop 补证据重做 → 再次停在 HITL。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(5), _retrieval(6)],
        gap_reports=[_gaps(2), _gaps(2)],
    )
    config = _config('hitl-reject')
    result = orch.graph.invoke(_state(), config)
    assert '__interrupt__' in result
    # 人工 reject → gap_loop（补检+重抽）→ gap → hitl 再次中断
    result = orch.graph.invoke(Command(resume='reject'), config)
    assert result['hitl_status'] == 'rejected'
    assert '__interrupt__' in result
    assert result['n_gap_loops'] == 1
    # 第二次 approve 放行
    result = orch.graph.invoke(Command(resume='approve'), config)
    assert result['report_paths']['marker'] == 'report-done'


# ---------- 边界与降级 ----------


def test_empty_retrieval_degrades_but_continues(tmp_path):
    """检索为空 → 抽取跳过留痕，Gap 为空仍走 HITL，不中断。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[RetrievalResult(query='q')],
        gap_reports=[_gaps(0)],
    )
    state = orch.run('q', auto_approve=True)
    assert 'extract skipped: no papers' in state['errors']
    assert state['report_paths']['marker'] == 'report-done'


def test_hitl_approve_via_run_auto(tmp_path):
    """run(auto_approve=True) 自动放行 HITL（脚本场景）。"""
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(5)],
        gap_reports=[_gaps(2)],
    )
    state = orch.run('q')
    assert state['hitl_status'] == 'approved'


# ---------- RAG 双数据源补检 ----------


def test_retrieve_more_merges_rag_papers(tmp_path):
    """补检时 Sci-Base local search 并入 all_papers（双数据源）。"""
    rag = _rag_index(tmp_path)
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(1), _retrieval(5)],
        gap_reports=[_gaps(2)],
        rag_tool=rag,
    )
    state = orch.run('q thermoelectric', auto_approve=True)
    assert orch.retrieval_agent.calls == 2  # 首轮 + 1 补检
    assert state['n_retrieve_loops'] == 1
    # 双数据源：web 5 条 + RAG 命中并入，去重后应包含 scibase 来源
    sources = {p['source'] for p in state['all_papers']}
    assert 'scibase' in sources
    rag_papers = [p for p in state['all_papers'] if p['source'] == 'scibase']
    assert rag_papers, 'RAG local search 结果应并入 all_papers'
    assert all(p['doc_id'].startswith('rag-') for p in rag_papers)
    assert state['report_paths']['marker'] == 'report-done'


def test_retrieve_more_rag_unavailable_degrades(tmp_path):
    """RAG 索引不可用（无索引文件）→ 补检正常完成，不报错、不写入 errors。"""
    rag = RagRetrievalTool(index_path=tmp_path / 'missing_index.json')
    assert rag.available is False
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(1), _retrieval(5)],
        gap_reports=[_gaps(2)],
        rag_tool=rag,
    )
    state = orch.run('q', auto_approve=True)
    assert state['n_retrieve_loops'] == 1
    assert state['report_paths']['marker'] == 'report-done'
    assert 'extract skipped: no papers' not in state.get('errors', [])
    # 未并入任何 scibase 论文
    assert all(p['source'] != 'scibase' for p in state['all_papers'])


def test_retrieve_more_rag_dedup_with_web(tmp_path):
    """RAG 与 web 结果同 doc_id 时去重（不重复计数）。"""
    rag = _rag_index(tmp_path)
    # web 首轮 1 条（q-0）+ 补检 3 条（其中一条 doc_id 与 RAG 相同 → 合并去重）
    web_more = RetrievalResult(
        query='q',
        papers=[
            {
                'doc_id': 'rag-1', 'unique_id': '10.9/1',
                'title': 'GeTe thermoelectric alloys', 'source': 'papers',
            },
            {'doc_id': 'web-1', 'unique_id': 'u-web-1', 'title': 'Web paper', 'source': 'papers'},
        ],
        evidence=EvidenceChain(conclusion='test'),
        sub_queries=['q1'],
        total_found=2,
    )
    orch = _orchestrator(
        tmp_path,
        retrieval_results=[_retrieval(1), web_more],
        gap_reports=[_gaps(2)],
        rag_tool=rag,
    )
    state = orch.run('q thermoelectric', auto_approve=True)
    doc_ids = [p['doc_id'] for p in state['all_papers']]
    assert doc_ids.count('rag-1') == 1  # web 与 RAG 相同 doc_id 只保留一条

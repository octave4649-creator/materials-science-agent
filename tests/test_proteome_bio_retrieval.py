"""生物材料文献检索 Agent 单测。

用 FakeRetrievalAgent 注入，避免真实调用 Sciverse（exp.md 经验 30：
外部依赖一律注入，CI 不依赖网络）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.retrieval_agent import RetrievalResult
from src.proteome.bio_retrieval import (
    BioRetrievalAgent,
    BioRetrievalReport,
    DirectionResult,
)
from src.proteome.query_expander import GAP_DIRECTIONS
from src.retrieval.evidence import EvidenceChain, EvidenceItem


class FakeRetrievalAgent:
    """按调用顺序返回预设结果的假 RetrievalAgent。

    results_sequence: list，元素为 (papers, total_found) 或 Exception 实例。
    """

    def __init__(self, results_sequence: list[Any]) -> None:
        self._results = list(results_sequence)
        self._idx = 0
        self.calls: list[str] = []

    async def run(
        self,
        question: str,
        top_k: int = 10,
        year_from: int | None = None,
        mode: str = 'balanced',
    ) -> RetrievalResult:
        self.calls.append(question)
        if self._idx >= len(self._results):
            return RetrievalResult(query=question, papers=[], total_found=0)
        item = self._results[self._idx]
        self._idx += 1
        if isinstance(item, Exception):
            raise item
        papers, total_found = item
        result = RetrievalResult(
            query=question, papers=list(papers), total_found=total_found
        )
        result.evidence = EvidenceChain(conclusion=f'检索任务：{question}')
        for p in papers:
            result.evidence.add(
                EvidenceItem(
                    source='sciverse',
                    doc_id=p.get('doc_id') or p.get('title', ''),
                    text=(p.get('chunk') or '')[:100],
                )
            )
        return result


def _make_paper(doc_id: str, title: str = '', chunk: str = '') -> dict[str, Any]:
    """构造测试用 paper。"""
    return {
        'doc_id': doc_id,
        'unique_id': f'uid:{doc_id}',
        'title': title or f'Paper {doc_id}',
        'doi': f'10.1000/{doc_id}',
        'year': 2023,
        'journal': 'Yeast',
        'authors': ['Author A'],
        'score': 0.9,
        'citation_count': 10,
        'chunk': chunk or f'chunk for {doc_id}',
        'page_no': 1,
        'source': 'semantic',
    }


# ---------- BioRetrievalReport ----------


def test_report_to_dict_structure():
    """报告 to_dict 包含必要字段。"""
    report = BioRetrievalReport(
        directions=['temperature_response'],
        total_papers=1,
        papers=[_make_paper('d1')],
        evidence=EvidenceChain(conclusion='test'),
        per_direction=[
            DirectionResult(
                direction='temperature_response',
                query='q',
                description='d',
                n_papers=1,
                total_found=1,
                status='success',
            )
        ],
    )
    d = report.to_dict()
    assert d['total_papers'] == 1
    assert d['directions'] == ['temperature_response']
    assert d['n_evidence_items'] == 0
    assert len(d['papers']) == 1
    assert len(d['per_direction']) == 1
    assert d['per_direction'][0]['status'] == 'success'
    assert 'generated_at' in d


def test_report_save_and_reload(tmp_path: Path):
    """报告落盘后可读回，结构完整。"""
    report = BioRetrievalReport(
        directions=['temperature_response'],
        total_papers=1,
        papers=[_make_paper('d1')],
        evidence=EvidenceChain(conclusion='test'),
        per_direction=[
            DirectionResult(
                direction='temperature_response',
                query='q',
                description='d',
                n_papers=1,
                total_found=1,
                status='success',
            )
        ],
    )
    path = tmp_path / 'bio.json'
    returned = report.save(path)
    assert returned == path
    assert path.exists()
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['total_papers'] == 1
    assert data['papers'][0]['doc_id'] == 'd1'
    assert report.output_path == str(path)


# ---------- run_gap_search ----------


@pytest.mark.asyncio
async def test_run_gap_search_all_six_directions():
    """默认检索全部 6 个方向，每个方向 1 篇，去重后 6 篇。"""
    fake = FakeRetrievalAgent(
        [([_make_paper(f'd{i}')], 1) for i in range(6)]
    )
    agent = BioRetrievalAgent(retrieval=fake)
    report = await agent.run_gap_search(top_k=5)
    assert len(report.directions) == 6
    assert report.total_papers == 6
    assert len(report.papers) == 6
    assert all(d.status == 'success' for d in report.per_direction)
    assert len(fake.calls) == 6


@pytest.mark.asyncio
async def test_run_gap_search_subset_directions():
    """指定子集方向，只检索对应的 2 个。"""
    fake = FakeRetrievalAgent(
        [([_make_paper('d1')], 1), ([_make_paper('d2')], 1)]
    )
    agent = BioRetrievalAgent(retrieval=fake)
    report = await agent.run_gap_search(
        directions=['temperature_response', 'carbon_source_switch']
    )
    assert report.directions == ['temperature_response', 'carbon_source_switch']
    assert report.total_papers == 2
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_run_gap_search_dedupe_across_directions():
    """跨方向去重：两个方向返回相同 doc_id 的 paper，只保留一个。"""
    # 6 个方向，第 2 个方向返回与第 1 个相同 doc_id 的 paper
    results = [([_make_paper('shared')], 1)] * 2
    results += [([_make_paper(f'd{i}')], 1) for i in range(3, 7)]
    fake = FakeRetrievalAgent(results)
    agent = BioRetrievalAgent(retrieval=fake)
    report = await agent.run_gap_search()
    # 6 个方向，但 shared 重复，去重后 5 篇
    assert report.total_papers == 5
    # 第 2 个方向因去重新增为 0，status=partial
    assert report.per_direction[1].n_papers == 0
    assert report.per_direction[1].status == 'partial'


@pytest.mark.asyncio
async def test_run_gap_search_dedupe_disabled():
    """dedupe=False 时相同 paper 重复保留。"""
    results = [([_make_paper('shared')], 1)] * 2
    results += [([_make_paper(f'd{i}')], 1) for i in range(3, 7)]
    fake = FakeRetrievalAgent(results)
    agent = BioRetrievalAgent(retrieval=fake)
    report = await agent.run_gap_search(dedupe=False)
    assert report.total_papers == 6  # 不去重，全部保留


@pytest.mark.asyncio
async def test_run_gap_search_direction_failure_degrades():
    """某方向抛异常，降级为 failed，不中断后续方向。"""
    results: list[Any] = [([_make_paper('d1')], 1), RuntimeError('mock boom')]
    results += [([_make_paper(f'd{i}')], 1) for i in range(3, 6)]
    fake = FakeRetrievalAgent(results)
    agent = BioRetrievalAgent(retrieval=fake)
    report = await agent.run_gap_search()
    assert report.per_direction[1].status == 'failed'
    assert report.per_direction[1].error is not None
    assert 'mock boom' in report.per_direction[1].error
    assert report.per_direction[1].n_papers == 0
    # 其他方向正常
    assert report.per_direction[0].status == 'success'
    assert report.per_direction[2].status == 'success'
    assert len(fake.calls) == 6  # 全部 6 个方向都被调用


@pytest.mark.asyncio
async def test_run_gap_search_partial_when_empty():
    """某方向返回空 papers，status=partial。"""
    results: list[Any] = [([], 0)]
    results += [([_make_paper(f'd{i}')], 1) for i in range(2, 6)]
    fake = FakeRetrievalAgent(results)
    agent = BioRetrievalAgent(retrieval=fake)
    report = await agent.run_gap_search()
    assert report.per_direction[0].status == 'partial'
    assert report.per_direction[0].n_papers == 0


@pytest.mark.asyncio
async def test_run_gap_search_evidence_merged():
    """每个方向的证据项合并到总证据链。"""
    fake = FakeRetrievalAgent(
        [([_make_paper(f'd{i}')], 1) for i in range(6)]
    )
    agent = BioRetrievalAgent(retrieval=fake)
    report = await agent.run_gap_search()
    assert len(report.evidence.items) == 6
    # 证据项 doc_id 集合正确
    doc_ids = {item.doc_id for item in report.evidence.items}
    assert doc_ids == {f'd{i}' for i in range(6)}


@pytest.mark.asyncio
async def test_run_gap_search_query_matches_gap_directions():
    """投递给 RetrievalAgent 的查询与 GAP_DIRECTIONS 的英文查询一致。"""
    fake = FakeRetrievalAgent([([], 0)] * 6)
    agent = BioRetrievalAgent(retrieval=fake)
    await agent.run_gap_search()
    expected_queries = [
        GAP_DIRECTIONS[d]['en'] for d in GAP_DIRECTIONS
    ]
    assert fake.calls == expected_queries


# ---------- run_strain_search ----------


@pytest.mark.asyncio
async def test_run_strain_search_builds_question():
    """菌株-条件检索用 build_research_question 构建查询。"""
    fake = FakeRetrievalAgent([([_make_paper('s1')], 1)])
    agent = BioRetrievalAgent(retrieval=fake)
    result = await agent.run_strain_search(
        strain='BAI', temperature='37', carbon_source='galactose'
    )
    assert result.total_found == 1
    assert 'BAI' in fake.calls[0]
    assert '37' in fake.calls[0]
    assert 'galactose' in fake.calls[0]


# ---------- 同步包装 ----------


def test_run_gap_search_sync():
    """同步包装可正常调用。"""
    fake = FakeRetrievalAgent(
        [([_make_paper(f'd{i}')], 1) for i in range(6)]
    )
    agent = BioRetrievalAgent(retrieval=fake)
    report = agent.run_gap_search_sync()
    assert report.total_papers == 6


def test_run_strain_search_sync():
    """菌株检索同步包装。"""
    fake = FakeRetrievalAgent([([_make_paper('s1')], 1)])
    agent = BioRetrievalAgent(retrieval=fake)
    result = agent.run_strain_search_sync(strain='CEK')
    assert 'CEK' in result.query or 'CEK' in fake.calls[0]


# ---------- search_and_save ----------


def test_search_and_save(tmp_path: Path):
    """一键检索 + 落盘，返回 (报告, 路径)。"""
    fake = FakeRetrievalAgent(
        [([_make_paper(f'd{i}')], 1) for i in range(6)]
    )
    agent = BioRetrievalAgent(retrieval=fake, output_dir=tmp_path)
    out = tmp_path / 'out.json'
    report, path = agent.search_and_save(output_path=out)
    assert path == out
    assert out.exists()
    assert report.total_papers == 6
    data = json.loads(out.read_text(encoding='utf-8'))
    assert data['total_papers'] == 6


def test_search_and_save_auto_filename(tmp_path: Path):
    """output_path=None 时按时间戳自动生成文件名。"""
    fake = FakeRetrievalAgent(
        [([_make_paper(f'd{i}')], 1) for i in range(6)]
    )
    agent = BioRetrievalAgent(retrieval=fake, output_dir=tmp_path)
    report, path = agent.search_and_save()
    assert path.exists()
    assert path.name.startswith('bio_retrieval_')
    assert path.suffix == '.json'


# ---------- 边界 ----------


@pytest.mark.asyncio
async def test_run_gap_search_invalid_direction_ignored():
    """非法方向键被 query_expander 过滤，不参与检索。"""
    fake = FakeRetrievalAgent([([_make_paper('d1')], 1)])
    agent = BioRetrievalAgent(retrieval=fake)
    report = await agent.run_gap_search(
        directions=['temperature_response', 'not_a_real_direction']
    )
    assert report.directions == ['temperature_response']
    assert len(fake.calls) == 1


def test_direction_result_to_dict():
    """DirectionResult.to_dict 含 error 字段。"""
    d = DirectionResult(
        direction='x',
        query='q',
        description='d',
        n_papers=0,
        total_found=0,
        status='failed',
        error='boom',
    )
    out = d.to_dict()
    assert out['error'] == 'boom'
    assert out['status'] == 'failed'

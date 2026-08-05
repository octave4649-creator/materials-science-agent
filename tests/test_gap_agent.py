"""Gap Agent 测试：数据驱动 + LLM 推理（mock）+ Sciverse 新颖性回查（mock）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.agent import gap_agent as ga
from src.agent.gap_agent import GapAgent
from src.extraction.schemas import (
    ExtractionRecord,
    KnowledgeEntry,
    Material,
    PropertyEntry,
)
from src.gap.schemas import GapCandidate
from src.retrieval.sciverse_client import SciverseError


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认清空 LLM key（各测试按需 mock）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def _kb(tmp_path: Path, formulas: list[str]) -> Path:
    """构造含多证据条目的知识库文件。"""
    kb = ga.KnowledgeBase(path=tmp_path / "kb.json")
    for i, formula in enumerate(formulas):
        rec = ExtractionRecord(
            material=Material(formula=formula),
            properties=[PropertyEntry(name="zT", value=1.0 + i, unit=None)],
        )
        entry = KnowledgeEntry(
            record=rec,
            evidence_ids=[f"doc{i}", f"doc{i}b"],
            normalized_formula=formula,
        )
        kb.entries.append(entry)
    kb.save()
    return kb.path


class FakeSciverse:
    """Sciverse mock：可控 hits 或抛错。"""

    def __init__(self, hits: list[dict] | None = None, *, fail: bool = False) -> None:
        self.hits = hits or []
        self.fail = fail

    async def semantic_search(self, query: str, top_k: int = 5, mode: str = "fast") -> dict:
        if self.fail:
            raise SciverseError("mock sciverse down")
        return {"hits": self.hits}


def _hit(chunk: str) -> dict:
    return {"chunk": chunk, "score": 0.8, "doc_id": "h1"}


def test_run_data_driven_no_llm(tmp_path: Path) -> None:
    """无 LLM：覆盖率 + 矛盾检测产出 Gap，证据回链，报告落盘。"""
    out_path = tmp_path / "gaps.json"
    agent = GapAgent(
        kb_path=_kb(tmp_path, ["PbTe", "Bi2Te3"]),
        output_path=out_path,
        client=FakeSciverse(hits=[]),  # type: ignore[arg-type]
    )
    result = agent.run_sync(domain="thermoelectric", min_evidence=1, verify=True)
    report = result.report
    assert report.n_entries == 2
    assert len(report.gaps) >= 1
    for gap in report.gaps:
        assert gap.evidence_ids, "Gap 必须带证据链"
        assert all(eid.startswith("doc") for eid in gap.evidence_ids)
    assert out_path.is_file()


def test_run_verify_disabled(tmp_path: Path) -> None:
    """verify=False：跳过 Sciverse 回查，novelty 保持默认。"""
    agent = GapAgent(
        kb_path=_kb(tmp_path, ["PbTe"]),
        output_path=tmp_path / "gaps2.json",
        client=FakeSciverse(hits=[]),  # type: ignore[arg-type]
    )
    result = agent.run_sync(min_evidence=1, verify=False)
    assert result.report.gaps, "至少产出 Gap"
    assert all(g.novelty in ("已知", "部分已知", "新知") for g in result.report.gaps)


def test_llm_gaps_parse_and_map_evidence(tmp_path: Path) -> None:
    """LLM 输出解析：kb_entry_ids 回映射真实 doc_id，编造 formula 被丢弃。"""
    kb_path = _kb(tmp_path, ["PbTe", "Bi2Te3"])
    agent = GapAgent(kb_path=kb_path, client=FakeSciverse())  # type: ignore[arg-type]
    raw = {
        "gaps": [
            {
                "gap_type": "缺失知识连接",
                "statement": "PbTe 的热导率与掺杂浓度的关联未被系统研究",
                "rationale": "领域知识",
                "formulas": ["PbTe"],
                "kb_entry_ids": [0],
                "operability": "搜索掺杂-热导率关联",
                "confidence": 0.8,
            },
            {
                "gap_type": "方法空白",
                "statement": "FakeMatX 缺乏 ML 势函数",
                "rationale": "编造材料应被丢弃",
                "formulas": ["FakeMatX"],
                "kb_entry_ids": [1],
                "operability": "无",
                "confidence": 0.6,
            },
        ]
    }
    gaps = agent._parse_llm_gaps(raw)
    assert len(gaps) == 1
    assert gaps[0].statement.startswith("PbTe")
    assert gaps[0].evidence_ids == ["doc0", "doc0b"]  # 权威来源注入
    assert gaps[0].source == "llm"


def test_llm_gap_without_evidence_dropped(tmp_path: Path) -> None:
    """LLM 给出无 kb_entry_ids 的 Gap 被丢弃（证据链红线）。"""
    agent = GapAgent(kb_path=_kb(tmp_path, ["PbTe"]), client=FakeSciverse())  # type: ignore[arg-type]
    raw = {
        "gaps": [
            {
                "gap_type": "未探索方向",
                "statement": "PbTe 高温性能未研究",
                "rationale": "x",
                "formulas": ["PbTe"],
                "kb_entry_ids": [],
                "operability": "x",
                "confidence": 0.5,
            }
        ]
    }
    assert agent._parse_llm_gaps(raw) == []


def test_novelty_known_and_new(tmp_path: Path) -> None:
    """新颖性回查：命中 ≥2 条含公式片段 → 已知；0 条 → 新知。"""
    agent = GapAgent(
        kb_path=_kb(tmp_path, ["PbTe"]),
        client=FakeSciverse(hits=[_hit("PbTe thermoelectric"), _hit("PbTe doping")]),  # type: ignore[arg-type]
    )
    gap = GapCandidate(
        gap_type="未探索方向",
        statement="PbTe 性能研究不足",
        formulas=["PbTe"],
        evidence_ids=["doc0"],
        novelty="部分已知",
    )
    import asyncio

    result = asyncio.run(agent._verify_novelty([gap], ga.GapStats()))
    assert result[0].novelty == "已知"
    assert result[0].verification and "回查" in result[0].verification

    agent2 = GapAgent(
        kb_path=_kb(tmp_path, ["PbTe"]),
        client=FakeSciverse(hits=[_hit("other material")]),  # type: ignore[arg-type]
    )
    gap2 = GapCandidate(
        gap_type="未探索方向",
        statement="x",
        formulas=["PbTe"],
        evidence_ids=["doc0"],
        novelty="部分已知",
    )
    stats = ga.GapStats()
    result2 = asyncio.run(agent2._verify_novelty([gap2], stats))
    assert result2[0].novelty == "新知"


def test_novelty_degraded_on_sciverse_error(tmp_path: Path) -> None:
    """Sciverse 失败：降级留痕，novelty 保持默认。"""
    agent = GapAgent(
        kb_path=_kb(tmp_path, ["PbTe"]),
        client=FakeSciverse(fail=True),  # type: ignore[arg-type]
    )
    gap = GapCandidate(
        gap_type="未探索方向",
        statement="x",
        formulas=["PbTe"],
        evidence_ids=["doc0"],
        novelty="部分已知",
    )
    import asyncio

    stats = ga.GapStats()
    result = asyncio.run(agent._verify_novelty([gap], stats))
    assert stats.n_verify_degraded == 1
    assert result[0].novelty == "部分已知"
    assert "降级" in (result[0].verification or "")


def test_dedupe() -> None:
    """去重：同公式 + 同类型 + 同陈述只保留一条。"""
    gaps = [
        GapCandidate(
            gap_type="未探索方向",
            statement="PbTe 性能研究不足",
            formulas=["PbTe"],
            evidence_ids=["a"],
        ),
        GapCandidate(
            gap_type="未探索方向",
            statement="PbTe 性能研究不足",
            formulas=["PbTe"],
            evidence_ids=["b"],
        ),
        GapCandidate(
            gap_type="矛盾结论",
            statement="PbTe 带隙报道矛盾",
            formulas=["PbTe"],
            evidence_ids=["c"],
        ),
    ]
    out = GapAgent._dedupe(gaps)
    assert len(out) == 2

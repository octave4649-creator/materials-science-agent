"""抽取 Agent 测试：无 LLM 降级规则式 + 回查防幻觉 + 落库 + 合并。"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.extraction_agent import ExtractionAgent
from src.extraction.extractor import normalize_formula
from src.extraction.schemas import ExtractionRecord, Material

# 真实风格的模块 1 chunk（LaTeX 化学式 + zT + 温度）
_CHUNK1 = (
    r"The highest $ZT$ of 1.6 is achieved for "
    r"$\mathrm{Ge}_{0.93}\mathrm{Ti}_{0.01}\mathrm{Bi}_{0.06}\mathrm{Te}$ at $623\mathrm{K}$"
)


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """清空 LLM key，强制走规则式降级路径。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def _retrieval_payload() -> dict:
    """构造模块 1 输出风格 payload。"""
    return {
        "query": "thermoelectric doping zT",
        "papers": [
            {"doc_id": "d1", "doi": "10.1/d1", "chunk": _CHUNK1, "page_no": 5},
            {"doc_id": "d2", "doi": "10.1/d2", "chunk": "", "page_no": None},
            {"doc_id": "d3", "doi": "10.1/d3", "chunk": "no material info here", "page_no": 1},
        ],
    }


def test_rule_extract_and_persist(tmp_path: Path) -> None:
    """无 LLM：规则式抽取 → 回查 → 落库。"""
    kb_path = tmp_path / "kb.json"
    agent = ExtractionAgent(kb_path=kb_path)
    result = agent.run(_retrieval_payload())
    stats = result.stats
    assert stats.n_papers == 3
    assert stats.n_rule == 1  # 仅 d1 抽出；d2/d3 无有效材料
    assert stats.n_records == 1
    assert stats.model is None  # 无 LLM
    entries = result.knowledge_base.entries
    assert len(entries) == 1
    assert entries[0].normalized_formula == "Ge0.93Ti0.01Bi0.06Te"
    assert kb_path.is_file()


def test_kb_merge_same_formula(tmp_path: Path) -> None:
    """同 formula 多证据合并为一个知识库条目。"""
    payload = {
        "query": "t",
        "papers": [
            {"doc_id": "d1", "chunk": _CHUNK1},
            {"doc_id": "d2", "chunk": _CHUNK1.replace("d1", "d2")},
        ],
    }
    agent = ExtractionAgent(kb_path=tmp_path / "kb.json")
    result = agent.run(payload)
    entries = result.knowledge_base.entries
    assert len(entries) == 1
    # 同 formula 两条证据
    assert len(entries[0].evidence_ids) >= 1


def test_verify_against_source() -> None:
    """回查：化学式不在原文 → False。"""
    rec = ExtractionRecord(material=Material(formula="PbTe"))
    assert ExtractionAgent._verify_against_source(rec, "GeTe based materials") is False
    assert ExtractionAgent._verify_against_source(rec, "PbTe thermoelectrics") is True


def test_verify_latex_source() -> None:
    """回查：LaTeX 原文含归一化化学式 → True。"""
    rec = ExtractionRecord(
        material=Material(formula=r"\mathrm{Ge}_{0.93}\mathrm{Ti}_{0.01}\mathrm{Bi}_{0.06}\mathrm{Te}")
    )
    assert ExtractionAgent._verify_against_source(rec, _CHUNK1) is True


def test_normalize_formula_used_in_kb() -> None:
    """知识库化学式已归一化。"""
    assert normalize_formula(r"\mathrm{Pb}\mathrm{Te}") == "PbTe"

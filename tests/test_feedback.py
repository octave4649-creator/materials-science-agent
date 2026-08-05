"""模块 5↔6 搜索-验证闭环测试：反例母体提取、跨库分歧提取（离线、无网络）。"""
from __future__ import annotations

import json

from src.search.ga_search import LLMRoles, ga_search
from src.validation.feedback import extract_disputes, extract_negative_hosts


def _write_validation(tmp_path, name: str, results: list[dict]) -> None:
    (tmp_path / f"validation_{name}.json").write_text(
        json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8"
    )


def _entry(db: str, is_stable: bool) -> dict:
    return {"db": db, "formula": "GeTe", "is_stable": is_stable}


def test_extract_negative_hosts(tmp_path) -> None:
    """提取反例母体（去重、忽略已知/新知）。"""
    _write_validation(tmp_path, "1", [
        {"host": "SiGe", "candidate_formula": "SiGe-Ti6%", "verdict": "反例"},
        {"host": "Cu2Se", "candidate_formula": "Cu2Se-Ti6%", "verdict": "反例"},
        {"host": "PbTe", "candidate_formula": "PbTe-Ti6%", "verdict": "已知"},
        {"host": "Cu2Se", "candidate_formula": "Cu2Se-Na4%", "verdict": "反例"},
    ])
    neg = extract_negative_hosts(tmp_path)
    assert set(neg) == {"SiGe", "Cu2Se"}


def test_extract_disputes_oqmd_vs_mp(tmp_path) -> None:
    """提取跨库分歧（OQMD 稳定 vs MP 不稳定）。"""
    _write_validation(tmp_path, "1", [
        {
            "host": "GeTe",
            "candidate_formula": "Ge0.96Ti0.04Te",
            "verdict": "已知",
            "entries": [_entry("oqmd", True), _entry("mp", False)],
        },
        {
            "host": "PbTe",
            "candidate_formula": "PbTe-Ti6%",
            "verdict": "已知",
            "entries": [_entry("oqmd", True), _entry("mp", True)],
        },
        {
            "host": "SnTe",
            "candidate_formula": "SnTe-Ti6%",
            "verdict": "已知",
            "entries": [_entry("oqmd", True)],
        },
    ])
    disputes = extract_disputes(tmp_path)
    assert len(disputes) == 1
    assert disputes[0]["host"] == "GeTe"
    assert disputes[0]["oqmd_stable"] is True
    assert disputes[0]["mp_stable"] is False


def test_ga_search_negative_hosts_pruned(tmp_path) -> None:
    """反例母体回喂：以反例母体为宿主的候选被强制淘汰，审计留痕。"""
    roles = LLMRoles(chat_json=lambda s, u, k: {"_": "_"})
    finding = ga_search(
        gap_statement="PbTe/SiGe 掺杂 zT 空白",
        hosts=["PbTe", "SiGe"],
        roles=roles,
        generations=1,
        pop_size=6,
        llm_on=False,
        negative_hosts=["SiGe"],
    )
    assert finding.top_candidates
    assert all(c.host != "SiGe" for c in finding.top_candidates)
    actions = [s.action for s in finding.search_log.steps]
    assert "prune_feedback" in actions
    fb = next(s for s in finding.search_log.steps if s.action == "prune_feedback")
    assert fb.n_candidates > 0
    assert not finding.search_log.used_llm

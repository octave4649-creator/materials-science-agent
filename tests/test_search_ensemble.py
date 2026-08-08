"""四算法融合投票单测（tmp fixture，无网络）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.search.ensemble import (
    candidate_key,
    ensemble_findings,
    ensemble_vote,
    load_findings,
    render_html,
    render_markdown,
)

DOC_A = "a" * 64


def _cand(host: str, dopant: str, conc: float, formula: str, scientific: float = 0.8) -> dict:
    """构造候选 dict。"""
    return {
        "host": host, "dopant": dopant, "concentration": conc,
        "formula": formula, "scores": {"scientific": scientific},
    }


@pytest.fixture()
def env(tmp_path: Path) -> Path:
    """构造 findings 目录：同 gap 四算法 + 异 gap 单算法 + 坏文件。"""
    root = tmp_path / "proj"
    findings = root / "results" / "findings"
    findings.mkdir(parents=True)
    gap = "GeTe Ti 掺杂相变研究不足"
    common = {"gap_statement": gap, "evidence_ids": [DOC_A]}

    def write(name: str, algo: str, cands: list[dict]) -> None:
        (findings / name).write_text(
            json.dumps({**common, "algo": algo, "top_candidates": cands},
                       ensure_ascii=False),
            encoding="utf-8",
        )

    # ga：PbTe-Ti 4% 第 1 名；GeTe-Ti 6% 第 2 名
    write("finding_a1.json", "ga", [
        _cand("PbTe", "Ti", 4.0, "Pb0.96Ti0.04Te"),
        _cand("GeTe", "Ti", 6.0, "Ge0.94Ti0.06Te"),
    ])
    # mcts：PbTe-Ti 4% 第 1 名；GeTe-Ti 6% 第 2 名（共识）
    write("finding_a2.json", "mcts", [
        _cand("PbTe", "Ti", 4.0, "Pb0.96Ti0.04Te"),
        _cand("GeTe", "Ti", 6.0, "Ge0.94Ti0.06Te"),
    ])
    # bo：PbTe-Ti 4% 第 1 名（三票共识）；Bi2Te3-Se 2% 第 2 名
    write("finding_a3.json", "bo", [
        _cand("PbTe", "Ti", 4.0, "Pb0.96Ti0.04Te"),
        _cand("Bi2Te3", "Se", 2.0, "Bi2(Te0.98Se0.02)3"),
    ])
    # sr：GeTe-Ti 6% 第 1 名（共识）
    write("finding_a4.json", "sr", [
        _cand("GeTe", "Ti", 6.0, "Ge0.94Ti0.06Te"),
    ])
    # 异 gap：单算法
    (findings / "finding_b1.json").write_text(
        json.dumps({
            "gap_statement": "Mg3Sb2 空位机制不明",
            "algo": "ga",
            "evidence_ids": [],
            "top_candidates": [_cand("Mg3Sb2", "Bi", 2.0, "Mg3(Sb0.98Bi0.02)2")],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    # 坏文件（跳过）+ 无 algo（缺省 unknown）
    (findings / "finding_bad.json").write_text("not-json", encoding="utf-8")
    (findings / "finding_c1.json").write_text(
        json.dumps({
            "gap_statement": gap,
            "top_candidates": [_cand("PbTe", "Ti", 4.0, "Pb0.96Ti0.04Te")],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


class TestCandidateKey:
    def test_normalize_host_upper_dopant(self) -> None:
        assert candidate_key({"host": "pbte", "dopant": "ti", "concentration": 4.0}) == (
            "PBTE", "TI", 4.0,
        )

    def test_concentration_rounding(self) -> None:
        assert candidate_key({"host": "GeTe", "dopant": "Ti", "concentration": 6.05})[2] == 6.0

    def test_invalid_concentration_fallback(self) -> None:
        assert candidate_key({"host": "GeTe", "dopant": "Ti", "concentration": "x"})[2] == 0.0


class TestEnsembleVote:
    def test_consensus_ranked_first(self) -> None:
        r = ensemble_vote({
            "ga": [_cand("PbTe", "Ti", 4.0, "Pb0.96Ti0.04Te")],
            "mcts": [_cand("PbTe", "Ti", 4.0, "Pb0.96Ti0.04Te")],
            "bo": [_cand("Bi2Te3", "Se", 2.0, "Bi2(Te0.98Se0.02)3")],
        })
        top = r["votes"][0]
        assert top["host"] == "PbTe"
        assert top["n_votes"] == 2
        assert top["algorithms"] == ["ga", "mcts"]
        assert top["rank_by_algo"] == {"ga": 1, "mcts": 1}
        assert top["score"] == 2.0  # 1/1 + 1/1

    def test_rank_weighting(self) -> None:
        # 同一算法内：第 1 名权重 1.0 > 第 2 名 0.5
        r = ensemble_vote({
            "ga": [_cand("PbTe", "Ti", 4.0, "A"), _cand("GeTe", "Ti", 6.0, "B")],
        })
        assert r["votes"][0]["host"] == "PbTe"
        assert r["votes"][0]["score"] == 1.0
        assert r["votes"][1]["score"] == 0.5

    def test_duplicate_candidate_in_same_algo_only_top_rank(self) -> None:
        # 同算法重复候选只计最高排名（防刷票）
        r = ensemble_vote({
            "ga": [
                _cand("PbTe", "Ti", 4.0, "A"),
                _cand("PbTe", "Ti", 4.0, "A（重复）"),
            ],
        })
        assert len(r["votes"]) == 1
        assert r["votes"][0]["n_votes"] == 1

    def test_empty_input(self) -> None:
        r = ensemble_vote({})
        assert r["n_algorithms"] == 0
        assert r["votes"] == []
        assert r["n_votes_total"] == 0

    def test_concentration_tolerance_merge(self) -> None:
        # 浓度 4.0 与 4.1 取整后同桶（0.1 精度）
        r = ensemble_vote({
            "ga": [_cand("PbTe", "Ti", 4.0, "A")],
            "bo": [_cand("PbTe", "Ti", 4.1, "B")],
        })
        assert len(r["votes"]) == 1
        assert r["votes"][0]["n_votes"] == 2


class TestLoadAndGroup:
    def test_load_findings_skip_bad_and_default_algo(self, env: Path) -> None:
        findings = load_findings(env / "results")
        # a1-a4 + b1 + c1 = 6（坏文件跳过）
        assert len(findings) == 6
        c1 = next(f for f in findings if f.get("_file") == "finding_c1.json")
        assert c1["algo"] == "unknown"

    def test_ensemble_findings_group_by_gap(self, env: Path) -> None:
        results = ensemble_findings(load_findings(env / "results"))
        by_gap = {r["gap_statement"]: r for r in results}
        assert len(results) == 2
        gap = "GeTe Ti 掺杂相变研究不足"
        r = by_gap[gap]
        assert r["n_algorithms"] == 5  # ga/mcts/bo/sr + unknown
        assert r["n_findings"] == 5
        assert r["evidence_ids"] == [DOC_A]
        top = r["votes"][0]
        assert top["n_votes"] == 4  # ga + mcts + bo + unknown 都推 PbTe-Ti 4%
        assert top["host"] == "PbTe"

    def test_ensemble_sort_by_consensus(self, env: Path) -> None:
        results = ensemble_findings(load_findings(env / "results"))
        gap = "GeTe Ti 掺杂相变研究不足"
        r = next(x for x in results if x["gap_statement"] == gap)
        # 4 票共识 PbTe-Ti 4% 排第 1；GeTe-Ti 6% 3 票（ga+mcts+sr）排第 2
        assert r["votes"][0]["host"] == "PbTe"
        assert r["votes"][1]["host"] == "GeTe"
        assert r["votes"][1]["n_votes"] == 3


class TestRender:
    def test_render_markdown_sections(self, env: Path) -> None:
        results = ensemble_findings(load_findings(env / "results"))
        md = render_markdown(results)
        assert "# 四算法融合投票" in md
        assert "GeTe Ti 掺杂相变研究不足" in md
        assert "来源算法" in md

    def test_render_html_structure(self, env: Path) -> None:
        results = ensemble_findings(load_findings(env / "results"))
        h = render_html(results)
        assert "<!DOCTYPE html>" in h
        assert "四算法融合投票" in h
        assert "ok" in h  # 得票高亮

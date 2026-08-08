"""共识候选数据库交叉验证单测（tmp fixture，无网络）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.validation.consensus_verify import (
    CONSENSUS_MIN_VOTES,
    build_truth_map,
    parse_ensemble_md,
    render_html,
    render_markdown,
    resolve_parent,
    split_candidate,
    summarize,
    verify_consensus,
    verify_one,
)

ENSEMBLE_MD = """# 四算法融合投票（GA / MCTS / BO / SR）

## Mg3Sb2 空位机制不明

- 算法数：4｜候选总数：5｜finding：4 份

| 排名 | 候选 | 得票 | 得分 | 来源算法 | 平均可信度 |
| --- | --- | --- | --- | --- | --- |
| 1 | Mg3Sb2-Na2% | 2 | 1.0 | ga, sr | 0.65 |
| 2 | Mg3Sb2-Cd2% | 1 | 1.0 | sr | 0.8 |

## GeTe Ti 掺杂相变研究不足

- 算法数：4｜候选总数：4｜finding：4 份

| 排名 | 候选 | 得票 | 得分 | 来源算法 | 平均可信度 |
| --- | --- | --- | --- | --- | --- |
| 1 | Ge0.98Bi0.02Te | 2 | 1.5 | ga, mcts | 0.7 |
| 2 | Ge0.97Ti0.03Te | 2 | 1.25 | ga, sr | 0.7 |
"""


def _write_truth(tmp_path: Path, name: str, results: list[dict]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8")
    return p


class TestSplitCandidate:
    def test_simple_dopant(self) -> None:
        assert split_candidate("Mg3Sb2-Na2%") == ("Mg3Sb2", "Na", 2.0)

    def test_no_suffix(self) -> None:
        assert split_candidate("Ge0.98Bi0.02Te") == ("Ge0.98Bi0.02Te", None, None)

    def test_multi_dopant(self) -> None:
        h, d, c = split_candidate("CoSb3-Yb0.2Ba0.10%")
        assert h == "CoSb3"
        assert "Yb" in d
        assert c == 0.0  # 双掺杂描述浓度精度损失，母体不受影响


class TestResolveParent:
    def test_integer_host(self) -> None:
        assert resolve_parent("Mg3Sb2") == "Mg3Sb2"
        assert resolve_parent("ZrNiSn") == "ZrNiSn"

    def test_fraction_binary(self) -> None:
        assert resolve_parent("Ge0.98Bi0.02Te") == "GeTe"
        assert resolve_parent("Ge0.97Ti0.03Te") == "GeTe"

    def test_fraction_ternary_ab(self) -> None:
        # A/B 位拆分：Bi0.5Sb1.5Te3 → Sb2Te3（下标占比最大阳离子）
        assert resolve_parent("Bi0.5Sb1.5Te3") == "Sb2Te3"

    def test_fraction_alloy_si_ge(self) -> None:
        # 合金式（末尾非阴离子）→ 去数字下标
        assert resolve_parent("Si0.8Ge0.2") == "SiGe"

    def test_empty_or_unknown(self) -> None:
        assert resolve_parent("") is None
        assert resolve_parent("   ") is None


class TestParseEnsembleMd:
    def test_parse_groups_and_rows(self) -> None:
        results = parse_ensemble_md(ENSEMBLE_MD)
        assert len(results) == 2
        gap = results[0]
        assert "Mg3Sb2" in gap["gap_statement"]
        assert len(gap["votes"]) == 2
        top = gap["votes"][0]
        assert top["formula"] == "Mg3Sb2-Na2%"
        assert top["n_votes"] == 2
        assert top["score"] == 1.0
        assert top["algorithms"] == "ga, sr"
        assert top["avg_confidence"] == 0.65

    def test_empty_text(self) -> None:
        assert parse_ensemble_md("") == []
        assert parse_ensemble_md("无表格内容") == []


class TestBuildTruthMap:
    def test_priority_overwrite(self, tmp_path: Path) -> None:
        # 同一母体：验证失败（1）→ 反例（2）→ 已知（3）逐步覆盖
        _write_truth(tmp_path, "a.json", [
            {"candidate_formula": "GeTe", "host": "GeTe", "verdict": "验证失败",
             "reason": "查询失败", "entries": []},
        ])
        _write_truth(tmp_path, "b.json", [
            {"candidate_formula": "GeTe", "host": "GeTe", "verdict": "反例",
             "reason": "不稳定", "entries": [{"is_stable": False}]},
        ])
        _write_truth(tmp_path, "c.json", [
            {"candidate_formula": "GeTe", "host": "GeTe", "verdict": "已知",
             "reason": "稳定", "entries": [{"is_stable": True}]},
        ])
        truth = build_truth_map([tmp_path / "a.json", tmp_path / "b.json",
                                 tmp_path / "c.json"])
        assert truth["GeTe"]["verdict"] == "已知"

    def test_bad_file_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("not-json", encoding="utf-8")
        assert build_truth_map([tmp_path / "bad.json"]) == {}


class TestVerifyOne:
    def test_truth_cache_hit(self, tmp_path: Path) -> None:
        _write_truth(tmp_path, "t.json", [
            {"candidate_formula": "Mg3Sb2", "host": "Mg3Sb2",
             "verdict": "已知", "reason": "扩面直查稳定",
             "entries": [{"is_stable": True, "stability": 0.0}]},
        ])
        truth = build_truth_map([tmp_path / "t.json"])
        rec = verify_one({"formula": "Mg3Sb2-Na2%", "n_votes": 2}, truth)
        assert rec["parent_formula"] == "Mg3Sb2"
        assert rec["verdict"] == "已知"
        assert rec["cache_hit"] is True
        assert rec["dopant"] == "Na"

    def test_unresolvable_parent(self, tmp_path: Path) -> None:
        truth = build_truth_map([])
        rec = verify_one({"formula": "Pb0.98Na+Sr0.02Te", "n_votes": 1}, truth)
        assert rec["verdict"] == "验证失败"
        assert "无法解析" in rec["reason"]

    def test_miss_offline_verdict_failed(self, tmp_path: Path) -> None:
        truth = build_truth_map([])
        rec = verify_one({"formula": "Cu2Se-Te5%", "n_votes": 2}, truth)
        assert rec["verdict"] == "验证失败"
        assert "online" in rec["reason"]


class TestVerifyConsensus:
    def test_min_votes_filter(self, tmp_path: Path) -> None:
        _write_truth(tmp_path, "t.json", [
            {"candidate_formula": "Mg3Sb2", "host": "Mg3Sb2",
             "verdict": "已知", "reason": "", "entries": []},
            {"candidate_formula": "GeTe", "host": "GeTe",
             "verdict": "已知", "reason": "", "entries": []},
        ])
        truth = build_truth_map([tmp_path / "t.json"])
        results = parse_ensemble_md(ENSEMBLE_MD)
        records = verify_consensus(results, truth, min_votes=CONSENSUS_MIN_VOTES)
        # 仅 n_votes≥2 的 3 个候选进入（Mg3Sb2-Na2% + Ge0.98Bi0.02Te + Ge0.97Ti0.03Te）
        assert len(records) == 3
        assert all(r["n_votes"] >= 2 for r in records)
        assert records[0]["candidate"] == "Mg3Sb2-Na2%"

    def test_summarize_ratios(self) -> None:
        recs = [
            {"verdict": "已知"}, {"verdict": "已知"}, {"verdict": "反例"},
            {"verdict": "新知"}, {"verdict": "验证失败"},
        ]
        stats = summarize(recs)
        assert stats["n_consensus"] == 5
        assert stats["known_ratio"] == 0.4
        assert stats["counterexample_ratio"] == 0.2
        assert stats["novel_ratio"] == 0.2


class TestRender:
    def _records(self, tmp_path: Path) -> list[dict]:
        _write_truth(tmp_path, "t.json", [
            {"candidate_formula": "Mg3Sb2", "host": "Mg3Sb2",
             "verdict": "已知", "reason": "稳定",
             "entries": [{"is_stable": True, "stability": 0.02,
                          "delta_e": -0.5, "db": "oqmd"}]},
        ])
        truth = build_truth_map([tmp_path / "t.json"])
        results = parse_ensemble_md(ENSEMBLE_MD)
        return verify_consensus(results, truth)

    def test_render_markdown(self, tmp_path: Path) -> None:
        records = self._records(tmp_path)
        stats = summarize(records)
        md = render_markdown(records, stats)
        assert "# 共识候选数据库交叉验证对照表" in md
        assert "Mg3Sb2-Na2%" in md
        assert "已知" in md
        assert "hull=" in md

    def test_render_html_escapes(self, tmp_path: Path) -> None:
        records = self._records(tmp_path)
        stats = summarize(records)
        h = render_html(records, stats)
        assert "<!DOCTYPE html>" in h
        assert "<div class=\"wrap\">" in h
        assert "Mg3Sb2-Na2%" in h
        assert "</body></html>" in h


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

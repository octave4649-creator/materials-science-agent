"""build_demo_panel 聚合函数单测：真实产物 → 面板 payload 的正确性与健壮性。"""
from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.demo_panel import (
    build_payload,
    collect_ablation,
    collect_ensemble,
    collect_findings,
    collect_gaps,
    collect_kb,
    collect_recall_matrix,
    collect_validations,
    render_html,
)

# ---------------------------------------------------------------- fixtures


def _write(tmp_path: Path, rel: str, obj: object) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return p


def _gaps_payload(tmp_path: Path) -> Path:
    return _write(
        tmp_path,
        "gaps.json",
        {
            "domain": "thermoelectric",
            "n_entries": 2,
            "gaps": [
                {
                    "idx": 0,
                    "gap_type": "未探索方向",
                    "statement": "SnTe 共掺杂能带收敛协同机制不明",
                    "novelty": "新知",
                    "formulas": ["SnTe"],
                    "evidence_ids": ["a" * 64],
                    "operability": "以 SnTe 为种子搜索共掺杂",
                },
                {
                    "idx": 1,
                    "gap_type": "矛盾结论",
                    "statement": "Cu2Se 中 Te 取代 Se 的定量影响未见报道",
                    "novelty": "部分已知",
                    "formulas": ["Cu2Se"],
                    "evidence_ids": [],
                    "operability": "搜索 Te 取代比例",
                },
            ],
        },
    )


def _kb_payload(tmp_path: Path) -> Path:
    return _write(
        tmp_path,
        "kb.json",
        [
            {
                "normalized_formula": "GeTe",
                "evidence_ids": ["a" * 64],
                "record": {
                    "properties": [{"name": "figure_of_merit_zT", "value": 1.6}],
                    "synthesis": {"temperature": "623"},
                },
            },
            {
                "normalized_formula": "GeTe",  # 重复公式应去重
                "evidence_ids": [],
                "record": {"properties": [], "synthesis": {}},
            },
        ],
    )


def _findings_payload(tmp_path: Path) -> Path:
    return _write(
        tmp_path,
        "findings/finding_1.json",
        {
            "relation": "GeTe 中 Ti 掺杂 4.0% 提升 zT",
            "hypothesis": "Ti 掺杂可提升 zT",
            "gap_statement": "GeTe 高 Ti 相变-性能关联空白",
            "top_candidates": [
                {
                    "formula": "Ge0.96Ti0.04Te",
                    "dopant": "Ti",
                    "concentration": 4.0,
                    "scores": {"scientific": 0.85, "feasibility": 0.8},
                    "rationale": "文献常见掺杂区间",
                },
                {
                    "formula": "Ge0.94Ti0.06Te",
                    "dopant": "Ti",
                    "concentration": 6.0,
                    "scores": {"scientific": 0.8},
                    "rationale": "文献常见掺杂区间",
                },
            ],
        },
    )


def _validation_payload(tmp_path: Path) -> Path:
    results = [
        {
            "candidate_formula": "Ge0.96Ti0.04Te",
            "host": "GeTe",
            "dopant": "Ti",
            "concentration": 4.0,
            "verdict": "已知",
            "reason": "母体 GeTe 在 oqmd 已收录且稳定",
        },
        {
            "candidate_formula": "Ge0.94Ti0.06Te",
            "host": "GeTe",
            "dopant": "Ti",
            "concentration": 6.0,
            "verdict": "已知",
            "reason": "母体 GeTe 在 oqmd 已收录且稳定",
        },
    ]
    # 两个文件含重复候选 → 去重后 n_checks=2
    _write(tmp_path, "validation/validation_1.json", {"gap_statement": "g", "results": results})
    _write(tmp_path, "validation/validation_2.json", {"gap_statement": "g", "results": results})
    return tmp_path


# ---------------------------------------------------------------- tests


class TestCollectGaps:
    def test_counts_and_evidence(self, tmp_path: Path) -> None:
        out = collect_gaps(_gaps_payload(tmp_path))
        assert out["n_gaps"] == 2
        assert out["n_with_evidence"] == 1
        assert out["novelty_dist"] == {"新知": 1, "部分已知": 1}
        assert out["type_dist"] == {"未探索方向": 1, "矛盾结论": 1}
        assert out["gaps"][0]["n_evidence"] == 1
        assert out["gaps"][1]["n_evidence"] == 0

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        out = collect_gaps(tmp_path / "nope.json")
        assert out["n_gaps"] == 0 and out["gaps"] == []


class TestCollectKb:
    def test_dedup_and_props(self, tmp_path: Path) -> None:
        out = collect_kb(_kb_payload(tmp_path))
        assert len(out) == 1
        assert out[0]["formula"] == "GeTe"
        assert out[0]["properties"] == ["figure_of_merit_zT=1.6"]
        assert out[0]["synthesis_temp"] == "623"
        assert out[0]["n_evidence"] == 1

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert collect_kb(tmp_path / "nope.json") == []


class TestCollectFindings:
    def test_candidates_truncated(self, tmp_path: Path) -> None:
        _findings_payload(tmp_path)
        out = collect_findings(tmp_path / "findings", top_n=1)
        assert out["n_findings"] == 1
        f = out["findings"][0]
        assert len(f["top_candidates"]) == 1
        assert f["top_candidates"][0]["formula"] == "Ge0.96Ti0.04Te"
        assert f["top_candidates"][0]["score"] == 0.85
        assert f["n_candidates"] == 2

    def test_empty_dir(self, tmp_path: Path) -> None:
        out = collect_findings(tmp_path / "empty")
        assert out["n_findings"] == 0 and out["findings"] == []


class TestCollectValidations:
    def test_dedup_and_dist(self, tmp_path: Path) -> None:
        _validation_payload(tmp_path)
        out = collect_validations(tmp_path / "validation")
        assert out["n_checks"] == 2
        assert out["verdict_dist"] == {"已知": 2}

    def test_empty_dir(self, tmp_path: Path) -> None:
        out = collect_validations(tmp_path / "empty")
        assert out["n_checks"] == 0 and out["verdict_dist"] == {}


class TestCollectMisc:
    def test_recall_matrix_latest(self, tmp_path: Path) -> None:
        _write(tmp_path, "eval/recall_matrix_1.json", {"matrix": [{"a": 1}]})
        _write(tmp_path, "eval/recall_matrix_2.json", {"matrix": [{"a": 2}]})
        out = collect_recall_matrix(tmp_path / "eval")
        assert out["matrix"] == [{"a": 2}]  # 取最新

    def test_recall_matrix_missing(self, tmp_path: Path) -> None:
        out = collect_recall_matrix(tmp_path / "eval")
        assert out["matrix"] == []

    def test_ablation_parse(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path, "ablation.json",
            {"arms": {"full": {"mean_best_score": 0.8}}, "gains": {"ga_evolution_gain_pct": 2.65}},
        )
        out = collect_ablation(p)
        assert out["arms"]["full"]["mean_best_score"] == 0.8
        assert out["gains"]["ga_evolution_gain_pct"] == 2.65

    def test_ablation_missing(self, tmp_path: Path) -> None:
        out = collect_ablation(tmp_path / "nope.json")
        assert out["arms"] == {} and out["gains"] == {}

    def test_ensemble_consensus_count(self, tmp_path: Path) -> None:
        md = tmp_path / "ensemble" / "ensemble_1.md"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(
            "## gapA\n- 算法数：1（unknown）｜候选总数：5\n"
            "## gapB\n- 算法数：3（ga,mcts,sr）｜候选总数：8\n",
            encoding="utf-8",
        )
        out = collect_ensemble(md.parent)
        assert out["n_gap_groups"] == 2
        assert out["n_consensus"] == 1

    def test_ensemble_missing(self, tmp_path: Path) -> None:
        out = collect_ensemble(tmp_path / "nope")
        assert out["n_gap_groups"] == 0


class TestRender:
    def test_html_self_contained(self, tmp_path: Path) -> None:
        # 构造最小 payload，验证渲染自检项
        payload = {
            "domain": "test",
            "gaps": {
                "n_gaps": 0, "gaps": [], "novelty_dist": {}, "type_dist": {},
                "n_with_evidence": 0,
            },
            "kb": [], "findings": {"n_findings": 0, "findings": []},
            "validation": {"verdict_dist": {}, "n_checks": 0, "items": []},
            "recall": {"matrix": [], "note": ""},
            "ablation": {"arms": {}, "gains": {}},
            "ensemble": {"n_gap_groups": 0, "n_consensus": 0},
        }
        html = render_html(payload)
        assert "__DATA__" not in html
        assert html.count("</script>") == 2
        assert 'id="demo-data"' in html

    def test_script_injection_escaped(self) -> None:
        # 数据含 "</script>" 时必须转义为 "<\/script>"
        payload = {
            "domain": 'x</script><script>alert(1)</script>',
            "gaps": {
                "n_gaps": 0, "gaps": [], "novelty_dist": {}, "type_dist": {},
                "n_with_evidence": 0,
            },
            "kb": [], "findings": {"n_findings": 0, "findings": []},
            "validation": {"verdict_dist": {}, "n_checks": 0, "items": []},
            "recall": {"matrix": [], "note": ""},
            "ablation": {"arms": {}, "gains": {}},
            "ensemble": {"n_gap_groups": 0, "n_consensus": 0},
        }
        html = render_html(payload)
        assert html.count("</script>") == 2  # 注入的 </script> 已转义
        assert "<\\/script>" in html


class TestBuildPayload:
    def test_real_artifacts_end_to_end(self) -> None:
        # 真实仓库产物 → 全链路不抛错且关键计数合理（运行于项目根）
        payload = build_payload()
        assert payload["gaps"]["n_gaps"] >= 1
        assert payload["findings"]["n_findings"] >= 1
        assert payload["validation"]["n_checks"] >= 1
        assert isinstance(payload["kb"], list)

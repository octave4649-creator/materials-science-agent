"""result_evidence_backfill 单测：finding/验证产物六通道回填。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.evaluation.gap_evidence_backfill import load_kb_index
from src.evaluation.result_evidence_backfill import (
    backfill_finding,
    backfill_results_dir,
    backfill_validation_file,
)

_DOC_KB_EXACT = "a" * 64
_DOC_KB_PARENT = "b" * 64
_DOC_RETRIEVAL = "c" * 64


def _kb_index() -> dict:
    """真实索引（GeTe 精确 + 掺杂母体）。"""
    return load_kb_index(_kb_path())


def _kb_path() -> Path:
    """临时知识库：GeTe（精确）+ 掺杂 Ge0.93Ti0.01Bi0.06Te（母体 GeTe）。"""
    td = Path(tempfile.mkdtemp())
    p = td / "kb.json"
    p.write_text(
        json.dumps(
            [
                {"normalized_formula": "GeTe", "evidence_ids": [_DOC_KB_EXACT]},
                {
                    "normalized_formula": "Ge0.93Ti0.01Bi0.06Te",
                    "evidence_ids": [_DOC_KB_PARENT],
                },
            ]
        ),
        encoding="utf-8",
    )
    return p


def _results_dir() -> Path:
    """临时 results 目录：retrieval 产物 + findings + validation 各一份。"""
    td = Path(tempfile.mkdtemp())
    (td / "findings").mkdir()
    (td / "validation").mkdir()
    (td / "eval").mkdir()
    # 检索产物：一篇 chunk 含 PbTe
    (td / "retrieval_1.json").write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "doc_id": _DOC_RETRIEVAL,
                        "chunk": "PbTe-based thermoelectrics show zT improvement",
                        "title": "PbTe doping study",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    # finding：无证据（gap.formulas 含 GeTe）
    (td / "findings" / "finding_x.json").write_text(
        json.dumps(
            {
                "relation": "GeTe 掺杂关系",
                "gap_statement": "GeTe 研究缺口",
                "gap": {"formulas": ["GeTe"]},
                "top_candidates": [
                    {"host": "GeTe", "formula": "Ge0.96Ti0.04Te"}
                ],
                "evidence_ids": [],
            }
        ),
        encoding="utf-8",
    )
    # validation：无证据（results 含分数式候选）
    (td / "validation" / "validation_x.json").write_text(
        json.dumps(
            {
                "source_finding": "finding_x.json",
                "gap_statement": "GeTe 研究缺口",
                "evidence_ids": [],
                "results": [
                    {
                        "candidate_formula": "Ge0.96Ti0.04Te",
                        "host": "GeTe",
                        "parent_formula": "GeTe",
                        "verdict": "已知",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return td


class TestBackfillFinding:
    def test_fill_from_gap_formula(self) -> None:
        # gap.formulas 含 GeTe → kb_exact + kb_parent 双证据回填
        finding = {
            "relation": "r",
            "gap": {"formulas": ["GeTe"]},
            "top_candidates": [],
            "evidence_ids": [],
        }
        out, stats = backfill_finding(finding, _kb_index(), [])
        assert stats["filled"] is True
        assert _DOC_KB_EXACT in out["evidence_ids"]
        assert _DOC_KB_PARENT in out["evidence_ids"]
        assert out["evidence_backfill"]["sources"][_DOC_KB_EXACT] == "kb_exact"
        assert out["evidence_backfill"]["sources"][_DOC_KB_PARENT] == "kb_parent"

    def test_keep_existing_evidence(self) -> None:
        # 已有证据（继承 Gap）保留，不重复回填
        finding = {
            "relation": "r",
            "gap": {"formulas": ["GeTe"]},
            "top_candidates": [],
            "evidence_ids": [_DOC_KB_EXACT],
        }
        out, stats = backfill_finding(finding, _kb_index(), [])
        assert stats["filled"] is False
        assert out["evidence_ids"] == [_DOC_KB_EXACT]
        assert "evidence_backfill" not in out

    def test_fill_from_top_candidates(self) -> None:
        # gap 无 formulas，top_candidates[].host 命中
        finding = {
            "relation": "r",
            "gap": {"formulas": []},
            "top_candidates": [{"host": "GeTe", "formula": "Ge0.96Ti0.04Te"}],
            "evidence_ids": [],
        }
        out, _ = backfill_finding(finding, _kb_index(), [])
        assert _DOC_KB_EXACT in out["evidence_ids"]

    def test_no_match_keeps_empty(self) -> None:
        # 未命中任何证据 → 保持空，不编造
        finding = {
            "relation": "r",
            "gap": {"formulas": ["LiFePO4"]},
            "top_candidates": [],
            "evidence_ids": [],
        }
        out, stats = backfill_finding(finding, _kb_index(), [])
        assert stats["filled"] is False
        assert out["evidence_ids"] == []


class TestBackfillValidation:
    def test_fill_from_results(self) -> None:
        # 分数式候选 → 名义母体 GeTe → kb 证据回填
        data = {
            "gap_statement": "GeTe 缺口",
            "evidence_ids": [],
            "results": [
                {"candidate_formula": "Ge0.96Ti0.04Te", "host": "GeTe"}
            ],
        }
        out, stats = backfill_validation_file(data, _kb_index(), [])
        assert stats["filled"] is True
        assert _DOC_KB_EXACT in out["evidence_ids"]
        assert "evidence_backfill" in out

    def test_skip_when_existing(self) -> None:
        # 已有证据跳过
        data = {
            "gap_statement": "g",
            "evidence_ids": [_DOC_KB_EXACT],
            "results": [{"candidate_formula": "Ge0.96Ti0.04Te"}],
        }
        out, stats = backfill_validation_file(data, _kb_index(), [])
        assert stats["filled"] is False
        assert out["evidence_ids"] == [_DOC_KB_EXACT]

    def test_no_match_keeps_empty(self) -> None:
        # 未命中保持空
        data = {
            "gap_statement": "g",
            "evidence_ids": [],
            "results": [{"candidate_formula": "LiFePO4"}],
        }
        out, stats = backfill_validation_file(data, _kb_index(), [])
        assert stats["filled"] is False
        assert out["evidence_ids"] == []


class TestBackfillResultsDir:
    def test_batch_dir(self) -> None:
        # 批量回填：finding + validation 各 1 份被填，统计正确
        results_dir = _results_dir()
        stats, per_item = backfill_results_dir(
            "findings", _kb_path(), results_dir
        )
        assert stats["n_items"] == 1
        assert stats["n_filled"] == 1
        # 落盘回读确认
        saved = json.loads(
            (results_dir / "findings" / "finding_x.json").read_text(encoding="utf-8")
        )
        assert saved["evidence_ids"]

        stats_v, _ = backfill_results_dir("validation", _kb_path(), results_dir)
        assert stats_v["n_items"] == 1
        assert stats_v["n_filled"] == 1

    def test_skip_filled(self) -> None:
        # 已回填后重跑 → 全部跳过
        results_dir = _results_dir()
        backfill_results_dir("findings", _kb_path(), results_dir)
        stats2, _ = backfill_results_dir("findings", _kb_path(), results_dir)
        assert stats2["n_filled"] == 0
        assert stats2["n_skipped"] == 1

"""gap_evidence_backfill 单测：六通道回填（kb_exact/kb_parent/kb_similar/retrieval/
retrieval_title/retrieval_parent）。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.evaluation.gap_evidence_backfill import (
    backfill_gaps,
    load_kb_index,
    load_retrieval_papers,
    match_evidence_for_formula,
)

_DOC_KB_EXACT = "a" * 64
_DOC_KB_PARENT = "b" * 64
_DOC_RETRIEVAL = "c" * 64


def _kb_entries() -> list[dict]:
    """构造知识库：GeTe（精确）+ 掺杂 Ge0.93Ti0.01Bi0.06Te（母体为 GeTe）。"""
    return [
        {
            "normalized_formula": "GeTe",
            "evidence_ids": [_DOC_KB_EXACT],
        },
        {
            "normalized_formula": "Ge0.93Ti0.01Bi0.06Te",
            "evidence_ids": [_DOC_KB_PARENT],
        },
    ]


def _papers() -> list[dict]:
    """构造检索产物：一篇 chunk 含 PbTe。"""
    return [
        {
            "doc_id": _DOC_RETRIEVAL,
            "chunk": "PbTe-based thermoelectrics show zT improvement via Na doping",
        },
        {
            "doc_id": "d" * 64,
            "chunk": "unrelated battery cathode content",
        },
    ]


def _gaps(formulas: list[list[str]], existing: list[list[str]] | None = None) -> dict:
    existing = existing or [[] for _ in formulas]
    return {
        "domain": "thermoelectric",
        "gaps": [
            {
                "gap_type": "未探索方向",
                "statement": f"statement {i}",
                "formulas": fs,
                "evidence_ids": list(evs),
            }
            for i, (fs, evs) in enumerate(zip(formulas, existing))
        ],
    }


def load_kb_index_from(entries: list[dict]) -> dict:
    """测试辅助：dict 列表 → 索引（复用真实路径逻辑）。"""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "kb.json"
        p.write_text(json.dumps(entries), encoding="utf-8")
        return load_kb_index(p)


class TestMatchEvidenceForFormula:
    def test_kb_exact_match(self) -> None:
        # GeTe 同时命中 kb_exact（GeTe 条目）与 kb_parent（掺杂条目母体），两者均保留
        found, sources = match_evidence_for_formula(
            "GeTe", load_kb_index_from(_kb_entries()), []
        )
        assert _DOC_KB_EXACT in found
        assert sources[_DOC_KB_EXACT] == "kb_exact"
        assert len(found) == len(set(found))

    def test_kb_parent_match(self) -> None:
        # Gap 公式是母体 GeTe，知识库掺杂公式母体也是 GeTe → kb_parent
        found, sources = match_evidence_for_formula(
            "GeTe", load_kb_index_from(_kb_entries()), []
        )
        assert _DOC_KB_PARENT in found
        assert sources[_DOC_KB_PARENT] == "kb_parent"
        # 精确 + 母体都命中，两者都保留
        assert _DOC_KB_EXACT in found

    def test_retrieval_chunk_match(self) -> None:
        found, sources = match_evidence_for_formula("PbTe", {}, _papers())
        assert found == [_DOC_RETRIEVAL]
        assert sources[_DOC_RETRIEVAL] == "retrieval"

    def test_no_match_returns_empty(self) -> None:
        found, sources = match_evidence_for_formula(
            "Mg3Sb2", load_kb_index_from(_kb_entries()), _papers()
        )
        assert found == []
        assert sources == {}

    def test_kb_similar_match(self) -> None:
        # Gap Bi0.5Sb1.5Te3 vs KB Bi0.5Sb1.5Te：去掉末尾下标数字后一致 → kb_similar
        kb = load_kb_index_from(
            [{"normalized_formula": "Bi0.5Sb1.5Te", "evidence_ids": [_DOC_KB_PARENT]}]
        )
        found, sources = match_evidence_for_formula("Bi0.5Sb1.5Te3", kb, [])
        assert _DOC_KB_PARENT in found
        assert sources[_DOC_KB_PARENT] == "kb_similar"

    def test_kb_similar_not_fired_for_stem_mismatch(self) -> None:
        # GeTe vs KB Ge0.93Ti0.01Bi0.06Te：去掉末尾数字后仍不同 → 不触发 kb_similar
        kb = load_kb_index_from(_kb_entries())
        found, sources = match_evidence_for_formula("GeTe", kb, [])
        assert _DOC_KB_PARENT in found  # 仅 kb_parent 命中
        assert all(v != "kb_similar" for v in sources.values())

    def test_retrieval_parent_match(self) -> None:
        # Gap Bi0.5Sb1.5Te3 → 整数母体 Sb2Te3，chunk 含 Sb2Te3 → retrieval_parent
        papers = [{"doc_id": _DOC_RETRIEVAL, "chunk": "Sb2Te3-based thermoelectric"}]
        found, sources = match_evidence_for_formula("Bi0.5Sb1.5Te3", {}, papers)
        assert _DOC_RETRIEVAL in found
        assert sources[_DOC_RETRIEVAL] == "retrieval_parent"

    def test_retrieval_parent_skipped_for_integer_formula(self) -> None:
        # 整数公式 PbTe 自身即母体 → 不触发 retrieval_parent（避免无意义遍历）
        found, sources = match_evidence_for_formula(
            "PbTe", {}, [{"doc_id": _DOC_RETRIEVAL, "chunk": "PbTe-based"}]
        )
        assert _DOC_RETRIEVAL in found
        assert sources[_DOC_RETRIEVAL] == "retrieval"

    def test_retrieval_title_match(self) -> None:
        # chunk 未命中、标题点名公式 → retrieval_title（覆盖 Mg3Sb2/Cu2Se/CoSb3 类场景）
        papers = [
            {
                "doc_id": _DOC_RETRIEVAL,
                "title": "Mg3Sb2-based thermoelectric materials for power generation",
                "chunk": "unrelated battery cathode content",
            }
        ]
        found, sources = match_evidence_for_formula("Mg3Sb2", {}, papers)
        assert _DOC_RETRIEVAL in found
        assert sources[_DOC_RETRIEVAL] == "retrieval_title"

    def test_retrieval_chunk_priority_over_title(self) -> None:
        # chunk 命中时优先 retrieval 通道，标题通道不重复计数
        papers = [
            {
                "doc_id": _DOC_RETRIEVAL,
                "title": "Mg3Sb2-based thermoelectric materials",
                "chunk": "Mg3Sb2 shows promising zT above 600K",
            }
        ]
        found, sources = match_evidence_for_formula("Mg3Sb2", {}, papers)
        assert found == [_DOC_RETRIEVAL]
        assert sources[_DOC_RETRIEVAL] == "retrieval"

    def test_retrieval_title_no_match_when_absent(self) -> None:
        # 标题与 chunk 均不含公式 → 空
        papers = [
            {
                "doc_id": _DOC_RETRIEVAL,
                "title": "thermoelectric power generation review",
                "chunk": "unrelated battery cathode content",
            }
        ]
        found, sources = match_evidence_for_formula("Mg3Sb2", {}, papers)
        assert found == []
        assert sources == {}

    def test_kb_parent_variable_formula(self) -> None:
        # 变量式 Gap（Ge1-x-yTixBiyTe）名义母体 GeTe == KB 掺杂条目母体 → kb_parent
        kb = load_kb_index_from(_kb_entries())
        found, sources = match_evidence_for_formula("Ge1-x-yTixBiyTe", kb, [])
        assert _DOC_KB_PARENT in found
        assert sources[_DOC_KB_PARENT] == "kb_parent"

    def test_retrieval_parent_variable_formula(self) -> None:
        # 变量式 Gap（Ge1-xBixTe）名义母体 GeTe 出现在 chunk → retrieval_parent
        papers = [{"doc_id": _DOC_RETRIEVAL, "chunk": "GeTe-based thermoelectric with Bi doping"}]
        found, sources = match_evidence_for_formula("Ge1-xBixTe", {}, papers)
        assert _DOC_RETRIEVAL in found
        assert sources[_DOC_RETRIEVAL] == "retrieval_parent"

    def test_empty_formula_returns_empty(self) -> None:
        found, sources = match_evidence_for_formula("", {}, [])
        assert found == []
        assert sources == {}


class TestLoadIndexAndPapers:
    def test_load_kb_index_dedup_by_evidence_count(self, tmp_path) -> None:
        kb_path = tmp_path / "kb.json"
        kb_path.write_text(
            json.dumps(
                [
                    {"normalized_formula": "GeTe", "evidence_ids": [1]},
                    {"normalized_formula": "GeTe", "evidence_ids": [1, 2]},
                    {"normalized_formula": "", "evidence_ids": [3]},
                ]
            ),
            encoding="utf-8",
        )
        index = load_kb_index(kb_path)
        assert set(index) == {"GeTe"}
        assert index["GeTe"]["evidence_ids"] == [1, 2]

    def test_load_retrieval_papers_dedup_doc_id(self, tmp_path) -> None:
        d = tmp_path / "retrieval_1.json"
        d.write_text(
            json.dumps(
                {"papers": [{"doc_id": "x", "chunk": "1"}, {"doc_id": "x", "chunk": "2"}]}
            ),
            encoding="utf-8",
        )
        papers = load_retrieval_papers(tmp_path)
        assert len(papers) == 1

    def test_load_retrieval_missing_dir_returns_empty(self, tmp_path) -> None:
        assert load_retrieval_papers(tmp_path / "nope") == []

    def test_load_kb_missing_returns_empty_index(self, tmp_path) -> None:
        assert load_kb_index(tmp_path / "nope.json") == {}


class TestBackfillGaps:
    def test_fills_and_preserves_existing(self) -> None:
        gaps = _gaps(
            formulas=[["GeTe"], ["PbTe"], ["Mg3Sb2"]],
            existing=[[_DOC_KB_EXACT], [], []],
        )
        gaps, stats, per_gap = backfill_gaps(
            gaps, load_kb_index_from(_kb_entries()), _papers()
        )
        # Gap0：已有保留 + kb_exact + kb_parent 并集去重
        assert gaps["gaps"][0]["evidence_ids"] == [_DOC_KB_EXACT, _DOC_KB_PARENT]
        assert gaps["gaps"][0]["evidence_backfill"]["n_existing"] == 1
        assert gaps["gaps"][0]["evidence_backfill"]["n_added"] == 1
        # Gap1：PbTe 检索命中
        assert gaps["gaps"][1]["evidence_ids"] == [_DOC_RETRIEVAL]
        # Gap2：无匹配保持空
        assert gaps["gaps"][2]["evidence_ids"] == []
        assert stats["n_filled"] == 2
        assert stats["n_empty_after"] == 1
        assert per_gap[2]["filled"] is False

    def test_dedup_cross_formula(self) -> None:
        # 同一 Gap 两个公式都命中同一证据 → 只保留一次
        gaps = _gaps(formulas=[["GeTe", "Ge0.93Ti0.01Bi0.06Te"]])
        gaps, stats, _ = backfill_gaps(
            gaps, load_kb_index_from(_kb_entries()), []
        )
        evids = gaps["gaps"][0]["evidence_ids"]
        assert len(evids) == len(set(evids))
        assert _DOC_KB_EXACT in evids and _DOC_KB_PARENT in evids
        assert stats["n_new_evidence"] == 2

    def test_unchanged_when_existing_no_new(self) -> None:
        gaps = _gaps(formulas=[["Mg3Sb2"]], existing=[["z" * 64]])
        gaps, stats, _ = backfill_gaps(
            gaps, load_kb_index_from(_kb_entries()), _papers()
        )
        assert stats["n_unchanged"] == 1
        assert gaps["gaps"][0]["evidence_ids"] == ["z" * 64]

    def test_source_dist_accumulates(self) -> None:
        gaps = _gaps(formulas=[["GeTe"], ["PbTe"]])
        _, stats, _ = backfill_gaps(
            gaps, load_kb_index_from(_kb_entries()), _papers()
        )
        assert stats["source_dist"] == {
            "kb_exact": 1, "kb_parent": 1, "retrieval": 1,
        }

    def test_evidence_backfill_sources_recorded(self) -> None:
        gaps = _gaps(formulas=[["GeTe"], ["PbTe"]])
        gaps, _, _ = backfill_gaps(
            gaps, load_kb_index_from(_kb_entries()), _papers()
        )
        s0 = gaps["gaps"][0]["evidence_backfill"]["sources"]
        assert s0[_DOC_KB_EXACT] == "kb_exact"
        assert s0[_DOC_KB_PARENT] == "kb_parent"
        assert gaps["gaps"][1]["evidence_backfill"]["sources"][_DOC_RETRIEVAL] == "retrieval"

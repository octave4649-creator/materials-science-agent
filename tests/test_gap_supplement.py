"""gap_supplement 单测：无证据 Gap 缺失母体清单与补检查询生成。"""
from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.gap_supplement import (
    KEYWORD_MAP,
    _pick_keywords,
    build_query_for_gap,
    extract_missing_hosts,
    find_evidence_missing_gaps,
    generate_supplement_plan,
    save_plan,
)


def _gaps() -> dict:
    """构造 gaps.json：2 条有证据 + 2 条无证据（SnTe 与 Mg3Sb2）。"""
    return {
        "domain": "thermoelectric",
        "gaps": [
            {
                "idx": 0,
                "gap_type": "未探索方向",
                "statement": "GeTe 共掺杂与能带收敛协同提升热电优值",
                "formulas": ["GeTe"],
                "evidence_ids": ["a" * 64],
            },
            {
                "idx": 1,
                "gap_type": "矛盾结论",
                "statement": "SnTe 共掺杂与掺杂对能带收敛的影响存在争议",
                "formulas": ["SnTe"],
                "evidence_ids": [],
            },
            {
                "idx": 2,
                "gap_type": "缺失知识连接",
                "statement": "Mg3Sb2 载流子迁移率与阳离子空位的关系未被系统研究",
                "formulas": ["Mg3Sb2", "mg3sb2"],
                "evidence_ids": None,
            },
            {
                "idx": 3,
                "gap_type": "未探索方向",
                "statement": "ZrNiSn 半赫斯勒合金热稳定性",
                "formulas": [],
                "evidence_ids": [],
            },
        ],
    }


class TestFindEvidenceMissingGaps:
    def test_only_empty_evidence_returned(self) -> None:
        missing = find_evidence_missing_gaps(_gaps())
        # 有证据的 idx0 排除；None 视为空（idx2）；formulas 空但证据空也算（idx3）
        assert [g["idx"] for g in missing] == [1, 2, 3]

    def test_no_gaps_returns_empty(self) -> None:
        assert find_evidence_missing_gaps({"gaps": []}) == []


class TestExtractMissingHosts:
    def test_dedup_and_preserve_order(self) -> None:
        missing = find_evidence_missing_gaps(_gaps())
        hosts = extract_missing_hosts(missing)
        # SnTe、Mg3Sb2（小写 mg3sb2 归一化去重）、无公式 Gap 不产生母体
        assert hosts == ["SnTe", "Mg3Sb2"]

    def test_empty_input(self) -> None:
        assert extract_missing_hosts([]) == []


class TestPickKeywords:
    def test_subword_mutual_exclusion(self) -> None:
        # 「共掺杂」命中后跳过子词「掺杂」→ 只留 codoping
        kws = _pick_keywords("SnTe 共掺杂与能带收敛")
        assert "codoping" in kws
        assert "doping" not in kws

    def test_dedup_same_keyword(self) -> None:
        kws = _pick_keywords("掺杂掺杂掺杂")
        assert kws == ["doping"]

    def test_max_kw_cap(self) -> None:
        kws = _pick_keywords("共掺杂 掺杂 能带收敛 晶格热导率 载流子迁移率")
        assert len(kws) <= 2

    def test_no_match_returns_empty(self) -> None:
        assert _pick_keywords("无关内容") == []

    def test_map_keys_valid(self) -> None:
        # KEYWORD_MAP 键非空、值非空
        assert all(zh and en for zh, en in KEYWORD_MAP.items())


class TestBuildQueryForGap:
    def test_query_contains_host_keywords_thermoelectric(self) -> None:
        q = build_query_for_gap(_gaps()["gaps"][1])
        parts = q.split()
        assert parts[0] == "SnTe"
        assert "thermoelectric" in parts
        assert "codoping" in parts
        assert "doping" not in parts  # 互斥消歧后无冗余

    def test_query_with_no_formula_uses_empty_host(self) -> None:
        q = build_query_for_gap(_gaps()["gaps"][3])
        # 无母体时仍保留主题词与热电限定
        assert "thermoelectric" in q
        assert "ZrNiSn" not in q  # 母体来自 formulas，缺失则无


class TestGenerateSupplementPlan:
    def test_plan_counts_match(self) -> None:
        plan = generate_supplement_plan(_gaps())
        missing = find_evidence_missing_gaps(_gaps())
        assert plan["n_missing_gaps"] == len(missing) == 3
        assert len(plan["queries"]) == len(missing)
        assert len(plan["batch_commands"]) == len(missing)
        assert len(plan["next_steps"]) == 3
        # 缺失母体去重后为 2 个
        assert len(plan["missing_hosts"]) == 2

    def test_queries_have_gap_idx(self) -> None:
        plan = generate_supplement_plan(_gaps())
        idxs = [item["gap_idx"] for item in plan["queries"]]
        assert idxs == [1, 2, 3]

    def test_batch_commands_executable_shape(self) -> None:
        plan = generate_supplement_plan(_gaps())
        for cmd in plan["batch_commands"]:
            assert cmd.startswith("python scripts/run_retrieval.py")
            assert "--top-k 5 --mode fast" in cmd


class TestSavePlan:
    def test_save_and_reload(self, tmp_path: Path) -> None:
        out = tmp_path / "plan.json"
        plan = generate_supplement_plan(_gaps())
        save_plan(plan, out)
        assert out.exists()
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["n_missing_gaps"] == 3
        assert loaded["queries"] == plan["queries"]

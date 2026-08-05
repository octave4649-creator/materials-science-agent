"""模块 5 阶段 4 消融实验测试：三臂运行/指标提取/汇总统计（离线、无 LLM）。"""
from __future__ import annotations

import json

import pytest

from src.search.ablation import (
    ARMS,
    _arm_llm_only,
    build_report,
    collect_metrics,
    run_ablation,
)
from src.search.ga_search import LLMRoles
from src.search.schemas import SPRFinding


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """清空 LLM key（规则模式）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def _roles() -> LLMRoles:
    """规则模式角色（chat 永不调用）。"""
    return LLMRoles(chat_json=lambda s, u, k: {"_": "_"})


GAP = {"statement": "PbTe 中 Na/Sr 共掺杂协同效应空白", "formulas": ["PbTe"]}


def test_arms_defined() -> None:
    """三臂齐全且顺序固定。"""
    assert ARMS == ("full", "rule", "llm")


def test_llm_only_rule_fallback() -> None:
    """纯 LLM 臂在 LLM 不可用时退化为规则种子+打分（与 rule 公平对比）。"""
    finding = _arm_llm_only(
        gap_statement=GAP["statement"], hosts=["PbTe"], roles=_roles(), llm_on=False
    )
    assert isinstance(finding, SPRFinding)
    assert finding.top_candidates
    assert finding.confidence > 0
    assert not finding.search_log.used_llm


def test_collect_metrics() -> None:
    """指标提取：分数/成本/多样性。"""
    roles = _roles()
    finding = _arm_llm_only(
        gap_statement=GAP["statement"], hosts=["PbTe"], roles=roles, llm_on=False
    )
    m = collect_metrics(finding, "llm")
    assert m.arm == "llm"
    assert m.best_score > 0
    assert m.best_formula
    assert m.unique_dopants > 0
    assert m.llm_calls == 0


def test_rule_mode_arms_identical() -> None:
    """规则模式下 full/rule 两臂输出一致（GA 确定性子进程），验证消融公平性。"""
    f_full = run_ablation([GAP], top_n=1, generations=2, pop_size=8, llm_on=False)
    full = next(m for m in f_full if m.arm == "full")
    rule = next(m for m in f_full if m.arm == "rule")
    # 规则模式下 full 与 rule 都是 GA+规则打分，best 分数应一致
    assert full.best_score == rule.best_score
    assert full.best_formula == rule.best_formula


def test_build_report_gains() -> None:
    """汇总统计与增益计算（构造可控指标验证公式）。"""
    metrics = [
        # full 臂：3 个 gap，分数 0.9/0.8/0.7 → 均值 0.8
        _mk_metric("full", 0.9), _mk_metric("full", 0.8), _mk_metric("full", 0.7),
        # rule 臂：均值 0.6 → 融合增益 (0.8-0.6)/0.6 = 33.33%
        _mk_metric("rule", 0.6), _mk_metric("rule", 0.6), _mk_metric("rule", 0.6),
        # llm 臂：均值 0.7 → GA 演化增益 (0.8-0.7)/0.7 ≈ 14.29%
        _mk_metric("llm", 0.7), _mk_metric("llm", 0.7), _mk_metric("llm", 0.7),
    ]
    report = build_report(metrics)
    assert report["arms"]["full"]["mean_best_score"] == pytest.approx(0.8)
    assert report["gains"]["llm_fusion_gain_pct"] == pytest.approx(33.33, abs=0.01)
    assert report["gains"]["ga_evolution_gain_pct"] == pytest.approx(14.29, abs=0.01)
    assert report["gains"]["llm_proposal_vs_rule_pct"] == pytest.approx(16.67, abs=0.01)
    assert report["n_gaps"] == 3


def _mk_metric(arm: str, score: float) -> object:
    """构造单条 ArmMetrics（复用 dataclass 导入）。"""
    from src.search.ablation import ArmMetrics

    return ArmMetrics(
        arm=arm, gap_statement=f"gap-{arm}", best_score=score,
        best_formula=f"{arm}-X", llm_calls=2, llm_failures=0,
        n_candidates=5, unique_dopants=3,
    )


def test_ablation_json_serializable() -> None:
    """报告可 JSON 序列化（供落盘）。"""
    metrics = run_ablation([GAP], top_n=1, generations=1, pop_size=6, llm_on=False)
    report = build_report(metrics)
    dumped = json.dumps(report, ensure_ascii=False)
    assert '"arms"' in dumped
    assert '"gains"' in dumped


def test_candidate_scores_assigned() -> None:
    """纯 LLM 臂规则模式：候选分数已赋（scientific 非空）。"""
    roles = _roles()
    finding = _arm_llm_only(
        gap_statement=GAP["statement"], hosts=["PbTe"], roles=roles, llm_on=False
    )
    for c in finding.top_candidates:
        assert c.scores.get("scientific", 0) > 0

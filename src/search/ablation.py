"""模块 5 阶段 4：GA vs 纯规则 vs 纯 LLM 消融实验。

量化 LLM 三角色融合的增益（对齐 `.trae/rules/05-route-a-SPR.md` 融合深度要求）：

- arm `full`: GA × LLM（生成器/评估器/剪枝器）——完整融合
- arm `rule`: GA 纯规则（`--no-llm` 等价：规则网格种子 + 规则打分）——无 LLM 基线
- arm `llm` : 纯 LLM（一次性生成 + 评估，无 GA 演化算子）——隔离「GA 演化」增益

指标（每 Gap × 每臂）：
- best_score : Top 候选平均分（scientific/feasibility/support 均值）
- llm_calls / llm_failures（成本与稳定性）
- unique_dopants（搜索覆盖多样性）

汇总输出：三臂均值对比 + 两个增益（LLM 融合增益 / GA 演化增益），
落盘 results/ablation/ablation_report.json（固定随机种子，可复现）。
"""
from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from src.search.ga_search import (
    LLMRoles,
    _make_candidates,
    _nominal_formula,
    ga_search,
    rule_score,
)
from src.search.schemas import Candidate, SPRFinding

# 三臂定义（顺序即报告顺序）
ARMS = ("full", "rule", "llm")
# 纯 LLM 臂的候选数上限（与 GA 种群规模解耦，单次生成+评估）
LLM_ONLY_POP = 12


@dataclass
class ArmMetrics:
    """单 Gap × 单臂的指标。"""

    arm: str
    gap_statement: str
    best_score: float = 0.0
    best_formula: str = ""
    llm_calls: int = 0
    llm_failures: int = 0
    n_candidates: int = 0
    unique_dopants: int = 0

    def to_dict(self) -> dict[str, Any]:
        """序列化。"""
        return asdict(self)


def _arm_llm_only(
    *,
    gap_statement: str,
    hosts: list[str],
    roles: LLMRoles,
    llm_on: bool,
) -> SPRFinding:
    """纯 LLM 臂：一次性生成种子 + 批量评估，无演化算子。

    若 LLM 不可用则退化为规则网格种子 + 规则打分（与 rule 臂公平对比）。
    """
    log = roles.log
    log.add(generation=0, action="llm_only_start", n_candidates=0,
            detail="纯 LLM：单次生成+评估（无 GA 演化）")
    pop: list[Candidate] = []
    if llm_on:
        seeds = roles.generate_seeds(gap_statement, hosts)
        if seeds:
            for s in seeds[:LLM_ONLY_POP]:
                host = s.get("host") or (hosts[0] if hosts else "PbTe")
                dopant = s.get("dopant") or "Bi"
                try:
                    conc = float(s.get("concentration") or 6.0)
                except (TypeError, ValueError):
                    conc = 6.0
                pop.append(
                    Candidate(
                        host=host, dopant=dopant, concentration=conc,
                        formula=_nominal_formula(host, dopant, conc),
                        rationale=s.get("rationale", ""), source="llm_seed",
                    )
                )
            log.add(generation=0, action="seed", n_candidates=len(pop),
                    llm_role="generator", detail=f"LLM 生成 {len(pop)} 个种子")
    if not pop:
        base_hosts = hosts[:2] or ["PbTe"]
        per_host = max(1, LLM_ONLY_POP // len(base_hosts))
        for host in base_hosts:
            pop.extend(_make_candidates(host)[:per_host])
        pop = pop[:LLM_ONLY_POP]
        log.add(generation=0, action="seed", n_candidates=len(pop),
                detail="LLM 不可用，规则网格种子（公平对比基线）")

    # 评估（LLM 或规则）
    if llm_on:
        results = roles.evaluate(pop)
        if results:
            for c in pop:
                r = results.get(c.formula)
                if r and isinstance(r, dict):
                    c.scores = {
                        k: float(v) for k, v in r.items()
                        if k in ("scientific", "feasibility", "support")
                        and isinstance(v, (int, float))
                    }
        else:
            for c in pop:
                c.scores = rule_score(c)
    else:
        for c in pop:
            c.scores = rule_score(c)

    kept = sorted(pop, key=lambda c: c.score_avg(), reverse=True)
    best = kept[:5]
    log.add(generation=0, action="done", n_candidates=len(best),
            detail=f"纯 LLM 输出 Top {len(best)} 候选")
    if best:
        top = best[0]
        relation = (
            f"{top.host} 中 {top.dopant} 掺杂（{top.concentration}%）→ "
            f"LLM 直接建议的构效关系（无 GA 演化）"
        )
        hypothesis = (
            f"在 {top.host} 中以 {top.dopant} 掺杂 {top.concentration}% 可提升 zT"
            f"（预期 {top.score_avg():.2f}，需实验/计算验证）"
        )
        mechanism = f"LLM 单次推理建议（理由：{top.rationale[:80]}）"
        confidence = round(top.score_avg(), 2)
    else:
        relation, hypothesis, mechanism, confidence = (
            "未发现候选", "需扩大搜索空间", "搜索未收敛", 0.0
        )
    return SPRFinding(
        relation=relation, hypothesis=hypothesis, mechanism=mechanism,
        top_candidates=best, gap_statement=gap_statement, confidence=confidence,
        search_log=log,
    )


def run_arm(
    arm: str,
    *,
    gap_statement: str,
    hosts: list[str],
    roles: LLMRoles,
    generations: int = 3,
    pop_size: int = 12,
    llm_on: bool = True,
) -> SPRFinding:
    """按臂运行搜索（full/rule 走 GA，llm 走纯 LLM）。"""
    if arm == "full":
        return ga_search(
            gap_statement=gap_statement, hosts=hosts, roles=roles,
            generations=generations, pop_size=pop_size, llm_on=llm_on,
        )
    if arm == "rule":
        return ga_search(
            gap_statement=gap_statement, hosts=hosts, roles=roles,
            generations=generations, pop_size=pop_size, llm_on=False,
        )
    if arm == "llm":
        return _arm_llm_only(
            gap_statement=gap_statement, hosts=hosts, roles=roles, llm_on=llm_on,
        )
    raise ValueError(f"arm 必须是 {ARMS} 之一，收到 {arm!r}")


def collect_metrics(
    finding: SPRFinding, arm: str, oracle: Any | None = None,
) -> ArmMetrics:
    """从 finding 提取单臂指标。

    若提供 oracle（VerificationOracle 真值评分代理），best_score/best_formula
    改用数据库真值统一打分——三臂在同一把尺子上可比（修复 full/rule
    评估器不同导致的分数不可比问题，见 verification_oracle.py docstring）。
    """
    cands = finding.top_candidates
    if oracle and cands:
        scored = sorted(cands, key=lambda c: oracle.mean_score(c), reverse=True)
        best = scored[0]
        best_score = round(oracle.mean_score(best), 3)
    else:
        best = max(cands, key=lambda c: c.score_avg()) if cands else None
        best_score = round(best.score_avg(), 3) if best else 0.0
    dopants = {c.dopant for c in cands if c.dopant}
    return ArmMetrics(
        arm=arm,
        gap_statement=finding.gap_statement,
        best_score=best_score,
        best_formula=best.formula if best else "",
        llm_calls=finding.search_log.llm_calls,
        llm_failures=finding.search_log.llm_failures,
        n_candidates=len(cands),
        unique_dopants=len(dopants),
    )


def run_ablation(
    gaps: list[dict[str, Any]],
    *,
    top_n: int = 5,
    generations: int = 3,
    pop_size: int = 12,
    llm_on: bool = True,
    chat_json: Any = None,
    oracle: Any = None,
) -> list[ArmMetrics]:
    """对 Gap 清单运行三臂消融，返回全部指标（固定 rng seed 由 ga_search 内部保证）。

    参数:
        gaps: Gap 清单（gaps.json 的 gaps 字段）
        top_n: 参与消融的 Gap 数上限
        generations: GA 代数（full/rule）
        pop_size: GA 种群大小
        llm_on: full/llm 臂是否启用 LLM（关闭时与 rule 等价，用于对照实验）
        chat_json: 可注入的 chat_json（测试用），缺省用 src.common.llm.llm_chat_json
        oracle: VerificationOracle 真值评分代理（可选）；提供后 best_score
            用数据库验证真值统一打分，三臂公平可比

    返回:
        每 Gap × 每臂一条 ArmMetrics。
    """
    from src.common.llm import llm_chat_json

    chat = chat_json or llm_chat_json
    out: list[ArmMetrics] = []
    for gap in gaps[:top_n]:
        statement = gap.get("statement", "")
        hosts = gap.get("formulas") or ["PbTe"]
        for arm in ARMS:
            roles = LLMRoles(chat_json=chat)
            finding = run_arm(
                arm, gap_statement=statement, hosts=hosts, roles=roles,
                generations=generations, pop_size=pop_size,
                llm_on=llm_on and arm != "rule",
            )
            out.append(collect_metrics(finding, arm, oracle=oracle))
    return out


def build_report(metrics: list[ArmMetrics]) -> dict[str, Any]:
    """三臂汇总统计 + 增益量化（均值/中位数/成本/多样性 + LLM 融合与 GA 演化增益）。"""
    arms: dict[str, list[ArmMetrics]] = {}
    for m in metrics:
        arms.setdefault(m.arm, []).append(m)

    def _agg(items: list[ArmMetrics]) -> dict[str, Any]:
        scores = [m.best_score for m in items]
        mean = statistics.fmean(scores) if scores else 0.0
        return {
            "n": len(items),
            "mean_best_score": round(mean, 4),
            "median_best_score": round(statistics.median(scores), 4) if scores else 0.0,
            "max_best_score": round(max(scores), 4) if scores else 0.0,
            "total_llm_calls": sum(m.llm_calls for m in items),
            "total_llm_failures": sum(m.llm_failures for m in items),
            "mean_unique_dopants": round(
                statistics.fmean(m.unique_dopants for m in items), 2
            ) if items else 0.0,
        }

    per_arm = {a: _agg(arms.get(a, [])) for a in ARMS}

    def _gain(a: str, b: str) -> float | None:
        """相对增益（a 相对 b，百分数；b 为 0 时返回 None）。"""
        base = per_arm[b]["mean_best_score"]
        if not base:
            return None
        return round((per_arm[a]["mean_best_score"] - base) / base * 100.0, 2)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_gaps": len({m.gap_statement for m in metrics}),
        "arms": per_arm,
        "gains": {
            "llm_fusion_gain_pct": _gain("full", "rule"),
            "ga_evolution_gain_pct": _gain("full", "llm"),
            "llm_proposal_vs_rule_pct": _gain("llm", "rule"),
        },
        "per_gap_metrics": [m.to_dict() for m in metrics],
    }


def save_report(report: dict[str, Any], out_dir: Any) -> Any:
    """落盘消融报告（results/ablation/ablation_report.json）。"""
    from pathlib import Path

    out = Path(out_dir) / "ablation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out

"""矛盾检测：同体系多文献数值对比（Gap 识别方法 2）。

对齐 `.trae/rules/04-literature-agent.md` 第 4.2.2 节：
对同一体系的多条抽取记录做数值对比，标记冲突结论。
不同文献对同一体系同一性能的报道值差异超阈值 → 「矛盾结论」Gap。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.extraction.knowledge_base import KnowledgeBase
from src.gap.coverage import normalize_prop_name
from src.gap.schemas import GapCandidate

# 默认冲突阈值：相对差异 > 30% 或绝对差异 > 0.1
DEFAULT_REL_THRESHOLD = 0.3
DEFAULT_ABS_THRESHOLD = 0.1


def _values_by_prop(
    kb: KnowledgeBase,
) -> dict[str, dict[str, list[tuple[float, list[str]]]]]:
    """按 体系 × 性能名 收集数值与证据（数值为 None 的跳过）。

    返回:
        {formula: {prop_name: [(value, evidence_ids), ...]}}
    """
    out: dict[str, dict[str, list[tuple[float, list[str]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for entry in kb.entries:
        formula = entry.normalized_formula
        for prop in entry.record.properties:
            if prop.value is None:
                continue
            key = normalize_prop_name(prop.name)
            if not key:
                continue
            out[formula][key].append((prop.value, entry.evidence_ids))
    return dict(out)


def _conflict_ratio(v1: float, v2: float) -> float:
    """相对差异（分母取均值，防除零）。"""
    denom = max(abs(v1), abs(v2), 1e-9)
    return abs(v1 - v2) / denom


def detect_contradictions(
    kb: KnowledgeBase,
    *,
    rel_threshold: float = DEFAULT_REL_THRESHOLD,
    abs_threshold: float = DEFAULT_ABS_THRESHOLD,
    max_gaps: int = 10,
) -> list[GapCandidate]:
    """检测同体系矛盾结论。

    参数:
        kb: 知识库
        rel_threshold: 相对差异阈值（默认 0.3）
        abs_threshold: 绝对差异阈值（默认 0.1，防小数值误报）
        max_gaps: 返回的最大 Gap 数

    返回:
        矛盾结论 Gap 候选列表（含冲突数值与证据回链）。
    """
    by_prop = _values_by_prop(kb)
    gaps: list[GapCandidate] = []
    for formula, props in by_prop.items():
        for prop_name, values in props.items():
            # 仅多来源报道时比较（≥2 个不同值）
            if len(values) < 2:
                continue
            seen: list[tuple[float, list[str]]] = []
            for value, evids in values:
                conflicted = False
                for prev, prev_evids in seen:
                    if (
                        _conflict_ratio(value, prev) > rel_threshold
                        and abs(value - prev) > abs_threshold
                    ):
                        conflicted = True
                        break
                if conflicted:
                    gaps.append(
                        GapCandidate(
                            gap_type="矛盾结论",
                            statement=(
                                f"{formula} 的 {prop_name} 报道存在矛盾："
                                f"{prev} vs {value}"
                            ),
                            rationale=(
                                f"不同文献对同一体系同一性能的报道差异超过阈值"
                                f"（相对 >{rel_threshold:.0%} 且绝对 >{abs_threshold}），"
                                "可能是制备条件、测量方法或计算参数差异导致，"
                                "值得系统对比研究"
                            ),
                            formulas=[formula],
                            evidence_ids=sorted(set(prev_evids + evids)),
                            novelty="部分已知",
                            operability=(
                                f"以 {formula} 的 {prop_name} 矛盾为切入点，"
                                "对比制备/测量条件，构建条件-性能关联"
                            ),
                            confidence=0.6,
                            source="contradiction",
                        )
                    )
                    if len(gaps) >= max_gaps:
                        return gaps
                    break
                seen.append((value, evids))
    return gaps


def contradiction_stats(kb: KnowledgeBase) -> dict[str, Any]:
    """矛盾统计（审计用）。"""
    by_prop = _values_by_prop(kb)
    n_multi = sum(1 for props in by_prop.values() for vs in props.values() if len(vs) >= 2)
    return {"n_multi_source_props": n_multi, "n_formulas": len(by_prop)}

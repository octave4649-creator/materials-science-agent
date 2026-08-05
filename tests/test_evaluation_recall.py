"""评测模块：已知关系召回率计算器测试（host/dopant/浓度容差匹配）。"""
from __future__ import annotations

from src.evaluation.recall import (
    aggregate_recall,
    candidate_matches,
    hit_at_k,
    hit_at_ks,
)


def _candidate(host: str, dopant: str, conc: float, **kw) -> dict:
    """候选最小形态（含 host/dopant/concentration 字段即可）。"""
    return {"host": host, "dopant": dopant, "concentration": conc, **kw}


def _fact(host: str = "PbTe", dopant: str = "Na", concentration: float = 2.0) -> dict:
    return {"host": host, "dopant": dopant, "concentration": concentration}


def test_exact_match() -> None:
    """完全一致的 host/dopant/浓度 → 命中。"""
    assert candidate_matches(_candidate("PbTe", "Na", 2.0), _fact())


def test_concentration_tolerance_match() -> None:
    """浓度在容差内（2.0 vs 2.5，容差 1.5）→ 命中。"""
    assert candidate_matches(_candidate("PbTe", "Na", 2.5), _fact())


def test_concentration_outside_tolerance_miss() -> None:
    """浓度超出容差（2.0 vs 5.0）→ 未命中。"""
    assert not candidate_matches(_candidate("PbTe", "Na", 5.0), _fact())


def test_dopant_case_insensitive() -> None:
    """掺杂元素大小写不敏感（Na vs na）→ 命中。"""
    assert candidate_matches(_candidate("PbTe", "na", 2.0), _fact())


def test_wrong_host_miss() -> None:
    """母体不匹配 → 未命中。"""
    assert not candidate_matches(_candidate("GeTe", "Na", 2.0), _fact())


def test_wrong_dopant_miss() -> None:
    """掺杂元素不匹配 → 未命中。"""
    assert not candidate_matches(_candidate("PbTe", "Sr", 2.0), _fact())


def test_host_normalize_match() -> None:
    """host LaTeX 变体归一化匹配（Ge_{0.93}... 类变体由 normalize_formula 处理）。"""
    # 纯母体应无变体，验证不误伤已掺杂 host 的归一化相等性
    assert candidate_matches(
        _candidate("Mg3Sb2", "Bi", 2.0), _fact("Mg3Sb2", "Bi", 2.0)
    )


def test_hit_at_k_top_position() -> None:
    """期望方案出现在第 3 位 → hit@1 否、hit@3 是。"""
    cands = [
        _candidate("PbTe", "Ti", 4.0),
        _candidate("PbTe", "Bi", 6.0),
        _candidate("PbTe", "Na", 2.0),
    ]
    assert not hit_at_k(cands, _fact(), 1)
    assert hit_at_k(cands, _fact(), 3)
    hits = hit_at_ks(cands, _fact(), (1, 3, 5))
    assert hits == {"hit@1": False, "hit@3": True, "hit@5": True}


def test_aggregate_recall() -> None:
    """跨关系召回率：3 命中 / 5 总 → 0.6。"""
    assert aggregate_recall([True, False, True, False, True]) == 0.6
    assert aggregate_recall([]) == 0.0


def test_empty_expected_invalid() -> None:
    """期望标注缺字段 → 一律未命中（不误报）。"""
    assert not candidate_matches(_candidate("PbTe", "Na", 2.0), {"host": ""})
    assert not candidate_matches(_candidate("PbTe", "Na", 2.0), {"host": "PbTe"})

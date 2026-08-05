"""模块 5 阶段 4 真值评分代理（VerificationOracle）测试：离线、无网络。"""
from __future__ import annotations

import json

from src.search.ablation import collect_metrics
from src.search.ga_search import Candidate
from src.search.schemas import SearchLog, SPRFinding
from src.search.verification_oracle import VerificationOracle

GAP = {"statement": "PbTe 中 Na/Sr 共掺杂协同效应空白", "formulas": ["PbTe"]}


def _write_validation(tmp_path, name: str, results: list[dict]) -> None:
    """写入一个对齐 validation_agent 输出结构的 JSON 文件。"""
    (tmp_path / f"validation_{name}.json").write_text(
        json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8"
    )


def _result(formula: str, host: str, verdict: str, stable: bool = True) -> dict:
    """构造单条验证结果（验证失败 entries 为空，对齐真实直查失败场景）。"""
    entries = [] if verdict == "验证失败" else [
        {"db": "oqmd", "formula": host, "is_stable": stable}
    ]
    return {
        "candidate_formula": formula,
        "host": host,
        "parent_formula": None,
        "dopant": formula.split("0.")[1][:2] if "0." in formula else "Ti",
        "concentration": 6.0,
        "verdict": verdict,
        "entries": entries,
    }


def _candidate(formula: str, host: str, dopant: str = "Ti", conc: float = 4.0) -> Candidate:
    """构造消融候选。"""
    return Candidate(
        host=host, dopant=dopant, concentration=conc, formula=formula,
        rationale="test", source="random",
    )


def test_load_indexes_formula_and_host(tmp_path) -> None:
    """load 索引候选公式与母体（host 去重）。"""
    _write_validation(tmp_path, "1", [_result("Ge0.94Ti0.06Te", "GeTe", "已知", True)])
    _write_validation(tmp_path, "2", [_result("Pb0.94Ti0.06Te", "PbTe", "已知", True)])
    oracle = VerificationOracle(tmp_path)
    assert oracle.load(tmp_path) == 2
    assert "Ge0.94Ti0.06Te" in oracle._formula_table
    assert "PbTe" in oracle._host_table


def test_score_verdict_ordering(tmp_path) -> None:
    """严苛尺子：已知 > 新知 > 反例（反例显著低分）。"""
    _write_validation(tmp_path, "1", [
        _result("Ge0.94Ti0.06Te", "GeTe", "已知", True),
        _result("Pb0.94Ti0.06Te", "PbTe", "反例", False),
        _result("Sn0.94Ti0.06Te", "SnTe", "新知", True),
    ])
    oracle = VerificationOracle(tmp_path)
    known = oracle.mean_score(_candidate("Ge0.94Ti0.06Te", "GeTe"))
    counter = oracle.mean_score(_candidate("Pb0.94Ti0.06Te", "PbTe"))
    novel = oracle.mean_score(_candidate("Sn0.94Ti0.06Te", "SnTe"))
    assert known > novel > counter
    assert counter < 0.6  # 反例被严苛惩罚
    assert known > 0.75  # 已知高分


def test_score_verification_failed_low(tmp_path) -> None:
    """验证失败如实低分（不伪装成新知/反例），且低于同母体已知候选。"""
    _write_validation(tmp_path, "1", [
        _result("Ge0.93Ti0.01Bi0.06Te", "GeTe", "验证失败"),
        _result("Ge0.94Ti0.06Te", "GeTe", "已知", True),
    ])
    oracle = VerificationOracle(tmp_path)
    failed = oracle.mean_score(_candidate("Ge0.93Ti0.01Bi0.06Te", "GeTe"))
    known = oracle.mean_score(_candidate("Ge0.94Ti0.06Te", "GeTe"))
    assert failed < known


def test_score_host_fallback(tmp_path) -> None:
    """未命中候选公式时回退母体表（host 在库且稳定 → 中高分）。"""
    _write_validation(tmp_path, "1", [_result("Ge0.94Ti0.06Te", "GeTe", "已知", True)])
    oracle = VerificationOracle(tmp_path)
    # 候选公式未在表，但 host=GeTe 在库稳定
    s = oracle.mean_score(_candidate("Ge0.90Ti0.10Te", "GeTe"))
    assert s > 0.7
    # 完全未知体系 → 保守分
    s_unk = oracle.mean_score(_candidate("X0.94Ti0.06Y", "XY"))
    assert s_unk < 0.7


def test_load_indexes_parent_formula(tmp_path) -> None:
    """parent_formula（A/B 位拆分解析母体）也索引进 host 表。"""
    _write_validation(tmp_path, "1", [{
        "candidate_formula": "Bi0.5Sb1.5Te3-Ti6%",
        "host": "Bi0.5Sb1.5Te3",
        "parent_formula": "Sb2Te3",
        "dopant": "Ti",
        "concentration": 6.0,
        "verdict": "已知",
        "entries": [{"db": "oqmd", "formula": "Sb2Te3", "is_stable": True}],
    }])
    oracle = VerificationOracle(tmp_path)
    oracle.load(tmp_path)
    assert "Sb2Te3" in oracle._host_table
    # 搜索候选以 Sb2Te3 为宿主时也能命中真值
    s = oracle.mean_score(_candidate("Sb2Te3-Ti6%", "Sb2Te3"))
    assert s > 0.7


def test_collect_metrics_uses_oracle(tmp_path) -> None:
    """collect_metrics 提供 oracle 时 best_score 用真值分（公平可比）。"""
    _write_validation(tmp_path, "1", [
        _result("Ge0.94Ti0.06Te", "GeTe", "已知", True),
        _result("Ge0.96Ti0.04Te", "GeTe", "反例", False),
    ])
    oracle = VerificationOracle(tmp_path)
    # 构造 finding：top_candidates 含一个已知、一个反例
    log = SearchLog()
    log.used_llm = False
    finding = SPRFinding(
        relation="r", hypothesis="h", mechanism="m", gap_statement=GAP["statement"],
        top_candidates=[
            _candidate("Ge0.94Ti0.06Te", "GeTe"),
            _candidate("Ge0.96Ti0.04Te", "GeTe"),
        ],
        confidence=0.5, search_log=log,
    )
    m = collect_metrics(finding, "full", oracle=oracle)
    assert m.best_formula == "Ge0.94Ti0.06Te"  # oracle 下已知候选胜出
    # oracle 分数与 GA 内部 score_avg 不同尺子，但为 0-1
    assert 0.0 < m.best_score <= 1.0

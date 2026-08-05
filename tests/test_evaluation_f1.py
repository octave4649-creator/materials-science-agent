"""评测模块：字段级 F1 计算器测试（对齐语义 + 数值容差 + 空字段跳过）。"""
from __future__ import annotations

import pytest

from src.evaluation.f1 import confusion_to_metrics, extraction_f1, field_confusion


def _rec(**overrides):
    """构造最小五段式抽取记录（dict 形态）。"""
    base = {
        "material": {
            "formula": "Ge0.93Ti0.01Bi0.06Te",
            "composition": "GeTe 掺 Ti 1%、Bi 6%",
            "structure": {"space_group": "Fm-3m", "lattice": None, "phase": "cubic"},
        },
        "properties": [{"name": "zT", "value": 1.6, "unit": None, "condition": "723K"}],
        "methods": [{"type": "EXPERIMENT", "software": "hot press", "key_params": None}],
        "synthesis": {"precursors": None, "temperature": "800°C",
                      "atmosphere": "Ar", "duration": "4h"},
    }
    base.update(overrides)
    return base


def _rule_rec():
    """规则式降级路径形态：仅 formula/temperature/zT/band_gap。"""
    return {
        "material": {"formula": "Ge0.93Ti0.01Bi0.06Te", "composition": None,
                     "structure": {"space_group": None, "lattice": None, "phase": None}},
        "properties": [{"name": "zT", "value": 1.6, "unit": None, "condition": None}],
        "methods": [],
        "synthesis": {"precursors": None, "temperature": "800°C",
                      "atmosphere": None, "duration": None},
    }


def test_perfect_match_all_fields_f1_one() -> None:
    """gold 与 pred 完全一致 → 全部字段 F1=1。"""
    rec = _rec()
    result = extraction_f1([rec], [rec])
    assert result["micro"]["f1"] == 1.0
    assert result["macro"]["f1"] == 1.0
    for field in ("formula", "composition", "structure", "properties", "methods", "synthesis"):
        assert result["per_field"][field]["f1"] == 1.0


def test_rule_missing_fields_recall_zero() -> None:
    """规则式缺 structure/methods/atmosphere/duration → 对应字段 recall=0。"""
    gold = _rec()
    pred = _rule_rec()
    result = extraction_f1([gold], [pred])
    assert result["per_field"]["formula"]["f1"] == 1.0
    assert result["per_field"]["structure"]["recall"] == 0.0
    assert result["per_field"]["methods"]["recall"] == 0.0
    assert result["per_field"]["methods"]["precision"] == 1.0  # 无预测不误伤
    # synthesis 有 temperature 命中（gold 3 项 temp/atm/dur vs pred 1 项）
    assert result["per_field"]["synthesis"]["recall"] == round(1 / 3, 4)
    assert result["per_field"]["properties"]["f1"] == 1.0


def test_empty_empty_field_skipped() -> None:
    """gold/pred 都无 methods 与 structure → 不产生混淆计数（不膨胀）。"""
    rec = _rec(
        material={"formula": "PbTe", "composition": None,
                  "structure": {"space_group": None, "lattice": None, "phase": None}},
        methods=[],
        synthesis={"precursors": None, "temperature": None, "atmosphere": None, "duration": None},
        properties=[{"name": "zT", "value": 1.4, "unit": None, "condition": None}],
    )
    result = extraction_f1([rec], [rec])
    assert result["per_field"]["methods"]["tp"] == 0
    assert result["per_field"]["methods"]["fp"] == 0
    assert result["per_field"]["methods"]["fn"] == 0
    assert result["per_field"]["formula"]["f1"] == 1.0


def test_property_value_tolerance_match() -> None:
    """性能数值容差匹配：1.6 vs 1.61（5% 容差内）→ 命中。"""
    gold = _rec(properties=[{"name": "zT", "value": 1.6, "unit": None, "condition": None}])
    pred = _rec(properties=[{"name": "zT", "value": 1.61, "unit": None, "condition": None}])
    assert field_confusion(gold, pred, "properties") == (1, 0, 0)


def test_property_value_outside_tolerance_miss() -> None:
    """性能数值超出容差 → 漏检（fn=1）。"""
    gold = _rec(properties=[{"name": "zT", "value": 1.6, "unit": None, "condition": None}])
    pred = _rec(properties=[{"name": "zT", "value": 1.0, "unit": None, "condition": None}])
    assert field_confusion(gold, pred, "properties") == (0, 1, 1)


def test_property_name_contains_match() -> None:
    """性能名互含匹配：'zT' vs 'figure of merit zT' → 命中。"""
    gold = _rec(properties=[{"name": "zT", "value": None, "unit": None, "condition": None}])
    pred = _rec(properties=[
        {"name": "figure of merit zT", "value": None, "unit": None, "condition": None}
    ])
    assert field_confusion(gold, pred, "properties") == (1, 0, 0)


def test_formula_latex_normalized_match() -> None:
    """化学式归一化匹配：LaTeX 下标 vs 纯文本 → 命中。"""
    gold = _rec(material={"formula": "Ge0.93Ti0.01Bi0.06Te", "composition": None,
                          "structure": {"space_group": None, "lattice": None, "phase": None}})
    pred = _rec(material={"formula": "Ge_{0.93}Ti_{0.01}Bi_{0.06}Te", "composition": None,
                          "structure": {"space_group": None, "lattice": None, "phase": None}})
    assert field_confusion(gold, pred, "formula") == (1, 0, 0)


def test_hallucinated_field_fp() -> None:
    """gold 无 properties 但 pred 提取出 → 幻觉计数 fp=1。"""
    gold = _rec(properties=[])
    pred = _rec(properties=[{"name": "zT", "value": 1.6, "unit": None, "condition": None}])
    assert field_confusion(gold, pred, "properties") == (0, 1, 0)


def test_mismatched_sample_count_raises() -> None:
    """gold/pred 样本数不一致 → ValueError。"""
    with pytest.raises(ValueError):
        extraction_f1([_rec()], [_rec(), _rec()])


def test_confusion_to_metrics_divide_by_zero() -> None:
    """防除零：全零混淆 → 指标 0。"""
    m = confusion_to_metrics(0, 0, 0)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0
    assert m == {"tp": 0, "fp": 0, "fn": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0}

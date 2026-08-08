"""抽取工具测试：化学式归一化、规则式抽取、去重合并。"""
from __future__ import annotations

from src.extraction.extractor import (
    merge_records,
    normalize_formula,
    rule_based_extract,
)
from src.extraction.schemas import ExtractionRecord, Material, PropertyEntry


def test_normalize_latex_formula() -> None:
    """LaTeX 化学式归一化。"""
    raw = r"\mathrm{Ge}_{0.93}\mathrm{Ti}_{0.01}\mathrm{Bi}_{0.06}\mathrm{Te}"
    assert normalize_formula(raw) == "Ge0.93Ti0.01Bi0.06Te"


def test_normalize_html_formula() -> None:
    """HTML 下标归一化。"""
    assert normalize_formula("Bi<sub>2</sub>Te<sub>3</sub>") == "Bi2Te3"


def test_normalize_plain() -> None:
    """纯文本化学式保持不变。"""
    assert normalize_formula("PbTe") == "PbTe"


def test_rule_extract_latex_chunk() -> None:
    """规则式抽取 LaTeX 片段：化学式 + zT + 温度。"""
    text = (
        r"The highest $ZT$ of 1.6 is achieved for "
        r"$\mathrm{Ge}_{0.93}\mathrm{Ti}_{0.01}\mathrm{Bi}_{0.06}\mathrm{Te}$ at $623\mathrm{K}$"
    )
    rec = rule_based_extract(text, doc_id="d1")
    assert rec is not None
    assert rec.material.formula == "Ge0.93Ti0.01Bi0.06Te"
    zt = [p for p in rec.properties if p.name == "figure_of_merit_zT"]
    assert zt and zt[0].value == 1.6
    assert rec.synthesis.temperature is not None


def test_rule_extract_html_chunk() -> None:
    """规则式抽取 HTML 化学式。"""
    text = "doping of nanostructured Bi<sub>2</sub>Te<sub>3</sub> thermoelectrics"
    rec = rule_based_extract(text)
    assert rec is not None
    assert rec.material.formula == "Bi2Te3"


def test_rule_extract_no_material_returns_none() -> None:
    """无材料信息的文本返回 None。"""
    assert rule_based_extract("random text without chemical formula here") is None


def test_rule_extract_rejects_unit_formula() -> None:
    """单位误提取过滤：Wm^-1K^-1 不应被当作化学式。"""
    text = r"$\kappa_{\mathrm{min}} = 0.42\mathrm{Wm}^{-1}\mathrm{K}^{-1}$"
    assert rule_based_extract(text) is None


def test_rule_extract_skips_unit_finds_formula() -> None:
    """同时含单位与真实化学式的文本：跳过单位，提取真实化学式。"""
    text = (
        r"the thermal conductivity of 0.42\mathrm{Wm}^{-1}\mathrm{K}^{-1} "
        r"for $\mathrm{Ca}_{5}\mathrm{In}_{2}\mathrm{Sb}_{6}$"
    )
    rec = rule_based_extract(text)
    assert rec is not None
    assert rec.material.formula == "Ca5In2Sb6"


# ---------- composition 提取（gold 复算 recall=0 修复） ----------


def test_rule_extract_composition_doped() -> None:
    """掺杂描述："Ti and Bi doped" → composition 有值。"""
    text = "The highest ZT of 1.6 is achieved for Ti and Bi doped GeTe"
    rec = rule_based_extract(text)
    assert rec is not None
    assert rec.material.composition == "Ti and Bi doped"


def test_rule_extract_composition_single_doped() -> None:
    """单元素掺杂："Zn-doped" → composition。"""
    text = "The peak zT in Zn-doped Sr5In2Sb6 is lower"
    rec = rule_based_extract(text)
    assert rec is not None
    assert rec.material.composition == "Zn-doped"


def test_rule_extract_composition_or_doping() -> None:
    """或掺杂："Pb or Ca doping" → composition。"""
    text = "Pb or Ca doping can enhance the thermoelectric figure of merit of Bi2Te3"
    rec = rule_based_extract(text)
    assert rec is not None
    assert rec.material.composition == "Pb or Ca doping"


def test_rule_extract_composition_ptype() -> None:
    """载流子类型："p-type" → composition。"""
    text = "zT can be enhanced for p-type PbTe at 900 K"
    rec = rule_based_extract(text)
    assert rec is not None
    assert rec.material.composition == "p-type"


def test_rule_extract_composition_absent_none() -> None:
    """无掺杂描述 → composition 保持 None（不引入误报）。"""
    text = "the thermoelectric figure of merit for Ca5In2Sb6"
    rec = rule_based_extract(text)
    assert rec is not None
    assert rec.material.composition is None


def test_merge_records_same_formula() -> None:
    """同 formula 记录合并：属性并集。"""
    r1 = ExtractionRecord(
        material=Material(formula="PbTe"), properties=[PropertyEntry(name="zT", value=1.0)]
    )
    r2 = ExtractionRecord(
        material=Material(formula="PbTe"),
        properties=[PropertyEntry(name="band_gap", value=0.31, unit="eV")],
    )
    merged = merge_records([r1, r2])
    assert len(merged) == 1
    names = {p.name for p in merged[0].properties}
    assert names == {"zT", "band_gap"}


def test_merge_records_dedupe_duplicate_props() -> None:
    """合并时重复属性去重。"""
    r1 = ExtractionRecord(
        material=Material(formula="PbTe"), properties=[PropertyEntry(name="zT", value=1.0)]
    )
    r2 = ExtractionRecord(
        material=Material(formula="PbTe"), properties=[PropertyEntry(name="zT", value=1.0)]
    )
    merged = merge_records([r1, r2])
    assert len(merged[0].properties) == 1

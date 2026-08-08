"""规则式抽取与归一化工具。

LLM 未配置或调用失败时的降级路径（00-project-rules.md 3.3 可回退要求）：
从文献片段中正则提取化学式、温度、性能数值等，保证流水线不中断。
同时提供化学式归一化（LaTeX / HTML 标记 → 纯文本），供 LLM 结果清洗与去重。
"""
from __future__ import annotations

import re

from src.extraction.schemas import (
    ExtractionRecord,
    Material,
    PropertyEntry,
    SourceRef,
    SynthesisInfo,
)

# LaTeX 化学式：\mathrm{Ge}_{0.93}\mathrm{Ti}_{0.01} → Ge0.93Ti0.01
_LATEX_RE = re.compile(
    r"\\mathrm\{([A-Za-z][a-z]?)\}|\\mathrm\{([^}]+)\}|\\operatorname\{([^}]+)\}"
)
_SUBSCRIPT_RE = re.compile(r"[\{\}]")
# HTML 下标标签
_HTML_SUB_RE = re.compile(r"</?sub>", re.IGNORECASE)
# 温度（K / °C，兼容 LaTeX \mathrm{K} 包裹）
_TEMP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:\\mathrm\{)?°?[KkCc]\}?(?=[\s\.,;)\}$]|$)"
)
# zT 值（兼容 $ 分隔符，如 "$ZT$ of 1.6"）
_ZT_RE = re.compile(
    r"[zZ]T[$\s]*(?:of|is|=|to|values?|up to)?\s*[~≈]?\s*[$\s]*(\d+(?:\.\d+)?)"
)
# 带隙
_GAP_RE = re.compile(
    r"band\s*gap\s*(?:of|is|=|~|≈)?\s*(\d+(?:\.\d+)?)\s*(e[Vv])?"
)


def normalize_formula(raw: str | None) -> str:
    """归一化化学式：去 LaTeX/HTML 标记与空白，统一为纯文本。

    示例:
        ``\\mathrm{Ge}_{0.93}\\mathrm{Ti}_{0.01}\\mathrm{Bi}_{0.06}\\mathrm{Te}``
        → ``Ge0.93Ti0.01Bi0.06Te``
        ``Bi<sub>2</sub>Te<sub>3</sub>`` → ``Bi2Te3``
    """
    if not raw:
        return ""
    text = raw
    # 1. HTML 下标
    text = _HTML_SUB_RE.sub("", text)
    # 2. LaTeX \mathrm / \operatorname 及下标花括号
    text = _LATEX_RE.sub(lambda m: m.group(1) or m.group(2) or m.group(3), text)
    text = text.replace("\\_", "_").replace("_{", "").replace("}", "").replace("{", "")
    text = _SUBSCRIPT_RE.sub("", text)
    # 3. 去空白与 LaTeX 残留
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _extract_temperatures(text: str) -> list[str]:
    """提取温度列表（K / °C）。"""
    return [m.group(1) for m in _TEMP_RE.finditer(text)]


def _extract_properties(text: str) -> list[PropertyEntry]:
    """提取性能：zT、带隙等（带单位优先）。"""
    props: list[PropertyEntry] = []
    for m in _ZT_RE.finditer(text):
        props.append(PropertyEntry(name="figure_of_merit_zT", value=float(m.group(1))))
    for m in _GAP_RE.finditer(text):
        props.append(
            PropertyEntry(
                name="band_gap",
                value=float(m.group(1)),
                unit=m.group(2) or "eV",
            )
        )
    return props


# 合法元素符号集合（118 个），用于过滤单位/名词误提取（如 Wm^-1K^-1）
_ELEMENT_SYMBOLS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
    "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds",
    "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
}

# 化学式段：元素符号 + 可选系数（如 Ge0.93 / PbTe）
_FORMULA_SEG_RE = re.compile(r"[A-Z][a-z]?\d*(?:\.\d+)?")
# LaTeX 化学式序列（\mathrm{...}_{...}）
_LATEX_SEQ_RE = re.compile(
    r"(?:\\mathrm\{[A-Za-z][a-z]?\}\s*(?:_\{\s*[\d.]+\s*\})?\s*)+"
)
# HTML 下标序列（Bi<sub>2</sub>Te<sub>3</sub>）
_HTML_SEQ_RE = re.compile(r"(?:[A-Z][a-z]?<sub>\d+</sub>)+")
# 简单元素-数字组合（如 GeTe / Bi2Te3 / Sr5In2Sb6）
_SIMPLE_RE = re.compile(r"\b(?:[A-Z][a-z]?\d*(?:\.\d+)?){2,}\b")
# 掺杂/类型描述（composition 候选）：如 "Ti and Bi doped"、"Zn-doped"、
# "Pb or Ca doping"、"p-type"。对齐 gold 字段分布（composition 5/5 有值），
# 补齐规则抽取器从不填 composition 的结构性缺陷（per_field recall=0）。
_DOPING_PHRASE_RE = re.compile(
    r"(?:[A-Z][a-z]?\s*(?:and\s+|[a-z]+\s*,\s*|[a-z]+\s+or\s+)?)+"
    r"[- ]?dop(?:ed|ing)\b"
    r"|(?:p|n)-type\b"
)


def _is_valid_formula(norm: str) -> bool:
    """校验归一化化学式：每段均为合法元素符号（至少 2 段）。

    过滤单位误提取（如 ``Wm`` 来自 ``\\mathrm{Wm}^{-1}\\mathrm{K}^{-1}``）。
    """
    segments = _FORMULA_SEG_RE.findall(norm)
    if len(segments) < 2 or "".join(segments) != norm:
        return False
    return all(
        re.sub(r"\d+\.?\d*", "", seg) in _ELEMENT_SYMBOLS for seg in segments
    )


def _first_formula(text: str) -> str | None:
    """提取文本中第一个候选化学式（归一化后，需通过元素符号校验）。

    遍历全部候选（LaTeX → HTML → 简单组合），跳过单位等非法候选，
    返回第一个合法化学式；均非法返回 None。
    """
    for m in _LATEX_SEQ_RE.finditer(text):
        norm = normalize_formula(m.group(0))
        if len(norm) >= 2 and _is_valid_formula(norm):
            return norm
    for m in _HTML_SEQ_RE.finditer(text):
        norm = normalize_formula(m.group(0))
        if _is_valid_formula(norm):
            return norm
    for m in _SIMPLE_RE.finditer(text):
        norm = normalize_formula(m.group(0))
        if _is_valid_formula(norm):
            return norm
    return None


def _extract_composition(text: str) -> str | None:
    """提取组成/掺杂描述（composition 字段降级路径）。

    gold 复算揭示规则抽取器 composition recall=0（结构上从不填该字段），
    此函数补齐：捕获掺杂/类型修饰短语（"Ti and Bi doped"、"Zn-doped"、
    "Pb or Ca doping"、"p-type"）。取首个命中并清洗多余空白；
    未命中返回 None（保持空-空跳过语义，不引入误报）。
    """
    for m in _DOPING_PHRASE_RE.finditer(text):
        phrase = re.sub(r"\s+", " ", m.group(0)).strip()
        if phrase:
            return phrase
    return None


def rule_based_extract(text: str, *, doc_id: str | None = None) -> ExtractionRecord | None:
    """规则式抽取：从文献片段提取材料知识四元组（降级路径）。

    返回 None 表示未提取到任何材料信息（该片段不落库）。
    """
    formula = _first_formula(text)
    if not formula:
        return None
    temps = _extract_temperatures(text)
    props = _extract_properties(text)
    synthesis = SynthesisInfo(temperature=", ".join(temps) if temps else None)
    return ExtractionRecord(
        material=Material(
            formula=formula,
            composition=_extract_composition(text),
        ),
        properties=props,
        synthesis=synthesis,
        source=SourceRef(doc_id=doc_id),
        confidence=0.4,  # 规则式置信度固定低于 LLM
    )


def dedupe_key(record: ExtractionRecord) -> str:
    """归一化去重键：优先 formula（归一化），兜底 composition。"""
    return normalize_formula(record.material.formula) or normalize_formula(
        record.material.composition or ""
    )


def merge_records(records: list[ExtractionRecord]) -> list[ExtractionRecord]:
    """同体系（同 formula）记录合并：属性与方法取并集、来源合并。

    用于多篇文献对同一材料体系的抽取结果归一化。
    """
    merged: dict[str, ExtractionRecord] = {}
    order: list[str] = []
    for rec in records:
        key = dedupe_key(rec)
        if key not in merged:
            merged[key] = rec
            order.append(key)
            continue
        target = merged[key]
        # 属性按 (name, value) 去重合并
        existing = {(p.name, p.value) for p in target.properties}
        for p in rec.properties:
            if (p.name, p.value) not in existing:
                target.properties.append(p)
                existing.add((p.name, p.value))
        # 方法按 (type, software) 去重合并
        existing_m = {(m.type, m.software) for m in target.methods}
        for m in rec.methods:
            if (m.type, m.software) not in existing_m:
                target.methods.append(m)
                existing_m.add((m.type, m.software))
        # 合成条件：缺失字段补齐
        syn = target.synthesis
        if not syn.temperature and rec.synthesis.temperature:
            syn.temperature = rec.synthesis.temperature
        if not syn.precursors and rec.synthesis.precursors:
            syn.precursors = rec.synthesis.precursors
        # 置信度取更高者
        if (rec.confidence or 0) > (target.confidence or 0):
            target.confidence = rec.confidence
    return [merged[k] for k in order]

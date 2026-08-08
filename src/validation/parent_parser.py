"""A/B 位拆分纯母体解析器（模块 6 验证失败项优化）。

背景：搜索 Agent 的候选 host 常为「分数掺杂成分」（如 Ge0.93Ti0.01Bi0.06Te）
或「合金成分」（如 Bi0.5Sb1.5Te3），OQMD 直查易超时 → 验证失败。
本解析器从这类成分中提取「整数母体」（A/B 位拆分：主阳离子 + 阴离子），
供数据库按整数成分重验，提高判定覆盖率（对齐
`.trae/rules/03-materials-databases.md` 7.2 交叉验证流程）。

支持的热电计量型：
- AX 型：Ge0.93Ti0.01Bi0.06Te → GeTe（阳离子总数 ≈ 阴离子下标 1）
- A2X3 型：Bi0.5Sb1.5Te3 → Sb2Te3（阳离子总数 2、阴离子下标 3）

主阳离子 = 下标占比最大的阳离子，其余元素视为掺杂（A/B 位拆分）；
解析失败返回 None，调用方如实标注「验证失败」，不伪装结论。
"""
from __future__ import annotations

import re

# 热电体系常见阴离子（末尾匹配，避免把 Bi/Sb 等阳离子误判为阴离子）
_ANIONS = {"Te", "Se", "S", "As", "P", "Br", "Cl", "I", "F", "O", "N"}

# 元素 + 可选下标（整数或小数，如 0.93 / 3）
_TOKEN_RE = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")

# 变量式占位下标（如 Ge1-xBixTe / Ge1-x-yTixBiyTe）：主体阳离子后跟 1-x / 1-x-y
_VAR_MAIN_RE = re.compile(r"([A-Z][a-z]?)\s*[0-9.]*1\s*-\s*[xy](?:\s*-\s*[xy])?")

# 计量型判定的容差（浮点下标误差）
_EPS = 0.02


def _tokenize(formula: str) -> list[tuple[str, float]]:
    """提取 (元素, 下标) 列表；缺失下标视为 1。"""
    tokens: list[tuple[str, float]] = []
    for m in _TOKEN_RE.finditer(formula):
        elem = m.group(1)
        raw = m.group(2)
        sub = float(raw) if raw and raw != "." else 1.0
        tokens.append((elem, sub))
    return tokens


def parse_integer_parent(formula: str) -> str | None:
    """从分数掺杂/合金成分解析整数母体。

    参数:
        formula: 成分（如 Ge0.93Ti0.01Bi0.06Te / Bi0.5Sb1.5Te3）

    返回:
        整数母体化学式（如 GeTe / Sb2Te3）；无法解析返回 None。
    """
    if not formula or not formula.strip():
        return None
    # 多掺杂可能用 + 连接（如 Pb0.97Na+Sr0.03Te）：按主阳离子占比原则整体解析
    tokens = _tokenize(formula.replace("+", ""))
    if not tokens:
        return None
    # 末尾阴离子定位（只允许一个阴离子，多于一个保守返回 None）
    anion = tokens[-1][0]
    if anion not in _ANIONS:
        return None
    anion_sub = tokens[-1][1]
    cations = tokens[:-1]
    if not cations:
        return None
    # 主阳离子 = 下标占比最大者（其余为 A/B 位掺杂）
    main, main_sub = max(cations, key=lambda t: t[1])
    total_cation = sum(t[1] for t in cations)
    # AX 型：阳离子总数 ≈ 阴离子下标（1:1，下标 1 省略）
    if anion_sub == 1 and abs(total_cation - 1.0) < _EPS:
        return f"{main}{anion}"
    # A2X3 型：阳离子总数 2、阴离子下标 3（Bi2Te3 / Sb2Te3 类）
    if anion_sub == 3 and abs(total_cation - 2.0) < _EPS:
        return f"{main}2{anion}3"
    # 其余计量型暂不支持（保守，避免生成错误母体）
    return None


def parse_variable_parent(formula: str) -> str | None:
    """从变量式成分解析名义母体（如 Ge1-x-yTixBiyTe → GeTe）。

    背景：Gap 识别 LLM 常用「占位下标」表达掺杂体系（Ge1-xBixTe、
    Ge1-x-yTixBiyTe），此类公式无法被 `parse_integer_parent` 解析，导致
    证据回填时匹配不到知识库母体。本函数提取「主体阳离子（1-x 占位下标前的
    元素）+ 末尾阴离子」作为名义母体，供证据回填/验证按母体匹配。

    参数:
        formula: 变量式成分（含 x/y 占位下标）

    返回:
        名义母体化学式（如 GeTe）；非变量式或无法解析返回 None。
    """
    if not formula or ("x" not in formula and "y" not in formula):
        return None
    m = _VAR_MAIN_RE.search(formula)
    if not m:
        return None
    cation = m.group(1)
    tokens = _tokenize(formula)
    if not tokens or tokens[-1][0] not in _ANIONS:
        return None
    return f"{cation}{tokens[-1][0]}"

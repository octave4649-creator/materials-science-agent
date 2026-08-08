"""MP 相图级稳定性核对（含双 thermo 交叉复核）。

2026-08-08 十五次深度开发新增：MP 默认 thermo_type 为
GGA_GGA+U_R2SCAN 联合 hull，其竞争相集合含 r2SCAN 数据点，对部分热电
母体（Mg3Sb2/Sb2Te3/ZrNiSn）会算出异常巨大的 hull（9.7/21.6/13.4 eV），
而老 GGA_GGA+U thermo 下 hull=0.0 稳定——属 MP 数据层缺陷非材料真实性质
（exp 126）。故默认 thermo hull>0.5 时用 GGA_GGA+U 复核，输出两套结果
供归因，避免误判真实热电母体。

对外依赖（mp-api/pymatgen）缺失或 MP 查询失败时优雅降级返回带 note 的
结论，不抛异常（对齐 00-project-rules.md 3.3 错误处理）。
"""

from __future__ import annotations

import re
from typing import Any

from src.common.config import mp_api_key

_ELE_RE = re.compile(r"[A-Z][a-z]?")
_THERMO_LEGACY = {"thermo_types": ["GGA_GGA+U"]}
_THERMO_LEGACY_TAG = "GGA_GGA+U(老)"
_THERMO_DEFAULT_TAG = "GGA_GGA+U_R2SCAN(默认)"
_HULL_ABNORMAL_THRESHOLD = 0.5  # 默认 thermo hull 超过此值视为 MP 数据层缺陷嫌疑

# 延迟导入（模块顶层）：缺失时优雅降级；测试可 monkeypatch 这两个模块属性
try:
    from mp_api.client import MPRester  # noqa: E402
    from pymatgen.analysis.phase_diagram import PhaseDiagram  # noqa: E402
except ImportError:  # pragma: no cover - 无 MP 依赖的环境（CI）
    MPRester = None  # type: ignore[assignment]
    PhaseDiagram = None  # type: ignore[assignment]


def chemsys_for_formula(formula: str) -> str:
    """化学式 → MP chemsys 字符串（元素去重、按字母序、连字符分隔）。

    MP 的 get_entries_in_chemsys 要求元素按字母序排列，如 Cu2Se → "Cu-Se"、
    SiGe → "Ge-Si"（G < S）。解析失败返回空串由调用方兜底。
    """
    els = sorted({m.group() for m in _ELE_RE.finditer(formula)})
    return "-".join(els)


def check_phase_stability(formula: str, chemsys: str | None = None) -> dict[str, Any]:
    """对单个化学体系做 MP 相图级核对（含双 thermo 交叉复核）。

    参数:
        formula: 目标化学式（如 Mg3Sb2）
        chemsys: MP chemsys（元素字母序连字符）；None 时由 formula 推导

    返回:
        {"formula", "chemsys", "hull", "decomposition", "stable_in_mp",
         "note", ...}；MP 不可用/无该 formula 时返回带 note 的结论。
        双 thermo 分歧时额外含 legacy_hull/legacy_decomposition/
        thermo_discrepancy=True。
    """
    chemsys = chemsys or chemsys_for_formula(formula)
    if MPRester is None or PhaseDiagram is None:
        return {
            "formula": formula,
            "chemsys": chemsys,
            "note": "mp-api/pymatgen 未安装（模块导入失败），无法相图级核对",
        }

    def _single(mpr: Any, tag: str, criteria: dict) -> dict | None:
        """按指定 thermo 类型计算相图级稳定性，返回结果或 None（无该 formula）。"""
        try:
            entries = mpr.get_entries_in_chemsys(chemsys, additional_criteria=criteria)
        except Exception as exc:  # noqa: BLE001 - 单 thermo 失败降级，不中断
            return {"tag": tag, "note": f"MP 查询失败: {exc}"}
        if not entries:
            return {"tag": tag, "note": f"MP 无 {chemsys} 体系 entries"}
        pd = PhaseDiagram(entries)
        target = [e for e in entries if e.composition.reduced_formula == formula]
        if not target:
            return {
                "tag": tag,
                "note": f"MP 相图 {chemsys} 中无 {formula}（仅含 {len(entries)} 条 entries）",
            }
        entry = min(target, key=lambda e: e.energy_per_atom)
        decomp, hull = pd.get_decomp_and_e_above_hull(entry)
        stable = bool(hull < 0.1)  # pymatgen 返回 np 标量，显式转 Python bool 保证 JSON 可序列化
        decomp_txt = " + ".join(
            f"{d.reduced_formula} ({v:.3f} mol)" for d, v in decomp.items()
        )
        return {
            "tag": tag,
            "hull": round(float(hull), 4),
            "decomposition": decomp_txt,
            "stable_in_mp": stable,
            "n_entries": len(entries),
            "note": (
                f"相图级核对：{formula} 在 MP 相图中"
                + ("稳定（hull<0.1）" if stable else "不稳定")
                + f"，分解产物 {decomp_txt}"
            ),
        }

    with MPRester(mp_api_key()) as mpr:
        default = _single(mpr, _THERMO_DEFAULT_TAG, {})
        # 默认 thermo hull 异常大（>阈值）→ MP 数据层缺陷嫌疑，用老 thermo 交叉复核
        abnormal = default and default.get("hull") is not None
        if abnormal and default["hull"] > _HULL_ABNORMAL_THRESHOLD:  # noqa: SIM102
            legacy = _single(mpr, _THERMO_LEGACY_TAG, _THERMO_LEGACY)
        else:
            legacy = None

    if default is None:
        return {"formula": formula, "chemsys": chemsys, "note": "MP 核对无结果"}
    if default.get("hull") is None:
        return {"formula": formula, "chemsys": chemsys, **default}

    # 汇总结论：只要触发过 legacy 交叉复核（默认 thermo hull 异常）即留痕
    # thermo_discrepancy=True（exp 126 审计：复核事件本身就有信息量，即使判定一致）；
    # 判定不同时以物理合理（GGA_GGA+U 老 thermo）为准
    if legacy and legacy.get("hull") is not None:
        discrepancy = legacy["stable_in_mp"] != default["stable_in_mp"]
        stable_final = legacy["stable_in_mp"] if discrepancy else default["stable_in_mp"]
        if discrepancy:
            note = (
                f"{default['note']}；而 {_THERMO_LEGACY_TAG} thermo 下 hull="
                f"{legacy['hull']}（{'稳定' if legacy['stable_in_mp'] else '不稳定'}）。"
                "分歧归因：MP 默认 GGA_GGA+U_R2SCAN 联合 hull 的竞争相集合含 r2SCAN"
                "数据点，对部分热电母体产生异常巨大 hull，属 MP 数据层缺陷非材料真实"
                "性质（exp 126）；双 thermo 交叉复核下以 GGA_GGA+U 判定为准。"
                "该「数据库内 thermo 分歧」如实留痕，不作为 OQMD 稳定性判定的反例。"
            )
        else:
            note = (
                f"{default['note']}；{_THERMO_LEGACY_TAG} thermo 交叉复核结论一致"
                f"（hull={legacy['hull']}），默认 thermo 异常 hull 不影响判定"
                "（exp 126 双 thermo 交叉复核留痕）。"
            )
        return {
            "formula": formula,
            "chemsys": chemsys,
            "hull": default["hull"],
            "legacy_hull": legacy["hull"],
            "legacy_decomposition": legacy["decomposition"],
            "decomposition": default["decomposition"],
            "stable_in_mp": stable_final,
            "thermo_discrepancy": True,
            "n_entries": default["n_entries"],
            "note": note,
        }

    return {"formula": formula, "chemsys": chemsys, **default}

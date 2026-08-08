"""src/validation/mp_phase 双 thermo 相图级核验单测。

2026-08-08 十五次深度开发新增：MP 默认 thermo（GGA_GGA+U_R2SCAN 联合）
对部分热电母体（Mg3Sb2/Sb2Te3/ZrNiSn）算出异常巨大 hull，需 GGA_GGA+U
老 thermo 交叉复核。测试全 mock MPRester/PhaseDiagram，不依赖网络。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.validation.mp_phase as mp_phase  # noqa: E402
from src.validation.mp_phase import (  # noqa: E402
    _THERMO_LEGACY,
    _THERMO_LEGACY_TAG,
    check_phase_stability,
    chemsys_for_formula,
)


def _fake_entry(reduced_formula: str):
    """伪 Composition.energy_per_atom/reduced_formula 条目。"""
    return SimpleNamespace(
        composition=SimpleNamespace(reduced_formula=reduced_formula),
        energy_per_atom=0.0,
    )


def _make_fake_mp(calls: list[dict], entries: list) -> type:
    """构造记录 additional_criteria 调用并返回固定 entries 的伪 MPRester。"""

    class _FakeMP:
        def __init__(self, api_key):  # noqa: ANN001
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

        def get_entries_in_chemsys(self, chemsys, additional_criteria=None):  # noqa: ANN001, ANN202
            calls.append(dict(additional_criteria or {}))
            return entries

    return _FakeMP


def _make_switch_pd(hull_fn: Callable[[], float]) -> type:
    """构造按 hull_fn 返回 hull 的伪 PhaseDiagram（支持两次调用不同值）。"""

    class _SwitchPD:
        def __init__(self, entries):  # noqa: ANN001
            pass

        def get_decomp_and_e_above_hull(self, entry):  # noqa: ANN001, ANN202
            return {}, hull_fn()

    return _SwitchPD


def _install(monkeypatch: pytest.MonkeyPatch, mp: type, pd: type) -> None:
    """注入伪 MPRester / PhaseDiagram 到 mp_phase 模块。"""
    monkeypatch.setattr(mp_phase, "MPRester", mp)
    monkeypatch.setattr(mp_phase, "PhaseDiagram", pd)


def test_chemsys_for_formula_alphabetical() -> None:
    """chemsys 元素去重 + 字母序连字符。"""
    assert chemsys_for_formula("Cu2Se") == "Cu-Se"
    assert chemsys_for_formula("SiGe") == "Ge-Si"
    assert chemsys_for_formula("Mg3Sb2") == "Mg-Sb"
    assert chemsys_for_formula("ZrNiSn") == "Ni-Sn-Zr"


def test_chemsys_for_formula_dedup() -> None:
    """元素出现多次去重。"""
    assert chemsys_for_formula("Bi2Te3") == "Bi-Te"
    assert chemsys_for_formula("CoSb3") == "Co-Sb"


def test_stable_no_legacy_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认 thermo 稳定（hull<0.5）→ 不触发 legacy 复核，无 thermo_discrepancy。"""
    calls: list[dict] = []
    _install(
        monkeypatch,
        _make_fake_mp(calls, [_fake_entry("GeTe")]),
        _make_switch_pd(lambda: 0.0),
    )
    result = check_phase_stability("GeTe", "Ge-Te")
    assert result["stable_in_mp"] is True
    assert result["hull"] == 0.0
    assert "thermo_discrepancy" not in result
    assert result.get("legacy_hull") is None
    assert len(calls) == 1  # 未触发 legacy 复核


def test_abnormal_hull_triggers_legacy_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认 thermo hull 异常大（>0.5）→ legacy 复核 → 以 legacy 稳定为准。"""
    calls: list[dict] = []
    _install(
        monkeypatch,
        _make_fake_mp(calls, [_fake_entry("Mg3Sb2")]),
        _make_switch_pd(lambda: 9.7261 if len(calls) == 1 else 0.0),
    )
    result = check_phase_stability("Mg3Sb2", "Mg-Sb")
    # legacy 复核被触发（第二次调用带 thermo_types 过滤）
    assert len(calls) == 2
    assert calls[1] == _THERMO_LEGACY
    # 最终以 legacy 稳定为准
    assert result["stable_in_mp"] is True
    assert result["thermo_discrepancy"] is True
    assert result["legacy_hull"] == 0.0
    assert result["hull"] == 9.7261
    assert "exp 126" in result["note"]
    assert _THERMO_LEGACY_TAG in result["note"]


def test_abnormal_hull_legacy_also_unstable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认与 legacy 均不稳定 → 判定不稳定，复核事件仍留痕。"""
    calls: list[dict] = []
    _install(
        monkeypatch,
        _make_fake_mp(calls, [_fake_entry("X2Y")]),
        _make_switch_pd(lambda: 0.75),  # 两 thermo 均 0.75 不稳定
    )
    result = check_phase_stability("X2Y", "X-Y")
    assert len(calls) == 2
    assert result["stable_in_mp"] is False
    # 触发 legacy 复核（默认 hull 异常）即留痕，即使判定一致
    assert result["thermo_discrepancy"] is True
    assert result["hull"] == 0.75
    assert result["legacy_hull"] == 0.75
    assert "交叉复核结论一致" in result["note"]


def test_abnormal_hull_legacy_stable_but_default_unstable_uses_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认不稳定但 legacy 稳定 → 以 legacy 为准（Mg3Sb2 场景）。"""
    calls: list[dict] = []
    _install(
        monkeypatch,
        _make_fake_mp(calls, [_fake_entry("Mg3Sb2")]),
        _make_switch_pd(lambda: 9.7261 if len(calls) == 1 else 0.0),
    )
    result = check_phase_stability("Mg3Sb2", "Mg-Sb")
    assert result["stable_in_mp"] is True
    assert result["legacy_hull"] == 0.0
    assert result["thermo_discrepancy"] is True


def test_missing_entries_no_formula(monkeypatch: pytest.MonkeyPatch) -> None:
    """MP 无该 formula → 返回带 note 的结论而非异常。"""
    calls: list[dict] = []
    _install(
        monkeypatch,
        _make_fake_mp(calls, [_fake_entry("Other")]),
        _make_switch_pd(lambda: 0.0),
    )
    result = check_phase_stability("Missing", "Mi-Ss")
    assert "无 Missing" in result.get("note", "")
    assert result.get("hull") is None


def test_mp_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """MP 依赖缺失 → 优雅降级返回 note，不抛异常。"""
    monkeypatch.setattr(mp_phase, "MPRester", None)
    monkeypatch.setattr(mp_phase, "PhaseDiagram", None)
    result = check_phase_stability("GeTe", "Ge-Te")
    assert "未安装" in result["note"]
    assert result.get("hull") is None

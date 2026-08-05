"""Materials Project 客户端（模块 6 增强路径）。

对齐 `.trae/rules/03-materials-databases.md` 第 2 节：
- Key 存环境变量 `MP_API_KEY`，禁止入库
- 依赖 mp-api / pymatgen（pyproject `validation` extra），缺失时优雅降级
- MP 未配置/不可用时返回 None，调用方仅记录「MP 未启用」而非报错
"""
from __future__ import annotations

from typing import Any

from src.common.config import mp_api_key

# 稳定性阈值（energy above hull，eV/atom）
HULL_THRESHOLD = 0.1


def mp_available() -> bool:
    """MP 是否可用（有 Key 且 mp-api 可导入）。"""
    if not mp_api_key():
        return False
    try:
        import mp_api  # noqa: F401

        return True
    except ImportError:
        return False


def query_summary(formula: str) -> list[dict[str, Any]] | None:
    """按成分查询 MP 摘要（material_id / band_gap / 稳定性）。

    参数:
        formula: 成分（如 PbTe）

    返回:
        命中记录列表；MP 不可用返回 None（区别于「命中 0 条」）。
    """
    if not mp_available():
        return None
    try:
        from mp_api.client import MPRester

        with MPRester(mp_api_key()) as mpr:
            docs = mpr.materials.summary.search(
                formula=formula,
                fields=[
                    "material_id",
                    "formula_pretty",
                    "band_gap",
                    "is_metal",
                    "is_stable",
                    "formation_energy_per_atom",
                    "energy_above_hull",
                ],
            )
    except Exception:
        return None
    out: list[dict[str, Any]] = []
    for d in docs or []:
        out.append(
            {
                "material_id": d.material_id,
                "formula": d.formula_pretty,
                "band_gap": d.band_gap,
                "is_metal": d.is_metal,
                "is_stable": d.is_stable,
                "formation_energy_per_atom": d.formation_energy_per_atom,
                "energy_above_hull": d.energy_above_hull,
            }
        )
    return out

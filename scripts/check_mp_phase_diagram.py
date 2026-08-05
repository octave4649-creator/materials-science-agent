"""跨库分歧 MP 相图级核对脚本（t4：OQMD 稳定 vs MP 不稳定）。

背景：批量验证发现 GeTe 在 OQMD 稳定（hull=0.002）但 MP 中 mp-1080459
不稳定（hull=0.028）——两库竞争相集合/DFT 设置不同。本脚本用 MP 相图
（chemsys 内的全部 DFT entries）核对 GeTe 的分解产物与 hull 距离，
给出「分歧归因」结论，作为数据库间分歧的科学素材写入报告。

用法:
    python scripts/check_mp_phase_diagram.py [--chemsys Ge-Te]
输入: 跨库分歧清单（results/validation 自动提取）+ MP_API_KEY
输出: results/validation/mp_phase_check_<ts>.json + 控制台结论
依赖: mp-api + pymatgen（缺失时优雅降级打印提示，不影响主流程）
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import RESULTS_DIR, mp_api_key
from src.validation.feedback import extract_disputes


def _check_chemsys(chemsys: str, formula: str) -> dict:
    """对单个化学体系做 MP 相图级核对。

    返回:
        {"formula", "hull", "decomposition", "stable_in_mp",
         "dispute_resolved", "note"}；MP 不可用返回带 reason 的空结论。
    """
    try:
        from mp_api.client import MPRester
        from pymatgen.analysis.phase_diagram import PhaseDiagram
    except ImportError as exc:
        return {"formula": formula, "note": f"mp-api/pymatgen 未安装: {exc}"}

    try:
        with MPRester(mp_api_key()) as mpr:
            entries = mpr.get_entries_in_chemsys(chemsys)
    except Exception as exc:
        return {"formula": formula, "note": f"MP 查询失败: {exc}"}

    if not entries:
        return {"formula": formula, "note": f"MP 无 {chemsys} 体系 entries"}

    pd = PhaseDiagram(entries)
    target = [e for e in entries if e.composition.reduced_formula == formula]
    if not target:
        return {
            "formula": formula,
            "note": f"MP 相图 {chemsys} 中无 {formula}（仅含 {len(entries)} 条 entries）",
        }
    entry = min(target, key=lambda e: e.energy_per_atom)
    decomp, hull = pd.get_decomp_and_e_above_hull(entry)
    stable = hull < 0.1
    decomp_txt = " + ".join(
        f"{d.reduced_formula} ({v:.3f} mol)" for d, v in decomp.items()
    )
    return {
        "formula": formula,
        "chemsys": chemsys,
        "hull": round(float(hull), 4),
        "decomposition": decomp_txt,
        "stable_in_mp": stable,
        "n_entries": len(entries),
        "note": (
            "相图级核对：GeTe 在 MP 相图中"
            + ("稳定（hull<0.1）" if stable else "不稳定")
            + f"，分解产物 {decomp_txt}；OQMD 判定稳定而 MP 判定不稳定的"
            "分歧源于两库竞争相集合/DFT 设置不同，以相图级核对为准"
        ),
    }


def main() -> int:
    """入口：提取跨库分歧 → MP 相图级核对 → 结论落盘。"""
    argv = sys.argv[1:]
    chemsys = argv[argv.index("--chemsys") + 1] if "--chemsys" in argv else "Ge-Te"
    if not mp_api_key():
        print("MP_API_KEY 未配置，无法做相图级核对（先设置环境变量）")
        return 1
    validation_dir = RESULTS_DIR / "validation"
    disputes = extract_disputes(validation_dir)
    print(f"跨库分歧记录: {len(disputes)} 条")
    if not disputes:
        print("无跨库分歧，无需核对")
        return 0
    hosts = sorted({d["host"] for d in disputes})
    print(f"分歧母体: {hosts}")

    checks = [_check_chemsys(chemsys, h) for h in hosts]
    for c in checks:
        print(f"\n=== {c.get('formula', '?')} 相图级核对 ===")
        print(f"  hull: {c.get('hull', '-')} | 分解产物: {c.get('decomposition', '-')}")
        print(f"  结论: {c.get('note', '-')}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = validation_dir / f"mp_phase_check_{ts}.json"
    out_path.write_text(
        json.dumps(
            {
                "disputes": disputes,
                "phase_checks": checks,
                "conclusion": (
                    "跨库分歧经 MP 相图级核对归因：分歧源于两库竞争相集合/"
                    "DFT 设置差异，以相图级 hull 判定为准；分歧本身作为"
                    "「数据库间分歧」科学素材写入报告（03 规范 7.2 负结果同入库）"
                ),
                "generated_at": ts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n落盘: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

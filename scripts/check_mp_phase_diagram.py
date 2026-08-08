"""跨库分歧 / 共识候选反例 MP 相图级核对脚本（t4：OQMD 稳定 vs MP 不稳定）。

背景：批量验证发现 GeTe 在 OQMD 稳定（hull=0.002）但 MP 中 mp-1080459
不稳定（hull=0.028）——两库竞争相集合/DFT 设置不同。本脚本用 MP 相图
（chemsys 内的全部 DFT entries）核对目标的分解产物与 hull 距离，
给出「分歧归因」结论，作为数据库间分歧的科学素材写入报告。

核心逻辑（双 thermo 交叉复核）在 `src/validation/mp_phase.py`，本脚本仅做
CLI 封装 + 结果落盘。

两种用法：
1. 跨库分歧路径（默认）：extract_disputes 提取 OQMD 稳定 vs MP 不稳定的
   分歧母体 → 逐母体推导 chemsys → 相图级核对
2. 显式公式路径（--formulas "Cu2Se,SiGe"）：核对指定公式（如共识候选
   反例母体）在 MP 相图中的相图级稳定性，归因「条目级亚稳 vs 相图级」
   与「DFT 亚稳 vs 实验应用」分歧

用法:
    python scripts/check_mp_phase_diagram.py [--chemsys Ge-Te]
    python scripts/check_mp_phase_diagram.py --formulas "Cu2Se,SiGe"
输入: 跨库分歧清单（results/validation 自动提取）或 --formulas + MP_API_KEY
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
from src.validation.mp_phase import check_phase_stability, chemsys_for_formula


def main() -> int:
    """入口：跨库分歧或 --formulas → MP 相图级核对 → 结论落盘。"""
    argv = sys.argv[1:]
    if not mp_api_key():
        print("MP_API_KEY 未配置，无法做相图级核对（先设置环境变量）")
        return 1
    validation_dir = RESULTS_DIR / "validation"

    formulas_arg = None
    if "--formulas" in argv:
        formulas_arg = argv[argv.index("--formulas") + 1]

    if formulas_arg:
        # 显式公式路径：核对指定公式（共识候选反例母体等）
        formulas = [f.strip() for f in formulas_arg.split(",") if f.strip()]
        if not formulas:
            print("--formulas 为空，无法核对")
            return 1
        checks = []
        for f in formulas:
            chemsys = chemsys_for_formula(f)
            print(f"推导 chemsys：{f} → {chemsys}")
            checks.append(check_phase_stability(f, chemsys))
        source = {"mode": "formulas", "formulas": formulas}
    else:
        chemsys = argv[argv.index("--chemsys") + 1] if "--chemsys" in argv else "Ge-Te"
        validation_dir = RESULTS_DIR / "validation"
        disputes = extract_disputes(validation_dir)
        print(f"跨库分歧记录: {len(disputes)} 条")
        if not disputes:
            print("无跨库分歧，无需核对")
            return 0
        hosts = sorted({d["host"] for d in disputes})
        print(f"分歧母体: {hosts}")
        checks = []
        for h in hosts:
            h_chemsys = chemsys_for_formula(h) or chemsys
            checks.append(check_phase_stability(h, h_chemsys))
        source = {"mode": "disputes", "chemsys": chemsys, "hosts": hosts}

    for c in checks:
        print(f"\n=== {c.get('formula', '?')} 相图级核对 ===")
        if c.get("legacy_hull") is not None:
            print(
                f"  hull(默认 R2SCAN): {c.get('hull', '-')} | "
                f"legacy_hull(GGA_GGA+U): {c['legacy_hull']}"
            )
        else:
            print(f"  hull: {c.get('hull', '-')} | 分解产物: {c.get('decomposition', '-')}")
        print(f"  结论: {c.get('note', '-')}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = validation_dir / f"mp_phase_check_{ts}.json"
    out_path.write_text(
        json.dumps(
            {
                "source": source,
                "phase_checks": checks,
                "conclusion": (
                    "MP 相图级核对归因：分歧源于两库竞争相集合/DFT 设置差异，"
                    "以相图级 hull 判定为准；DFT 相图级亚稳不等于实验不可用"
                    "（如 Cu2Se/SiGe 为热电常用材料），构效关系判定需结合"
                    "DFT 与实验双重证据；分歧本身作为「数据库间分歧」科学素材"
                    "写入报告（03 规范 7.2 负结果同入库）"
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

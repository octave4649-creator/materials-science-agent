"""NOMAD/AFLOW 可选数据库交叉验证 CLI（模块 6 阶段 1 未勾选项落地）。

用法:
    python scripts/run_extra_db_check.py [--formulas "GeTe,ZrNiSn"]
        [--oracle results/oracle/oracle_truth_20260808T132948.json] [--out results/validation]
输出: results/validation/extra_db_check_<ts>.json / .md
      （NOMAD 结构存在性计数 + AFLOW 晶体对称性/形成焓，补强路线 A 双库核验论证）

默认从最新 oracle_truth 母体池聚合 12 共识母体；--formulas 显式指定则优先。
两库均免 Key；网络不可用时按条留痕「未连通」，不中断整体。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import RESULTS_DIR  # noqa: E402
from src.validation.aflow_client import AFLOWClient, AFLOWError  # noqa: E402
from src.validation.nomad_client import NOMADClient, NOMADError  # noqa: E402

VALIDATION_DIR = RESULTS_DIR / "validation"
ORACLE_DIR = RESULTS_DIR / "oracle"


def _pick_oracle() -> Path:
    """取最新 oracle_truth json（无则报错）。"""
    candidates = sorted(
        ORACLE_DIR.glob("oracle_truth_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit(f"未找到 oracle 真值表：{ORACLE_DIR}")
    return candidates[0]


def collect_hosts(oracle_path: Path) -> list[str]:
    """oracle 真值表 → 母体池（去重保序）。"""
    data = json.loads(oracle_path.read_text(encoding="utf-8"))
    hosts: list[str] = []
    seen: set[str] = set()
    for r in data.get("results") or []:
        host = (r.get("host") or "").strip()
        if host and host not in seen:
            seen.add(host)
            hosts.append(host)
    return hosts


def check_one(
    formula: str, nomad: NOMADClient, aflow: AFLOWClient
) -> dict:
    """单母体交叉验证：NOMAD 结构计数 + AFLOW 对称性/形成焓。"""
    # NOMAD：结构存在性计数（用 query_structures 以区分「失败」与「命中 0」）
    nomad_n: int | None = None
    nomad_err: str | None = None
    try:
        nomad_n = len(nomad.query_structures(formula))
    except NOMADError as exc:
        nomad_err = str(exc)

    # AFLOW：晶体对称性 + 形成焓
    aflow_best = None
    aflow_err: str | None = None
    try:
        entries = aflow.query_species(formula)
    except AFLOWError as exc:
        aflow_err = str(exc)
    else:
        if entries:
            best = aflow.best_entry(formula)
            aflow_best = (
                best.model_dump() if best is not None else None
            )

    # 综合存在性判定：
    # - 任一库命中结构 → present（佐证已知，即使另一库不可达）
    # - 两库均可达且 0 命中 → absent（佐证新知，需双库确证）
    # - 均未命中但至少一库不可达 → unreachable（留痕，不误判「新知」）
    present_nomad = nomad_n is not None and nomad_n > 0
    present_aflow = aflow_best is not None
    if present_nomad or present_aflow:
        existence = "present"
    elif nomad_err is None and aflow_err is None:
        existence = "absent"
    else:
        existence = "unreachable"

    return {
        "formula": formula,
        "nomad_n_structures": nomad_n,
        "nomad_error": nomad_err,
        "aflow_best": aflow_best,
        "aflow_error": aflow_err,
        "existence": existence,
        "note": (
            "NOMAD/AFLOW 至少一库命中结构 → 佐证母体已知"
            if existence == "present"
            else "两库均可达且无命中 → 佐证母体新知（跨库分歧素材）"
            if existence == "absent"
            else "NOMAD/AFLOW 均未命中但至少一库不可达，无法判定存在性（留痕）"
        ),
    }


def render_markdown(records: list[dict], stats: dict) -> str:
    """渲染 MD 对照表。"""
    lines = [
        "# NOMAD/AFLOW 可选数据库交叉验证",
        "",
        f"- 生成时间：{stats['generated_at']}",
        f"- 母体数：{stats['n_hosts']}｜存在性分布：{stats['existence_dist']}",
        f"- NOMAD 连通：{'✅' if stats['nomad_ok'] else '❌ 未连通'}｜"
        f"AFLOW 连通：{'✅' if stats['aflow_ok'] else '❌ 未连通'}",
        "",
        "| 母体 | NOMAD 结构数 | AFLOW 空间群/焓(eV/atom) | 存在性 |",
        "|------|------------|--------------------------|--------|",
    ]
    for r in records:
        aflow = r["aflow_best"]
        aflow_txt = "未连通" if r["aflow_error"] else (
            f"{aflow['formula']} 焓={aflow['delta_e']}"
            if aflow and aflow.get("delta_e") is not None
            else (f"{aflow['formula']}" if aflow else "无命中")
        )
        nomad_txt = (
            "未连通" if r["nomad_error"]
            else str(r["nomad_n_structures"]) if r["nomad_n_structures"] is not None
            else "无命中"
        )
        lines.append(
            f"| {r['formula']} | {nomad_txt} | {aflow_txt} | {r['existence']} |"
        )
    lines.append("")
    lines.append(
        "> 存在性口径：present=至少一库命中结构（佐证已知，另一库不可达不抵消）；"
        "absent=两库均可达且 0 命中（佐证新知）；unreachable=均未命中但至少一库不可达（留痕）。"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="NOMAD/AFLOW 可选数据库交叉验证")
    parser.add_argument("--formulas", type=str, default=None,
                        help="显式指定母体列表（逗号分隔，优先于 oracle 聚合）")
    parser.add_argument("--oracle", type=str, default=None,
                        help="oracle 真值表路径（默认最新产物）")
    parser.add_argument("--out", type=str, default=None,
                        help="输出目录（默认 results/validation）")
    parser.add_argument("--no-network", action="store_true",
                        help="跳过在线查询（仅单测/离线验证用）")
    args = parser.parse_args()

    if args.formulas:
        hosts = [f.strip() for f in args.formulas.split(",") if f.strip()]
    else:
        oracle_path = Path(args.oracle) if args.oracle else _pick_oracle()
        hosts = collect_hosts(oracle_path)
    if not hosts:
        raise SystemExit("未解析到任何母体（--formulas 或 --oracle 均空）")

    nomad = NOMADClient()
    aflow = AFLOWClient()
    records = []
    for formula in hosts:
        rec = (
            {"formula": formula, "nomad_n_structures": None, "nomad_error": "离线跳过",
             "aflow_best": None, "aflow_error": "离线跳过", "existence": "unreachable",
             "note": "--no-network 离线模式，未在线查询（留痕）"}
            if args.no_network
            else check_one(formula, nomad, aflow)
        )
        records.append(rec)

    existence_dist: dict[str, int] = {}
    for r in records:
        existence_dist[r["existence"]] = existence_dist.get(r["existence"], 0) + 1
    stats = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"),
        "n_hosts": len(hosts),
        "existence_dist": existence_dist,
        "nomad_ok": any(r["nomad_error"] is None for r in records),
        "aflow_ok": any(r["aflow_error"] is None for r in records),
    }

    out_dir = Path(args.out) if args.out else VALIDATION_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"extra_db_check_{stats['generated_at']}"
    (stem.with_suffix(".json")).write_text(
        json.dumps(
            {"generated_at": stats["generated_at"], "stats": stats, "results": records},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    (stem.with_suffix(".md")).write_text(render_markdown(records, stats), encoding="utf-8")
    print(f"JSON 明细：{stem}.json")
    print(f"MD 对照表：{stem}.md")

    print(f"\n母体 {stats['n_hosts']} 个｜存在性分布：{existence_dist}")
    for r in records:
        print(f"  {r['formula']} → {r['existence']}"
              f"（NOMAD={r['nomad_n_structures']}，AFLOW="
              f"{'未连通' if r['aflow_error'] else '命中' if r['aflow_best'] else '无命中'}）")


if __name__ == "__main__":
    main()

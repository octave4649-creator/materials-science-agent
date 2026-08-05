"""模块 6 验证失败项重验脚本（t3：A/B 位拆分纯母体解析后重验）。

背景：批量验证 182 候选中有 38 个「验证失败」（分数掺杂宿主直查超时，
如 Ge0.93Ti0.01Bi0.06Te / Bi0.5Sb1.5Te3）。本脚本扫描既有验证产物，
仅对「验证失败」候选做纯母体解析（A/B 位拆分提取整数母体）后重验，
避免全量重查；解析失败仍如实标注「验证失败」，不伪装结论。

输出：
- results/validation/validation_<ts>_rerun_*.json：重验结果（对齐验证产物
  结构，VerificationOracle 直接读取，host/formula 判定按优先级自动覆盖）
- results/validation/failed_rerun_summary_<ts>.json：新旧判定分布对比汇总

用法:
    python scripts/rerun_failed_validation.py [--no-mp]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.validation_agent import _validate_candidate  # noqa: E402
from src.common.config import RESULTS_DIR  # noqa: E402
from src.validation.oqmd_client import OQMDClient  # noqa: E402
from src.validation.parent_parser import parse_integer_parent  # noqa: E402


def collect_failed(validation_dir: Path) -> list[tuple[dict, dict]]:
    """收集所有验证文件中的「验证失败」候选（含源 payload 与条目）。"""
    out: list[tuple[dict, dict]] = []
    for f in sorted(validation_dir.glob("validation_*.json")):
        payload = json.loads(f.read_text(encoding="utf-8"))
        for r in payload.get("results") or []:
            if r.get("verdict") == "验证失败":
                out.append((payload, r))
    return out


def main() -> int:
    """入口：解析失败项 → 纯母体重验 → 对齐验证结构落盘 + 分布对比。"""
    argv = sys.argv[1:]
    use_mp = False if "--no-mp" in argv else None
    validation_dir = RESULTS_DIR / "validation"
    if not validation_dir.exists():
        print(f"验证目录不存在: {validation_dir}")
        return 1

    failed = collect_failed(validation_dir)
    print(f"扫描到「验证失败」候选: {len(failed)} 个")
    if not failed:
        print("无需重验")
        return 0

    oqmd = OQMDClient()
    parsed_ok = sum(1 for _, r in failed if parse_integer_parent(r.get("host", "")))
    new_dist: Counter[str] = Counter()
    grouped: dict[str, dict] = {}
    for payload, r in failed:
        cand = {
            "host": r.get("host", ""),
            "dopant": r.get("dopant"),
            "concentration": r.get("concentration"),
            "formula": r.get("candidate_formula", ""),
        }
        result = _validate_candidate(cand, oqmd, use_mp=bool(use_mp))
        new_dist[result.verdict] += 1
        src = payload.get("source_finding", "")
        block = grouped.setdefault(
            src,
            {
                "source_finding": src,
                "gap_statement": payload.get("gap_statement"),
                "evidence_ids": payload.get("evidence_ids") or [],
                "results": [],
                "generated_at": "",
            },
        )
        block["results"].append(result.to_dict())

    print(f"\n解析出整数母体的候选: {parsed_ok} / {len(failed)}")
    print(f"旧判定分布: {{'验证失败': {len(failed)}}}")
    print(f"新判定分布: {dict(new_dist)}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    written: list[Path] = []
    for i, block in enumerate(grouped.values(), start=1):
        block["generated_at"] = ts
        out_path = validation_dir / f"validation_{ts}_rerun_{i}.json"
        out_path.write_text(
            json.dumps(block, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written.append(out_path)
    summary = validation_dir / f"failed_rerun_summary_{ts}.json"
    summary.write_text(
        json.dumps(
            {
                "old_distribution": {"验证失败": len(failed)},
                "new_distribution": dict(new_dist),
                "parsed_ok": parsed_ok,
                "n_candidates": len(failed),
                "generated_at": ts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    for p in written:
        print(f"落盘: {p}")
    print(f"汇总: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

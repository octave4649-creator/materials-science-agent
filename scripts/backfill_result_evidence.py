"""finding/验证产物证据回填 CLI：复用六通道为下游结论补 evidence_ids。

用法:
    python scripts/backfill_result_evidence.py [--target findings|validation|all]
        [--kb data/kb.json] [--results results]
输出: 回填写回 results/{target}/*.json（仅无证据条目）+ 报告
      results/eval/result_evidence_backfill_<ts>.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DATA_DIR, RESULTS_DIR
from src.evaluation.result_evidence_backfill import (
    backfill_results_dir,
    render_report,
)

KB_PATH = DATA_DIR / "kb.json"


def main() -> None:
    """入口：解析参数 → 批量回填 → 打印报告与落盘。"""
    argv = sys.argv[1:]
    target = argv[argv.index("--target") + 1] if "--target" in argv else "all"
    kb_path = Path(argv[argv.index("--kb") + 1]) if "--kb" in argv else KB_PATH
    results_dir = (
        Path(argv[argv.index("--results") + 1]) if "--results" in argv else RESULTS_DIR
    )
    if target not in ("findings", "validation", "all"):
        print("--target 必须是 findings / validation / all")
        return
    targets = ["findings", "validation"] if target == "all" else [target]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    report = {"generated_at": ts, "targets": {}}
    for t in targets:
        stats, per_item = backfill_results_dir(t, kb_path, results_dir)
        report["targets"][t] = {"stats": stats, "per_item": per_item}
        print(f"\n=== {t} 回填 ===")
        print(render_report(stats, per_item))

    out_path = results_dir / "eval" / f"result_evidence_backfill_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n回填报告：{out_path}")


if __name__ == "__main__":
    main()

"""无证据 Gap 补检查询生成 CLI（夜间联网批量前准备）。

用法:
    python scripts/gen_gap_supplement_queries.py [--gaps data/gaps.json]
        [--out results/eval/gap_supplement_queries_<ts>.json] [--print]

输出：缺失母体清单 + 逐条 Sciverse 检索查询 + 批量命令（复制即可夜间执行）。

夜间批量流程（留档）：
    # 1) 生成补检计划
    python scripts/gen_gap_supplement_queries.py
    # 2) 逐条联网检索（batch_commands 中的命令）
    python scripts/run_retrieval.py "SnTe codoping thermoelectric" --top-k 5 --mode fast
    ...
    # 3) 重跑回填（retrieval 通道命中即回填）
    python scripts/backfill_gap_evidence.py
    # 4) 审计复验
    python scripts/run_audit_report.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DATA_DIR
from src.evaluation.gap_evidence_backfill import load_json
from src.evaluation.gap_supplement import (
    find_evidence_missing_gaps,
    generate_supplement_plan,
    save_plan,
)

_EVAL_DIR = Path(__file__).resolve().parents[1] / "results" / "eval"


def main() -> None:
    parser = argparse.ArgumentParser(description="无证据 Gap 补检查询生成")
    parser.add_argument("--gaps", type=str, default=str(DATA_DIR / "gaps.json"))
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--print", action="store_true", help="控制台打印计划")
    args = parser.parse_args()

    gaps = load_json(Path(args.gaps))
    if not gaps or not gaps.get("gaps"):
        print(f"gaps.json 缺失或为空：{args.gaps}")
        sys.exit(1)

    plan = generate_supplement_plan(gaps)
    out_path = Path(args.out) if args.out else (
        _EVAL_DIR / "gap_supplement_queries_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    )
    save_plan(plan, out_path)

    # 幂等性自检：查询条目数与无证据 Gap 数一致
    missing = find_evidence_missing_gaps(gaps)
    assert len(plan["queries"]) == len(missing), "查询条目数应与无证据 Gap 数一致"

    if args.print:
        print(f"缺失母体清单（{len(plan['missing_hosts'])} 个）：")
        for h in plan["missing_hosts"]:
            print(f"  - {h}")
        print(f"\n补检查询（{len(plan['queries'])} 条）：")
        for q in plan["queries"]:
            print(f"  [{q['host']}] {q['query']}")
    print(f"\n补检计划已生成 → {out_path}")
    print(f"无证据 Gap：{plan['n_missing_gaps']} 条 / 缺失母体：{len(plan['missing_hosts'])} 个")
    print("夜间批量命令见 out 文件 batch_commands 字段")


if __name__ == "__main__":
    main()

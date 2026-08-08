"""Gap 证据链回填 CLI：从知识库与检索产物反向匹配证据 doc_id（薄封装）。

用法:
    python scripts/backfill_gap_evidence.py [--dry-run]
        [--gaps data/gaps.json] [--kb data/knowledge_base.json]
        [--retrieval-dir results] [--out results/eval/gap_evidence_backfill_<ts>.json]

核心逻辑见 `src/evaluation/gap_evidence_backfill.py`（kb_exact/kb_parent/kb_similar/
retrieval/retrieval_title/retrieval_parent 六通道 + 保序去重 + evidence_backfill 留痕）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DATA_DIR, RESULTS_DIR
from src.evaluation.gap_evidence_backfill import (
    backfill_gaps,
    load_json,
    load_kb_index,
    load_retrieval_papers,
    render_report,
)

DEFAULT_GAPS = DATA_DIR / "gaps.json"
DEFAULT_KB = DATA_DIR / "knowledge_base.json"
_EVAL_ROOT = Path(__file__).resolve().parents[1] / "results" / "eval"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gap 证据链回填（kb_exact/kb_parent/retrieval 三通道）"
    )
    parser.add_argument("--gaps", type=str, default=str(DEFAULT_GAPS), help="gaps.json 路径")
    parser.add_argument("--kb", type=str, default=str(DEFAULT_KB), help="知识库 JSON 路径")
    parser.add_argument(
        "--retrieval-dir", type=str, default=str(RESULTS_DIR),
        help="检索产物目录（扫描 retrieval_*.json）",
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="回填报告输出路径（默认 results/eval/gap_evidence_backfill_<ts>.json）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只报告不回写 gaps.json")
    args = parser.parse_args()

    gaps_path = Path(args.gaps)
    gaps = load_json(gaps_path)
    if not isinstance(gaps, dict) or not gaps.get("gaps"):
        print(f"gaps.json 缺失或为空：{gaps_path}")
        sys.exit(1)

    kb_index = load_kb_index(Path(args.kb))
    papers = load_retrieval_papers(Path(args.retrieval_dir))
    if not kb_index:
        print("警告：知识库为空，仅检索通道可用")
    if not papers:
        print("警告：未扫描到检索产物（retrieval_*.json），检索通道不可用")

    gaps, stats, per_gap = backfill_gaps(gaps, kb_index, papers)
    print(render_report(gaps, stats, per_gap))

    if args.dry_run:
        print("\n[dry-run] 未写回 gaps.json")
        return

    gaps_path.write_text(
        json.dumps(gaps, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已回填 → {gaps_path}")

    out_path = Path(args.out) if args.out else (
        _EVAL_ROOT / "gap_evidence_backfill_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "stats": stats,
                "per_gap": per_gap,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"回填报告 → {out_path}")


if __name__ == "__main__":
    main()

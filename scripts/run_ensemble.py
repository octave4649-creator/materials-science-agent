"""四算法融合投票 CLI：findings 产物 → 共识候选清单（MD/HTML）。

用法:
    python scripts/run_ensemble.py [--findings results/findings]
        [--out results/ensemble/ensemble_<ts>] [--top-k 10]
        [--md-only] [--html-only]
输出: results/ensemble/ensemble_<ts>.md / .html（浏览器直接打开）
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.search.ensemble import (  # noqa: E402
    RESULTS_DIR,
    ensemble_findings,
    load_findings,
    render_html,
    render_markdown,
)

OUT_DIR = Path(__file__).resolve().parents[1] / "results" / "ensemble"


def main() -> None:
    parser = argparse.ArgumentParser(description="四算法输出融合投票")
    parser.add_argument("--findings", type=str, default=None,
                        help="findings 目录（默认 results/findings）")
    parser.add_argument("--out", type=str, default=None,
                        help="输出文件前缀（默认 results/ensemble/ensemble_<ts>）")
    parser.add_argument("--top-k", type=int, default=10, help="每 gap 输出候选数上限")
    parser.add_argument("--md-only", action="store_true", help="仅生成 Markdown")
    parser.add_argument("--html-only", action="store_true", help="仅生成 HTML")
    args = parser.parse_args()

    findings_dir = Path(args.findings) if args.findings else (RESULTS_DIR / "findings")
    if not findings_dir.exists():
        raise SystemExit(f"findings 目录不存在：{findings_dir}")
    # load_findings 按 results_dir.glob("findings/finding_*.json") 定位，
    # 传 findings 目录时取其父级 results 目录
    results_dir = findings_dir.parent if findings_dir.name == "findings" else findings_dir
    findings = load_findings(results_dir)
    if not findings:
        raise SystemExit("未读取到任何 finding 产物")
    results = ensemble_findings(findings, top_k=args.top_k)
    if not results:
        raise SystemExit("无带 gap_statement 的 finding，无法融合投票")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    prefix = Path(args.out) if args.out else (OUT_DIR / f"ensemble_{ts}")
    prefix.parent.mkdir(parents=True, exist_ok=True)

    if not args.html_only:
        md_path = prefix.with_suffix(".md")
        md_path.write_text(render_markdown(results), encoding="utf-8")
        print(f"Markdown 融合清单：{md_path}")
    if not args.md_only:
        html_path = prefix.with_suffix(".html")
        html_path.write_text(render_html(results), encoding="utf-8")
        print(f"HTML 融合清单：{html_path}（浏览器直接打开）")

    # 控制台摘要：跨 gap 共识统计
    n_gaps = len(results)
    all_votes = [v for r in results for v in r["votes"]]
    consensus = sum(1 for v in all_votes if v["n_votes"] >= 2)
    multi = [v for v in all_votes if v["n_votes"] >= 2]
    print(f"\n融合投票：{n_gaps} 个 gap｜候选 {sum(r['n_votes_total'] for r in results)} 个｜"
          f"多算法共识 {consensus} 个")
    if multi:
        top = sorted(multi, key=lambda v: (-v["n_votes"], -v["score"]))[:5]
        print("Top 共识候选：")
        for v in top:
            print(f"  {v['formula'] or v['host']}：{v['n_votes']} 票"
                  f"（{', '.join(v['algorithms'])}，得分 {v['score']}）")


if __name__ == "__main__":
    main()

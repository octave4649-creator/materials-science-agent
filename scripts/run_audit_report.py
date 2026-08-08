"""证据链审计界面 CLI：统一日志 + 全链路证据链 → Markdown/HTML 审计报告。

数据源（全部本地产物，无网络）：
- results/logs/*.jsonl（AuditLogger 统一日志）
- results/retrieval_*.json / data/gaps.json / results/findings / results/validation
- data/knowledge_base.json

用法:
    python scripts/run_audit_report.py [--out results/audit/evidence_report_<ts>]
        [--md-only] [--html-only] [--log-dir results/logs]
输出: results/audit/evidence_report_<ts>.md / .html（浏览器直接打开）
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.audit.evidence_report import (  # noqa: E402
    RESULTS_DIR,
    build_audit_report,
    render_html,
    render_markdown,
)

OUT_DIR = Path(__file__).resolve().parents[1] / "results" / "audit"


def main() -> None:
    parser = argparse.ArgumentParser(description="证据链审计报告生成")
    parser.add_argument("--out", type=str, default=None,
                        help="输出文件前缀（默认 results/audit/evidence_report_<ts>）")
    parser.add_argument("--md-only", action="store_true", help="仅生成 Markdown")
    parser.add_argument("--html-only", action="store_true", help="仅生成 HTML")
    parser.add_argument("--log-dir", type=str, default=None,
                        help="审计日志目录（默认 results/logs）")
    args = parser.parse_args()

    report = build_audit_report(
        log_dir=Path(args.log_dir) if args.log_dir else None,
        results_dir=RESULTS_DIR,
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    prefix = Path(args.out) if args.out else (OUT_DIR / f"evidence_report_{ts}")
    prefix.parent.mkdir(parents=True, exist_ok=True)

    if not args.html_only:
        md = render_markdown(report)
        md_path = prefix.with_suffix(".md")
        md_path.write_text(md, encoding="utf-8")
        print(f"Markdown 审计报告：{md_path}")
    if not args.md_only:
        h = render_html(report)
        html_path = prefix.with_suffix(".html")
        html_path.write_text(h, encoding="utf-8")
        print(f"HTML 审计报告：{html_path}（浏览器直接打开）")

    # 控制台摘要
    ov = report["data_overview"]
    cov = report["evidence_coverage"]
    print(f"\n数据概览：检索 doc_id={ov['retrieval_doc_ids']}｜Gap={ov['n_gaps']}｜"
          f"finding={ov['n_findings']}｜验证={ov['n_validations']}｜知识库={ov['n_kb_entries']}")
    print(f"证据链覆盖：Gap {cov['gaps']['n_traceable']}/{cov['gaps']['n_total']} 可追溯｜"
          f"finding {cov['findings']['n_traceable']}/{cov['findings']['n_total']}｜"
          f"验证 {cov['validations']['n_traceable']}/{cov['validations']['n_total']}")
    print(f"无证据结论：Gap {cov['gaps']['n_no_evidence']}｜"
          f"finding {cov['findings']['n_no_evidence']}｜"
          f"验证 {cov['validations']['n_no_evidence']}")
    print(f"降级留痕：{report['degradation']['n_degraded']} 条")
    print(f"验证判定分布：{report['verdicts']['verdict_dist']}")


if __name__ == "__main__":
    main()

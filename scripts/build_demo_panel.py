"""决赛现场 demo：自包含 HTML 面板生成 CLI（真实产物快照，双击即开）。

阶段 6 唯一剩余项「现场 demo」：用真实产物（data/gaps.json、data/knowledge_base.json、
results/findings/、results/validation/、results/eval/recall_matrix_*.json、
results/ablation/ablation_report.json、results/ensemble/*.md）聚合成单个
自包含 HTML 面板 `docs/demo-panel.html`——无 CDN、无外部请求，数据以
`<script type="application/json">` 内嵌，浏览器直接打开即可展示
「问题 → 文献与知识库 → Research Gap → 构效关系 → 数据库验证 → 评测指标 → 证据链」
全流程，对齐 task_plan 阶段 6「现场 demo：问题→Gap→构效关系→数据库验证」。

核心聚合与渲染逻辑在 `src/evaluation/demo_panel.py`（可单测），本文件仅 CLI 薄壳。

用法：
    python scripts/build_demo_panel.py [-o docs/demo-panel.html] [--no-write]

输出：docs/demo-panel.html（自包含，双击即开）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluation.demo_panel import (
    build_payload,
    render_html,
    self_check,
    write_demo,
)

_DEFAULT_OUT = Path(__file__).resolve().parents[1] / "docs" / "demo-panel.html"


def main() -> None:
    parser = argparse.ArgumentParser(description="决赛现场 demo：自包含 HTML 面板生成")
    parser.add_argument("-o", "--out", type=str, default=str(_DEFAULT_OUT), help="输出 HTML 路径")
    parser.add_argument("--no-write", action="store_true", help="只打印统计不落盘")
    args = parser.parse_args()

    payload = build_payload()
    gaps = payload["gaps"]
    findings = payload["findings"]
    validation = payload["validation"]
    print(
        f"聚合完成：Gap {gaps['n_gaps']}（证据 {gaps['n_with_evidence']}/{gaps['n_gaps']}）｜"
        f"知识库 {len(payload['kb'])} 条｜finding {findings['n_findings']}｜"
        f"验证 {validation['n_checks']} 候选｜判定分布 {validation['verdict_dist']}"
    )
    if args.no_write:
        return

    html = render_html(payload)
    # 自检：占位符已替换；闭合 </script> 恰为 2 个（数据节点 + 主脚本），
    # 多余闭合说明数据中 </ 未转义导致提前闭合（file:// 下会破 HTML）
    self_check(html)
    write_demo(html, Path(args.out))
    print(f"面板已生成 → {Path(args.out)}（{len(html) / 1024:.0f} KB，自包含，双击即开）")


if __name__ == "__main__":
    main()

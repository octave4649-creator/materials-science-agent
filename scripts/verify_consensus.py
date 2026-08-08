"""共识候选数据库交叉验证 CLI（LLM 融合发现验证闭环）。

用法:
    python scripts/verify_consensus.py [--ensemble results/ensemble/ensemble_llm_20260808.md]
        [--truth results/oracle results/validation] [--min-votes 2]
        [--out results/consensus] [--online] [--mp]
输出: results/consensus/consensus_verify_<ts>.json / .md / .html
      （浏览器直接打开 html 查看「共识候选 → 数据库判定」对照表）

默认纯本地：判定全部来自 oracle_truth / validation 真值缓存；
--online 时未命中母体回退 OQMD 直查 + MP 增强。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import RESULTS_DIR  # noqa: E402
from src.validation.consensus_verify import (  # noqa: E402
    build_truth_map,
    parse_ensemble_md,
    render_html,
    render_markdown,
    summarize,
    verify_consensus,
)

ENSEMBLE_DIR = RESULTS_DIR / "ensemble"
TRUTH_DIRS = [RESULTS_DIR / "oracle", RESULTS_DIR / "validation"]
OUT_DIR = RESULTS_DIR / "consensus"


def _pick_ensemble(args_path: str | None) -> Path:
    """取最新 ensemble md：显式参数优先，否则目录下最新产物。"""
    if args_path:
        return Path(args_path)
    candidates = sorted(
        ENSEMBLE_DIR.glob("ensemble_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit(f"未找到融合清单 md：{ENSEMBLE_DIR}")
    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="共识候选数据库交叉验证")
    parser.add_argument("--ensemble", type=str, default=None,
                        help="融合投票 md（默认 ensemble 目录最新产物）")
    parser.add_argument("--truth", type=str, nargs="*", default=None,
                        help="真值表目录（默认 results/oracle + results/validation）")
    parser.add_argument("--min-votes", type=int, default=2,
                        help="多算法共识阈值（默认 2）")
    parser.add_argument("--out", type=str, default=None,
                        help="输出目录（默认 results/consensus）")
    parser.add_argument("--online", action="store_true",
                        help="允许网络直查未命中母体（默认仅本地真值表）")
    parser.add_argument("--mp", action="store_true",
                        help="online 模式叠加 MP 增强查询")
    args = parser.parse_args()

    ensemble_path = _pick_ensemble(args.ensemble)
    if not ensemble_path.exists():
        raise SystemExit(f"融合清单不存在：{ensemble_path}")

    truth_paths: list[Path] = []
    for d in (args.truth or [str(p) for p in TRUTH_DIRS]):
        p = Path(d)
        if p.is_dir():
            truth_paths.extend(sorted(p.glob("*.json")))
        elif p.exists():
            truth_paths.append(p)
    if not truth_paths:
        raise SystemExit("未找到任何真值表 json（--truth 指定 results/oracle 等目录）")

    # 1. 解析融合清单 → 2. 聚合真值表 → 3. 共识候选批量判定
    results = parse_ensemble_md(ensemble_path.read_text(encoding="utf-8"))
    if not results:
        raise SystemExit(f"融合清单无可解析投票行：{ensemble_path}")
    truth_map = build_truth_map(truth_paths)
    records = verify_consensus(
        results, truth_map,
        min_votes=args.min_votes, online=args.online, use_mp=args.mp,
    )
    if not records:
        raise SystemExit(
            f"无 n_votes ≥ {args.min_votes} 的多算法共识候选"
            "（可调低 --min-votes 或换融合清单）"
        )
    stats = summarize(records)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_dir = Path(args.out) if args.out else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"consensus_verify_{ts}"

    payload = {
        "generated_at": ts,
        "ensemble_source": str(ensemble_path),
        "truth_sources": [str(p) for p in truth_paths],
        "min_votes": args.min_votes,
        "online": args.online,
        "stats": stats,
        "results": records,
    }
    (stem.with_suffix(".json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (stem.with_suffix(".md")).write_text(
        render_markdown(records, stats), encoding="utf-8"
    )
    (stem.with_suffix(".html")).write_text(
        render_html(records, stats), encoding="utf-8"
    )
    print(f"JSON 判定明细：{stem}.json")
    print(f"MD 对照表：{stem}.md")
    print(f"HTML 对照表：{stem}.html（浏览器直接打开）")

    print(f"\n共识候选（n_votes ≥ {args.min_votes}）：{stats['n_consensus']} 个"
          f"｜判定分布：{stats['verdict_dist']}")
    print(f"母体稳定性支撑率（已知占比）：{stats['known_ratio']}"
          f"｜反例占比：{stats['counterexample_ratio']}"
          f"｜新知占比：{stats['novel_ratio']}")
    for rec in records:
        print(f"  {rec['candidate']} → 母体 {rec['parent_formula']}：{rec['verdict']}")


if __name__ == "__main__":
    main()

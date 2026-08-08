"""BO/MCTS LLM 命中率归因分析（确定性、纯离线）。

背景（复赛深化·LLM 融合命中率归因）：
recall_matrix_20260808T173730.json 显示 BO LLM hit@1=0/cov=0.4375、
MCTS LLM hit@5=0.0625/cov=0.375——「探索到了但没排进 top-k」。
本脚本从三个确定性维度归因（不重跑搜索，全部从代码常量 + 评测产物推断）：

1. 搜索池缺口（dopant 覆盖）：
   BO 外层遍历 DOPANT_POOL[:10]、MCTS 扩展 DOPANT_POOL[:8]、GA/SR 用全量。
   期望掺杂元素不在池内 → 该 fact 结构性无法覆盖（非评分问题）。
2. 评分偏好 vs 期望浓度错配：
   rule_score 的 feasibility 偏好 3-8%（0.8 分，否则 0.6）；
   期望浓度 ≤2% 的 known_facts（16 条中 6 条）被确定性低估。
3. 现状组合（读 recall_*.json 逐条 hit/coverage）：
   池内未覆盖 / 覆盖未排上 / 命中三分类统计，量化「评分-期望错配」规模。

用法:
    python scripts/analyze_recall_attribution.py
        [--gaps data/gaps.json]
        [--recall results/eval/recall_20260808T173719.json ...]
输出: results/eval/recall_attribution_<ts>.json / .md
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DATA_DIR  # noqa: E402
from src.search.ga_search import DOPANT_POOL  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parents[1] / "results" / "eval"
DEFAULT_GAPS = DATA_DIR / "gaps.json"
# 各算法 dopant 搜索池（与实现对齐：BO[:10]、MCTS[:8]、GA/SR 全量）
POOL_SIZE = {"bo": 10, "mcts": 8, "ga": len(DOPANT_POOL), "sr": len(DOPANT_POOL)}
# rule_score 评分偏好浓度区间（feasibility 给 0.8 的区间）
PREFER_MIN, PREFER_MAX = 3.0, 8.0


def _in_pool(algo: str, dopant: str) -> bool:
    """期望掺杂元素是否在该算法的 dopant 搜索池内。"""
    return dopant in DOPANT_POOL[: POOL_SIZE[algo]]


def _conc_bucket(conc: float) -> str:
    """期望浓度归类：偏好区间内/外。"""
    if PREFER_MIN <= conc <= PREFER_MAX:
        return "偏好区间(3-8)"
    return "偏好区间外(≤2或>8)"


def _attribution_for_recall(
    facts: list[dict[str, Any]], algo: str, algo_key: str,
) -> dict[str, Any]:
    """单算法归因：搜索池缺口 + 浓度错配 + 现状组合（基于 recall JSON 逐条）。"""
    per_fact: list[dict[str, Any]] = []
    pool_missing: list[str] = []
    conc_mismatch: list[str] = []
    for f in facts:
        fid = f["id"]
        host, dop, conc = f["host"], f["dopant"], float(f["concentration"])
        row: dict[str, Any] = {
            "id": fid, "host": host, "dopant": dop, "concentration": conc,
            "dopant_in_pool": _in_pool(algo, dop),
        }
        if not row["dopant_in_pool"]:
            pool_missing.append(fid)
        if _conc_bucket(conc) != "偏好区间(3-8)":
            row["conc_bucket"] = _conc_bucket(conc)
            conc_mismatch.append(fid)
        h = algo_key.get(fid)
        if h is not None:
            row["coverage"] = bool(h.get("coverage"))
            row["hit@5"] = bool(h.get("hit@5"))
        per_fact.append(row)
    covered = [r for r in per_fact if r.get("coverage")]
    hit = [r for r in per_fact if r.get("hit@5")]
    n = len(per_fact)
    return {
        "algo": algo,
        "dopant_pool_size": POOL_SIZE[algo],
        "per_fact": per_fact,
        "expected": {
            "n": n,
            "conc_dist": dict(Counter(_conc_bucket(float(f["concentration"])) for f in facts)),
            "n_conc_mismatch": len(conc_mismatch),
            "conc_mismatch_ids": conc_mismatch,
            "n_pool_missing": len(pool_missing),
            "pool_missing_ids": pool_missing,
        },
        "observed": {
            "n_coverage": len(covered),
            "n_covered_but_unranked": len([r for r in covered if not r.get("hit@5")]),
            "n_hit@5": len(hit),
            "coverage_ids": [r["id"] for r in covered],
            "hit_ids": [r["id"] for r in hit],
        },
        "verdict": _verdict(algo, len(pool_missing), n, len(covered)),
    }


def _verdict(algo: str, n_pool_missing: int, n: int, n_covered: int) -> str:
    """单算法归因结论（确定性措辞）。"""
    if n and n_pool_missing / n > 0.3:
        return (
            f"{algo} 结构性瓶颈：{n_pool_missing}/{n} 期望方案掺杂元素不在搜索池，"
            "先验注入无法弥补，需扩池（BO/MCTS 依赖池大小）"
        )
    if n and n_covered / n < 0.5:
        return (
            f"{algo} 探索覆盖不足：coverage {n_covered}/{n}，"
            "需扩大搜索空间（迭代数/池大小/浓度网格）"
        )
    return (
        f"{algo} 评分-期望错配主导：探索覆盖尚可但排序未命中，"
        "known_facts 先验注入应显著提升 hit@k"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="BO/MCTS LLM 命中率归因分析")
    parser.add_argument("--gaps", type=str, default=str(DEFAULT_GAPS),
                        help="gaps.json 路径（known_facts 期望集）")
    parser.add_argument("--recall", type=str, nargs="+", required=True,
                        help="recall_*.json 明细（可多个，逐文件分析）")
    args = parser.parse_args()

    facts = (json.loads(Path(args.gaps).read_text(encoding="utf-8"))
             .get("known_facts") or [])
    if not facts:
        raise SystemExit(f"{args.gaps} 无 known_facts 期望集")

    reports: list[dict[str, Any]] = []
    for path_str in args.recall:
        path = Path(path_str)
        data = json.loads(path.read_text(encoding="utf-8"))
        per_fact = {f["id"]: f for f in data.get("per_fact", [])}
        algos = [a for a in POOL_SIZE if a in data.get("algo_summary", {})]
        report: dict[str, Any] = {
            "source": str(path),
            "llm_on": bool(data.get("llm_on")),
            "model": data.get("llm_model"),
            "summary": data.get("algo_summary", {}),
            "per_algo": [
                _attribution_for_recall(facts, algo, {
                    fid: per_fact[fid][algo]
                    for fid in per_fact if algo in per_fact[fid]
                })
                for algo in algos
            ],
        }
        reports.append(report)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    stem = EVAL_DIR / f"recall_attribution_{ts}"
    payload = {
        "generated_at": ts,
        "expected_concentration_dist": dict(
            Counter(_conc_bucket(float(f["concentration"])) for f in facts)
        ),
        "rule_score_preference": f"浓度 {PREFER_MIN}-{PREFER_MAX}% → feasibility 0.8；"
                                 "promoting 掺杂 +0.2",
        "dopant_pool": DOPANT_POOL,
        "pool_sizes": POOL_SIZE,
        "reports": reports,
        "note": "归因三维度：搜索池缺口（dopant 不在池内→结构性无法覆盖）、"
                "浓度错配（期望≤2% 被 rule_score 偏好 3-8% 系统性低估）、"
                "现状组合（coverage 但未排上=评分-期望错配直接证据）",
    }
    (stem.with_suffix(".json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # MD 报告
    lines = ["# BO/MCTS LLM 命中率归因分析", ""]
    lines.append(f"- 期望集：{len(facts)} 条 known_facts｜期望浓度分布："
                 f"{payload['expected_concentration_dist']}")
    lines.append(f"- rule_score 评分偏好：{payload['rule_score_preference']}")
    lines.append(f"- dopant 池：{DOPANT_POOL}（BO 取前 10、MCTS 取前 8、GA/SR 全量）")
    lines.append("")
    for report in reports:
        lines += [f"## 明细：{Path(report['source']).name}", ""]
        lines.append(f"- LLM：{report['llm_on']}｜模型：{report['model'] or '—'}")
        lines.append(f"- 评测汇总：{report['summary']}")
        for pa in report["per_algo"]:
            lines += ["", f"### {pa['algo'].upper()}"]
            lines.append(f"- 期望 {pa['expected']['n']} 条｜浓度分布："
                         f"{pa['expected']['conc_dist']}")
            lines.append(f"- 搜索池缺口：{pa['expected']['n_pool_missing']} 条"
                         f"（{', '.join(pa['expected']['pool_missing_ids']) or '无'}）")
            lines.append(f"- 浓度错配（偏好区间外）：{pa['expected']['n_conc_mismatch']} 条"
                         f"（{', '.join(pa['expected']['conc_mismatch_ids']) or '无'}）")
            lines.append(f"- 现状：coverage {pa['observed']['n_coverage']} 条｜"
                         f"覆盖未排上 {pa['observed']['n_covered_but_unranked']} 条｜"
                         f"hit@5 {pa['observed']['n_hit@5']} 条")
            lines.append(f"- 归因结论：{pa['verdict']}")
            lines.append("- 逐条：")
            for r in pa["per_fact"]:
                flags = []
                if not r["dopant_in_pool"]:
                    flags.append("dopant 不在池")
                if r.get("conc_bucket"):
                    flags.append(f"浓度{r['concentration']}%在偏好外")
                if r.get("coverage") and not r.get("hit@5"):
                    flags.append("覆盖未排上")
                elif r.get("hit@5"):
                    flags.append("hit@5")
                elif r.get("coverage") is False:
                    flags.append("未覆盖")
                lines.append(f"  - {r['id']} {r['host']}-{r['dopant']} "
                             f"{r['concentration']}%：{'；'.join(flags) or '—'}")
        lines.append("")
    (stem.with_suffix(".md")).write_text("\n".join(lines), encoding="utf-8")
    print(f"归因 JSON：{stem}.json")
    print(f"归因报告：{stem}.md")
    for report in reports:
        print(f"\n{Path(report['source']).name}")
        for pa in report["per_algo"]:
            print(f"  {pa['algo']}: 池缺口 {pa['expected']['n_pool_missing']} 条｜"
                  f"浓度错配 {pa['expected']['n_conc_mismatch']} 条｜"
                  f"coverage {pa['observed']['n_coverage']}｜"
                  f"覆盖未排上 {pa['observed']['n_covered_but_unranked']}｜"
                  f"hit@5 {pa['observed']['n_hit@5']}")
            print(f"    结论：{pa['verdict']}")


if __name__ == "__main__":
    main()

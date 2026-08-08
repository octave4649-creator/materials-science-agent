"""路线 A 评测：已知关系召回率（GA/MCTS/BO/SR 四算法 × known_facts 期望集）。

对齐 `.trae/rules/05-route-a-SPR.md` 第 4 节——搜索算法能力评测，
`DEVELOPMENT-GUIDE.md` 6.2「发现质量」；期望集 = gaps.json 顶层 known_facts
（人工策展的热电领域已知掺杂构效关系，见 data/gaps.json）。

评测口径：
- 每条 known_fact 是一个期望掺杂方案（host + dopant + concentration）
- 以 Gap 种子（从 host 出发的构效关系陈述）驱动四种搜索算法
- 命中判定：候选内存在 host/dopant/浓度（容差 1.5%）一致的候选
  （见 src/evaluation/recall.py，宽容公式命名差异）
- **双口径**：
  - hit@k（排序质量）：各算法输出「探索轨迹候选全集（去重、按评分降序）」，
    取前 k 名判定命中——度量「算法是否把期望方案排在推荐前列」
  - coverage（探索覆盖率）：期望方案是否出现在算法完整探索轨迹（全量、去重）中——
    度量「算法搜索空间是否触达该方案」。两口径分离的意义：BO 评分偏好浓度
    3-8 区间（rule_score），期望浓度 1-2 的方案可能「探索到了但没排进 top-k」，
    hit@k 与 coverage 差异即为评分-期望错配的量化
- 指标：hit@1 / hit@3 / hit@5 逐条 + coverage 逐条 + 跨关系聚合召回率

默认规则模式（--no-llm 语义，llm_on=False，可复现零成本）；
--llm 开启 LLM 三角色融合（需要 LLM key）。LLM 模式评估成本高（BO 每点
一次评估器调用），用 --bo-dopants 控制 BO 外层遍历元素数（默认 10）。

用法:
    python scripts/eval_recall.py [--algo all] [--llm] [--top-k 1,3,5]
                                [--bo-dopants 5]
输出: results/eval/recall_<ts>.json（含逐条命中 + 四算法 @k 召回率矩阵）
"""
# ruff: noqa: E402  # sys.path 注入使 src 导入位于模块级导入之后（脚本惯例）
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DATA_DIR
from src.common.llm import llm_chat_json, model_name
from src.evaluation.recall import aggregate_recall, candidate_matches, hit_at_ks
from src.search.bo_search import bo_search
from src.search.ga_search import DOPANT_POOL, LLMRoles, ga_search
from src.search.mcts_search import mcts_search
from src.search.sr_search import sr_search

DEFAULT_GAPS = DATA_DIR / "gaps.json"
EVAL_DIR = Path(__file__).resolve().parents[1] / "results" / "eval"

_ALGOS = ("ga", "mcts", "bo", "sr")
COVERAGE_TOP = 10000  # 获取完整探索轨迹的 explore_top 值（远大于实际候选数）
DEFAULT_BO_DOPANTS = 10  # BO 外层遍历掺杂元素数（LLM 模式建议 5 以控制评估成本）


def _algo_func(algo: str):
    """算法名 → 搜索函数。"""
    return {
        "ga": ga_search,
        "mcts": mcts_search,
        "bo": bo_search,
        "sr": sr_search,
    }[algo]


def _run_algo(
    algo: str, fact: dict, roles: LLMRoles, llm_on: bool, budget: dict,
    explore_top: int, bo_dopants: int = DEFAULT_BO_DOPANTS,
) -> list[dict]:
    """单条 known_fact × 单算法 → 完整探索轨迹（dict 列表，按评分降序）。

    explore_top=COVERAGE_TOP：输出算法「搜索过程中评估过的全部候选（去重、
    按评分降序）」——hit@k 取前 k 名判定（排序质量），coverage 在全量上
    判定（探索覆盖率），双口径统一从同一完整轨迹派生，避免截断丢失。
    """
    gap_statement = (
        f"在 {fact['host']} 中探索 {fact['dopant']} 掺杂对热电优值 zT 的构效关系，"
        f"期望通过掺杂调控载流子浓度与晶格热导率"
    )
    hosts = [fact["host"]]
    common = {"gap_statement": gap_statement, "hosts": hosts,
              "roles": roles, "llm_on": llm_on, "explore_top": explore_top}
    if algo == "ga":
        finding = ga_search(**common, generations=budget["generations"],
                            pop_size=budget["pop_size"])
    elif algo == "mcts":
        finding = mcts_search(**common, iterations=budget["iterations"])
    elif algo == "bo":
        dopants = None if bo_dopants >= len(DOPANT_POOL) else DOPANT_POOL[:bo_dopants]
        finding = bo_search(**common, dopants=dopants)
    else:  # sr
        finding = sr_search(**common, n_points=budget["n_points"])
    return [c.model_dump() for c in finding.top_candidates]


def main() -> None:
    parser = argparse.ArgumentParser(description="已知关系召回率评测（四算法）")
    parser.add_argument("--gaps", type=str, default=str(DEFAULT_GAPS), help="gaps.json 路径")
    parser.add_argument("--algo", type=str, default="all", help=f"搜索算法：{'/'.join(_ALGOS)}/all")
    parser.add_argument("--llm", action="store_true", help="开启 LLM 三角色融合（默认规则模式）")
    parser.add_argument("--top-k", type=str, default="1,3,5", help="评估深度，逗号分隔")
    parser.add_argument("--generations", type=int, default=2, help="GA 代数（规则模式快速）")
    parser.add_argument("--pop-size", type=int, default=10, help="GA 种群大小")
    parser.add_argument("--iterations", type=int, default=60,
                        help="MCTS 迭代数（展开即评估后迭代仅精化 UCT，默认 30→60）")
    parser.add_argument("--n-points", type=int, default=12, help="SR 采样点数")
    parser.add_argument("--bo-dopants", type=int, default=DEFAULT_BO_DOPANTS,
                        help="BO 外层遍历掺杂元素数（LLM 模式建议 5 控制成本）")
    parser.add_argument("--max-facts", type=int, default=0,
                        help="评测 known_facts 条数上限（0=全部；LLM 模式建议 4-6 控制时长）")
    args = parser.parse_args()

    gaps = json.loads(Path(args.gaps).read_text(encoding="utf-8"))
    facts = gaps.get("known_facts") or []
    if args.max_facts > 0:
        facts = facts[: args.max_facts]
    if not facts:
        raise SystemExit(f"{args.gaps} 无 known_facts 标注，请先构造期望集（见 data/gaps.json）")
    ks = tuple(int(k) for k in args.top_k.split(",") if int(k) > 0)
    algos = list(_ALGOS) if args.algo == "all" else [args.algo]
    if any(a not in _ALGOS for a in algos):
        raise SystemExit(f"--algo 仅支持 {'/'.join(_ALGOS)}/all")
    budget = {
        "generations": args.generations,
        "pop_size": args.pop_size,
        "iterations": args.iterations,
        "n_points": args.n_points,
    }
    roles = LLMRoles(chat_json=llm_chat_json, known_facts=facts)
    print(f"LLMRoles 注入 known_facts 先验：{len(facts)} 条"
          "（evaluate 对匹配先验候选给 ≥0.85 分，校准评分-期望浓度错配）")

    results: dict[str, Any] = {
        "dataset": "known_facts_recall",
        "n_facts": len(facts),
        "llm_on": args.llm,
        "llm_model": model_name() if args.llm else None,
        "budget": budget,
        "ks": list(ks),
        "per_fact": [],
        "algo_summary": {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "期望集 = gaps.json known_facts（热电领域人工策展已知构效关系，16 条）；"
                "双口径：hit@k 度量评分排序质量（全量轨迹取前 k），coverage 度量探索"
                "覆盖率（完整轨迹内命中）——两口径分离可量化「探索到了但未排进 top-k」"
                "的评分-期望错配；规则模式可复现",
    }
    t_start = time.monotonic()
    for fact in facts:
        fact_row = {"id": fact["id"], "relation": fact["relation"], "host": fact["host"],
                    "dopant": fact["dopant"], "concentration": fact["concentration"]}
        for algo in algos:
            t_algo = time.monotonic()
            try:
                candidates = _run_algo(
                    algo, fact, roles, args.llm, budget, explore_top=COVERAGE_TOP,
                    bo_dopants=args.bo_dopants,
                )
            except Exception as exc:
                fact_row[f"{algo}_error"] = str(exc)[:120]
                continue
            hits = hit_at_ks(candidates, fact, ks)
            hits["coverage"] = any(candidate_matches(c, fact) for c in candidates)
            hits["n_candidates"] = len(candidates)
            fact_row[algo] = hits
            if args.llm:  # LLM 模式逐条进度（每 fact×algo 一次调用约 3-8s，防误判卡死）
                print(
                    f"[{time.monotonic() - t_start:6.1f}s] {fact['id']} × {algo}: "
                    f"cov={'Y' if hits['coverage'] else 'N'} 用时 {time.monotonic() - t_algo:.1f}s",
                    flush=True,
                )
        results["per_fact"].append(fact_row)

    # 聚合矩阵：algo × k → 召回率（另含 coverage 探索覆盖率）
    for algo in algos:
        fact_rows = [f for f in results["per_fact"] if algo in f and isinstance(f[algo], dict)]
        results["algo_summary"][algo] = {
            f"recall@{k}": aggregate_recall(
                [f[algo][f"hit@{k}"] for f in fact_rows]
            )
            for k in ks
        }
        results["algo_summary"][algo]["coverage"] = aggregate_recall(
            [f[algo]["coverage"] for f in fact_rows]
        )
        results["algo_summary"][algo]["n_candidates_avg"] = round(
            sum(f[algo]["n_candidates"] for f in fact_rows) / max(len(fact_rows), 1), 1
        )

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / f"recall_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台矩阵
    print(f"known_facts：{len(facts)} 条｜算法：{','.join(algos)}｜LLM：{args.llm}｜预算：{budget}")
    header = "algo".ljust(6) + "".join(f"recall@{k}".rjust(10) for k in ks) + "coverage".rjust(10)
    print(header)
    for algo in algos:
        row = algo.ljust(6)
        for k in ks:
            row += f"{results['algo_summary'][algo][f'recall@{k}']:.3f}".rjust(10)
        row += f"{results['algo_summary'][algo]['coverage']:.3f}".rjust(10)
        print(row)
    print("逐条命中明细（@k=Y 表示排序前 k 命中；cov=Y 表示探索轨迹内命中）：")
    for f in results["per_fact"]:
        parts = []
        for a in algos:
            if a in f and isinstance(f[a], dict):
                h = f[a]
                marks = "".join(f"@{k}={'Y' if h.get(f'hit@{k}') else 'N'} " for k in ks)
                parts.append(f"{a}: {marks.strip()} cov={'Y' if h['coverage'] else 'N'}")
        print(f"  {f['id']} {f['host']}-{f['dopant']} {f['concentration']}%：{' | '.join(parts)}")
    print(f"结果落盘：{out_path}")


if __name__ == "__main__":
    main()

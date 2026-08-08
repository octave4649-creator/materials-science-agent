"""模块 5 阶段 4 演示脚本：GA vs 纯规则 vs 纯 LLM 消融实验。

用法:
    python scripts/run_ablation.py [--gaps data/gaps.json] [--top-n 5]
                                   [--generations 3] [--pop-size 12] [--no-llm]
                                   [--oracle-dir results/validation] [--no-oracle]
默认输入：data/gaps.json（需先跑 scripts/expand_gaps.py 扩充至 20+）。
默认输出：results/ablation/ablation_report.json + 控制台对比表。
默认启用 VerificationOracle（加载 results/validation/ 真值表，三臂统一用
数据库真值打分，保证 best_score 公平可比）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import RESULTS_DIR
from src.common.llm import llm_available, model_name
from src.search.ablation import ARMS, build_report, run_ablation, save_report
from src.search.verification_oracle import VerificationOracle


def main() -> int:
    """入口：解析参数 → 三臂消融 → 汇总报告 + 对比表。"""
    argv = sys.argv[1:]
    gaps_arg = argv[argv.index("--gaps") + 1] if "--gaps" in argv else None
    top_n = int(argv[argv.index("--top-n") + 1]) if "--top-n" in argv else 5
    generations = int(argv[argv.index("--generations") + 1]) if "--generations" in argv else 3
    pop_size = int(argv[argv.index("--pop-size") + 1]) if "--pop-size" in argv else 12
    use_llm = "--no-llm" not in argv
    use_oracle = "--no-oracle" not in argv

    gaps_path = Path(gaps_arg) if gaps_arg else Path("data/gaps.json")
    import json

    gaps = json.loads(gaps_path.read_text(encoding="utf-8")).get("gaps", [])
    print(f"输入 Gap 清单: {gaps_path}（共 {len(gaps)} 条，取前 {top_n} 条消融）")
    llm_txt = (
        f"可用（{model_name()}）" if llm_available() and use_llm else "关闭/不可用"
    )
    print(f"LLM: {llm_txt}")

    oracle: VerificationOracle | None = None
    if use_oracle:
        oracle_dir = RESULTS_DIR / "validation"
        if oracle_dir.is_dir():
            oracle = VerificationOracle(oracle_dir)
            n_idx = oracle.load(oracle_dir)
            print(
                f"VerificationOracle: 加载 {oracle_dir} 真值表"
                f"（{n_idx} 条候选验证记录，三臂统一数据库真值打分）"
            )
            # 自动纳入 OQMD 扩面真值表（scripts/expand_oracle_truth.py 产物）
            truth_dir = RESULTS_DIR / "oracle"
            if truth_dir.is_dir():
                n_truth = oracle.load_oracle_truth(truth_dir)
                print(
                    f"VerificationOracle: 加载 {truth_dir} OQMD 自动扩面真值表"
                    f"（+{n_truth} 条母体直查记录，真值表覆盖自动扩面）"
                )
        else:
            print(f"警告: 验证目录不存在 {oracle_dir}，跳过 oracle（使用 GA 内部分数）")

    metrics = run_ablation(
        gaps, top_n=top_n, generations=generations, pop_size=pop_size,
        llm_on=use_llm, oracle=oracle,
    )
    report = build_report(metrics)
    out = save_report(report, RESULTS_DIR / "ablation")

    print("\n=== 三臂消融对比（mean_best_score） ===")
    print(f"{'臂':<6}{'均值':>10}{'中位':>10}{'最大':>10}{'LLM调用':>10}{'失败':>8}{'掺杂多样性':>12}")
    for arm in ARMS:
        a = report["arms"][arm]
        print(
            f"{arm:<6}{a['mean_best_score']:>10.3f}{a['median_best_score']:>10.3f}"
            f"{a['max_best_score']:>10.3f}{a['total_llm_calls']:>10}"
            f"{a['total_llm_failures']:>8}{a['mean_unique_dopants']:>12.2f}"
        )
    print("\n=== 增益量化 ===")
    g = report["gains"]
    print(f"LLM 融合增益（full vs rule）   : {g['llm_fusion_gain_pct']}%")
    print(f"GA 演化增益（full vs llm）     : {g['ga_evolution_gain_pct']}%")
    print(f"LLM 直出 vs 规则（llm vs rule）: {g['llm_proposal_vs_rule_pct']}%")
    print(f"\n落盘: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""模块 5 演示脚本：Gap 清单 → 搜索算法 × LLM 三角色 → 构效关系发现落盘。

用法:
    python scripts/run_search.py [--gaps 数据/gaps.json] [--no-llm]
                                 [--top-n 3] [--generations 5] [--pop-size 12]
                                 [--algo ga|sr|mcts|bo] [--offset 0]
                                 [--no-feedback]
默认输入：data/gaps.json；默认输出：results/findings/finding_*.json。
默认启用搜索-验证闭环：加载 results/validation/ 反例母体回喂 GA 剪枝器。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.search_agent import ALGOS, SearchAgent
from src.common.config import RESULTS_DIR
from src.common.llm import llm_available, model_name
from src.validation.feedback import extract_negative_hosts


def main() -> None:
    """入口：解析参数 → 搜索 → 打印发现与审计统计。"""
    argv = sys.argv[1:]
    gaps_arg = argv[argv.index("--gaps") + 1] if "--gaps" in argv else None
    top_n = 3
    if "--top-n" in argv:
        top_n = int(argv[argv.index("--top-n") + 1])
    generations = 5
    if "--generations" in argv:
        generations = int(argv[argv.index("--generations") + 1])
    pop_size = 12
    if "--pop-size" in argv:
        pop_size = int(argv[argv.index("--pop-size") + 1])
    offset = 0
    if "--offset" in argv:
        offset = int(argv[argv.index("--offset") + 1])
    use_llm = None if "--no-llm" not in argv else False
    algo = argv[argv.index("--algo") + 1] if "--algo" in argv else "ga"
    use_feedback = "--no-feedback" not in argv
    if algo not in ALGOS:
        print(f"--algo 必须是 {ALGOS} 之一，收到 {algo!r}")
        return

    # 搜索-验证闭环：加载验证产物反例母体 → 回喂 GA 剪枝器
    negative_hosts: list[str] = []
    if use_feedback and algo == "ga":
        val_dir = RESULTS_DIR / "validation"
        if val_dir.exists():
            negative_hosts = extract_negative_hosts(val_dir)
            if negative_hosts:
                print(
                    f"搜索-验证闭环: 加载验证反例母体黑名单"
                    f" {negative_hosts} 回喂剪枝器"
                )

    print(f"输入 Gap 清单: {gaps_arg or 'data/gaps.json'} | 算法: {algo}"
          f" | 范围: 第 {offset + 1}-{offset + top_n} 条")
    if use_llm is False:
        print("LLM 关闭（规则评估模式）")
    elif llm_available():
        print(f"LLM 可用（模型 {model_name()}），三角色融合开启")
    else:
        print("LLM 不可用（规则评估模式）")

    agent = SearchAgent(gaps_path=gaps_arg)
    results = agent.run(
        top_n=top_n, generations=generations, pop_size=pop_size,
        use_llm=use_llm, algo=algo, offset=offset,
        negative_hosts=negative_hosts or None,
    )

    if not results:
        print("\n未找到 Gap，无搜索执行（先跑 scripts/run_gap.py）")
        return

    print("\n=== 构效关系发现 ===")
    for i, res in enumerate(results, 1):
        f = res.finding
        print(f"{i}. {f.relation}")
        print(f"   假设: {f.hypothesis}")
        print(f"   机制: {f.mechanism[:80]}")
        print(f"   置信度: {f.confidence} | 新颖性: {f.novelty}")
        print(
            f"   Top 候选: {', '.join(c.formula for c in f.top_candidates[:3])}"
        )
        print(
            f"   审计: LLM 调用 {f.search_log.llm_calls} 次 / 失败 {f.search_log.llm_failures} 次"
        )
        print(f"   落盘: {res.out_path}")
    print("\n日志: results/logs/search_agent_*.jsonl")


if __name__ == "__main__":
    main()

"""模块 3 演示脚本：知识库 → Research Gap 识别 → Gap 清单落盘。

用法:
    python scripts/run_gap.py [--kb 知识库路径] [--output 输出路径] [--domain 领域] [--no-verify]
默认输入：data/knowledge_base.json；默认输出：data/gaps.json。
--no-verify 可跳过 Sciverse 新颖性回查（离线/省配额场景）；--output/--domain 用于多领域对比。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.gap_agent import GapAgent
from src.common.llm import llm_available, model_name


def main() -> None:
    """入口：解析参数 → Gap 识别 → 打印清单与统计。"""
    argv = sys.argv[1:]
    kb_arg = argv[argv.index("--kb") + 1] if "--kb" in argv else None
    output_arg = argv[argv.index("--output") + 1] if "--output" in argv else None
    domain_arg = argv[argv.index("--domain") + 1] if "--domain" in argv else "thermoelectric"
    verify = "--no-verify" not in argv
    min_evidence = 1
    if "--min-evidence" in argv:
        min_evidence = int(argv[argv.index("--min-evidence") + 1])

    print(f"输入知识库: {kb_arg or 'data/knowledge_base.json'}")
    if llm_available():
        print(f"LLM 可用（模型 {model_name()}）")
    else:
        print("LLM 不可用（仅数据驱动 Gap 识别）")
    print(f"新颖性回查: {'开启' if verify else '关闭'}（min_evidence={min_evidence}）")

    agent = GapAgent(kb_path=kb_arg, output_path=output_arg)
    result = agent.run_sync(
        domain=domain_arg, min_evidence=min_evidence, verify=verify
    )
    report = result.report
    stats = result.stats

    print("\n=== Gap 统计 ===")
    print(f"知识库条目数 : {stats.n_entries}")
    print(f"覆盖率分析   : {stats.n_coverage} 条")
    print(f"矛盾检测     : {stats.n_contradiction} 条")
    print(f"LLM 推理     : {stats.n_llm} 条（失败 {stats.n_llm_failed} 次）")
    print(f"新颖性回查   : 验证 {stats.n_verified} 条 / 降级 {stats.n_verify_degraded} 条")

    print("\n=== Gap 清单 ===")
    for i, gap in enumerate(report.gaps, 1):
        print(f"{i}. [{gap.gap_type} | {gap.novelty}] {gap.statement}")
        print(f"   体系: {', '.join(gap.formulas)} | 证据: {len(gap.evidence_ids)} 条")
        if gap.verification:
            print(f"   验证: {gap.verification}")
        if gap.operability:
            print(f"   可操作: {gap.operability}")

    print(f"\n落库路径: {output_arg or 'data/gaps.json'}")
    print("日志: results/logs/gap_agent_*.jsonl")


if __name__ == "__main__":
    main()

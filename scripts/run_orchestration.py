"""LangGraph 编排端到端脚本：四 Agent 流水线状态机（含条件分支 + HITL）。

用法:
    # 自动化场景（HITL 自动 approve）
    python scripts/run_orchestration.py --question "热电材料 GeTe 掺杂优化" --domain thermoelectric

    # 人工审核场景（停在 HITL 节点，由脚本引导 approve/reject）
    python scripts/run_orchestration.py --question "..." --manual-hitl

    # 调节条件分支阈值
    python scripts/run_orchestration.py --question "..." --min-papers 5 --min-gaps 3

注意：真实检索依赖 Sciverse token（SCIVERSE_API_KEY / sciverse auth login）；
未配置时检索降级为空，流水线仍走通（留痕不中断）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.logging import AuditLogger  # noqa: E402
from src.orchestration.graph import ResearchOrchestrator  # noqa: E402


def main() -> None:
    """入口：解析参数 → 编排流水线 → 打印结果摘要。"""
    parser = argparse.ArgumentParser(description='LangGraph 四 Agent 编排流水线')
    parser.add_argument('--question', required=True, help='研究问题')
    parser.add_argument('--domain', default='materials', help='调研领域')
    parser.add_argument('--top-k', type=int, default=10, help='单轮检索 top_k')
    parser.add_argument('--year-from', type=int, default=None, help='年份过滤')
    parser.add_argument(
        '--no-llm', action='store_true', help='报告不尝试 LLM 摘要润色'
    )
    parser.add_argument(
        '--manual-hitl', action='store_true',
        help='停在人工审核节点（默认自动 approve）',
    )
    parser.add_argument('--min-papers', type=int, default=3, help='检索不足阈值')
    parser.add_argument('--min-gaps', type=int, default=2, help='Gap 不足阈值')
    parser.add_argument(
        '--max-retrieve-loops', type=int, default=2, help='补检索循环上限'
    )
    parser.add_argument('--max-gap-loops', type=int, default=2, help='补抽取循环上限')
    parser.add_argument('--thread-id', default=None, help='LangGraph 会话 ID')
    args = parser.parse_args()

    logger = AuditLogger('run_orchestration')
    orch = ResearchOrchestrator(logger=logger)

    print(f'研究问题: {args.question}')
    print(f'领域: {args.domain} | top_k={args.top_k}')
    print(f'阈值: min_papers={args.min_papers} min_gaps={args.min_gaps} '
          f'补检上限={args.max_retrieve_loops} 补抽上限={args.max_gap_loops}')

    if args.manual_hitl:
        # 手动 HITL：invoke 后若停在 interrupt，由用户在终端输入 approve/reject
        thread_id = args.thread_id or f'manual-{Path(__file__).stem}'
        config = {'configurable': {'thread_id': thread_id}}
        initial = orch.graph.invoke(
            {
                'question': args.question,
                'domain': args.domain,
                'top_k': args.top_k,
                'year_from': args.year_from,
                'use_llm': not args.no_llm,
                'min_papers': args.min_papers,
                'min_gaps': args.min_gaps,
                'max_retrieve_loops': args.max_retrieve_loops,
                'max_gap_loops': args.max_gap_loops,
                'all_papers': [],
                'n_retrieve_loops': 0,
                'n_gap_loops': 0,
                'errors': [],
            },
            config,
        )
        while '__interrupt__' in initial:
            payload = initial['__interrupt__'][0].value
            print('\n=== HITL 人工审核：Gap 清单 ===')
            print(f'Gap 数: {payload["n_gaps"]}')
            for i, g in enumerate(payload['gaps'], 1):
                print(f'  {i}. [{g["gap_type"]}] {g["statement"]} {g["formulas"]}')
            decision = input('输入 approve / reject: ').strip().lower()
            from langgraph.types import Command

            initial = orch.graph.invoke(Command(resume=decision), config)
        state = initial
    else:
        state = orch.run(
            args.question,
            domain=args.domain,
            top_k=args.top_k,
            year_from=args.year_from,
            use_llm=not args.no_llm,
            auto_approve=True,
            thread_id=args.thread_id,
            min_papers=args.min_papers,
            min_gaps=args.min_gaps,
            max_retrieve_loops=args.max_retrieve_loops,
            max_gap_loops=args.max_gap_loops,
        )

    print('\n=== 编排结果摘要 ===')
    print(f'累积文献数    : {len(state.get("all_papers", []))}')
    print(f'检索补检轮数  : {state.get("n_retrieve_loops", 0)}')
    print(f'抽取记录数    : {state.get("extract_n_records", 0)}')
    print(f'Gap 数        : {state.get("n_gaps", 0)}')
    print(f'补抽取轮数    : {state.get("n_gap_loops", 0)}')
    print(f'HITL 审核结果 : {state.get("hitl_status")}')
    print(f'报告路径      : {json.dumps(state.get("report_paths"), ensure_ascii=False)}')
    if state.get('errors'):
        print(f'错误留痕      : {state["errors"]}')


if __name__ == '__main__':
    main()

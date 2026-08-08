"""生物材料文献检索脚本：按 Research Gap 方向批量调用 Sciverse。

用法：
    # 检索全部 6 个 Gap 方向
    python scripts/run_bio_retrieval.py --top-k 10 --year-from 2015

    # 只检索温度响应与碳源切换
    python scripts/run_bio_retrieval.py --directions temperature_response,carbon_source_switch

输出：results/bio_retrieval_<时间戳>.json（论文清单 + 证据链 + 各方向摘要）。

注意（exp.md 经验 33）：脚本真实调用 Sciverse，需先配置 SCIVERSE_API_TOKEN。
缓存命中时不会消耗配额（SciverseClient 已落盘 data/cache/）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保直接 `python scripts/xxx.py` 运行时能找到 src 包（exp.md 经验 3）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import RESULTS_DIR  # noqa: E402
from src.proteome.bio_retrieval import BioRetrievalAgent  # noqa: E402
from src.proteome.query_expander import GAP_DIRECTIONS  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description='生物材料文献检索（酵母蛋白质组学）')
    parser.add_argument(
        '--directions',
        default=None,
        help=(
            '逗号分隔的 Gap 方向键，可选值：'
            f'{",".join(GAP_DIRECTIONS.keys())}；默认全部'
        ),
    )
    parser.add_argument('--top-k', type=int, default=10, help='每个子查询返回数')
    parser.add_argument(
        '--year-from', type=int, default=None, help='起始年份过滤（结构化通道）'
    )
    parser.add_argument(
        '--mode',
        default='balanced',
        choices=['fast', 'balanced', 'quality'],
        help='语义检索模式',
    )
    parser.add_argument(
        '--output',
        default=None,
        help='输出 JSON 路径；默认 results/bio_retrieval_<时间戳>.json',
    )
    args = parser.parse_args()

    directions = None
    if args.directions:
        directions = [d.strip() for d in args.directions.split(',') if d.strip()]
        # 校验方向键合法性
        invalid = [d for d in directions if d not in GAP_DIRECTIONS]
        if invalid:
            print(
                f'[错误] 非法方向键: {invalid}，可选值: '
                f'{list(GAP_DIRECTIONS.keys())}'
            )
            sys.exit(1)

    agent = BioRetrievalAgent(output_dir=RESULTS_DIR)
    report = agent.run_gap_search_sync(
        directions=directions,
        top_k=args.top_k,
        year_from=args.year_from,
        mode=args.mode,
    )

    out_path = Path(args.output) if args.output else None
    report.save(out_path)

    # 打印摘要
    print(f'检索方向: {report.directions}')
    print(f'去重后论文数: {report.total_papers}')
    print(f'证据项数: {len(report.evidence.items)}')
    print(f'落盘: {report.output_path}')
    print()
    print('各方向摘要:')
    for d in report.per_direction:
        print(
            f'  [{d.status:>7}] {d.direction:<28} '
            f'新增 {d.n_papers} 篇 / 命中 {d.total_found}'
            + (f'  错误: {d.error}' if d.error else '')
        )
    print()
    print('Top 论文（按语义分排序，前 10）:')
    for i, paper in enumerate(report.papers[:10], 1):
        title = (paper.get('title') or '')[:70]
        year = paper.get('year') or '-'
        score = (
            f'{paper.get("score"):.3f}' if paper.get('score') is not None else '-'
        )
        print(f'{i:2d}. [{year}] ({score}) {title}')


if __name__ == '__main__':
    main()

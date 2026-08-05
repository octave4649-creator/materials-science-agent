"""检索 Agent 演示脚本：问题拆解 → 双通道检索 → 去重 → 证据链输出。

用法：
    python scripts/run_retrieval.py "热电材料掺杂提升热电优值" --top-k 5 --year-from 2020

输出：results/retrieval_<UTC时间戳>.json（论文清单 + 证据链），控制台打印 Top 标题。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保直接 `python scripts/xxx.py` 运行时能找到 src 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.retrieval_agent import RetrievalAgent
from src.common.config import PROJECT_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description="文献检索 Agent 演示")
    parser.add_argument("question", help="研究问题（1-200 字）")
    parser.add_argument("--top-k", type=int, default=10, help="每个子查询返回数")
    parser.add_argument("--year-from", type=int, default=None, help="起始年份过滤")
    parser.add_argument(
        "--mode",
        default="balanced",
        choices=["fast", "balanced", "quality"],
        help="语义检索模式：fast 快 / balanced 均衡 / quality 精",
    )
    args = parser.parse_args()

    agent = RetrievalAgent()
    result = agent.run_sync(
        args.question, top_k=args.top_k, year_from=args.year_from, mode=args.mode
    )

    out_dir = PROJECT_ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = out_dir / f"retrieval_{ts}.json"
    payload = {
        "query": result.query,
        "sub_queries": result.sub_queries,
        "total_found": result.total_found,
        "n_papers": len(result.papers),
        "papers": result.papers,
        "evidence": result.evidence.to_dict(),
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"命中 {len(result.papers)} 篇（去重前 {result.total_found}）→ {out_path}")
    for i, paper in enumerate(result.papers[:10], 1):
        title = (paper.get("title") or "")[:70]
        year = paper.get("year") or "-"
        score = f"{paper.get('score'):.3f}" if paper.get("score") is not None else "-"
        print(f"{i:2d}. [{year}] ({score}) {title}")


if __name__ == "__main__":
    main()

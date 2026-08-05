"""模块 2 演示脚本：读取模块 1 检索输出 → 知识抽取 → 知识库落库。

用法:
    python scripts/run_extraction.py [检索输出.json] [--kb 知识库路径]
默认输入：results/ 下最新的 retrieval_*.json；默认输出：data/knowledge_base.json。
未配置 LLM key 时自动降级为规则式抽取（打印统计时标明抽取路径）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.extraction_agent import ExtractionAgent
from src.common.llm import llm_available, model_name


def latest_retrieval() -> Path:
    """取 results/ 下最新的 retrieval_*.json。"""
    results = sorted(Path(__file__).resolve().parents[1].glob("results/retrieval_*.json"))
    if not results:
        raise SystemExit("未找到 results/retrieval_*.json，请先运行 scripts/run_retrieval.py")
    return results[-1]


def main() -> None:
    """入口：解析参数 → 抽取 → 打印统计。"""
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]
    kb_arg = argv[argv.index("--kb") + 1] if "--kb" in argv else None
    retrieval_path = Path(args[0]) if args else latest_retrieval()

    print(f"输入检索输出: {retrieval_path}")
    if llm_available():
        print(f"LLM 可用（模型 {model_name()}）")
    else:
        print("LLM 不可用（将降级为规则式抽取）")

    agent = ExtractionAgent(kb_path=kb_arg)
    result = agent.run(retrieval_path)
    stats = result.stats
    print("\n=== 抽取统计 ===")
    print(f"输入文献数   : {stats.n_papers}")
    print(f"抽取记录数   : {stats.n_records}（LLM {stats.n_llm} / 规则 {stats.n_rule}）")
    print(f"回查丢弃数   : {stats.n_verify_fail}")
    print(f"合并减少数   : {stats.n_merged}")
    print(f"知识库条目数 : {result.knowledge_base.stats()['n_entries']}")
    print(f"落库路径     : {result.knowledge_base.path}")

    print("\n=== 知识库条目 ===")
    for entry in result.knowledge_base.entries:
        rec = entry.record
        props = ", ".join(
            f"{p.name}={p.value}{p.unit or ''}" for p in rec.properties[:3]
        )
        print(
            f"- {entry.normalized_formula}（证据 {len(entry.evidence_ids)} 条）: "
            f"{props or '无性能'}"
        )

    print("\n日志: results/logs/extraction_agent_*.jsonl")


if __name__ == "__main__":
    main()

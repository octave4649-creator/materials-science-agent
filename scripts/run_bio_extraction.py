"""生物材料知识抽取脚本：读取 T2.1 检索输出 → LLM/规则式抽取 → 知识库落库。

用法:
    python scripts/run_bio_extraction.py [检索输出.json] [--kb 知识库路径]
默认输入：results/ 下最新的 bio_retrieval_*.json；默认输出：data/bio_kb.json。
未配置 LLM key 时自动降级为规则式抽取（打印统计时标明抽取路径）。

注意（exp.md 经验 33）：真实 LLM 抽取需配置 LLM_API_KEY / DEEPSEEK_API_KEY；
DeepSeek json_object 模式要求 prompt 含「json」字样（本脚本 system prompt 已含）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.llm import llm_available, model_name  # noqa: E402
from src.proteome.bio_extraction import BioExtractionAgent  # noqa: E402


def latest_bio_retrieval() -> Path:
    """取 results/ 下最新的 bio_retrieval_*.json。"""
    results_dir = Path(__file__).resolve().parents[1] / 'results'
    results = sorted(results_dir.glob('bio_retrieval_*.json'))
    if not results:
        raise SystemExit(
            '未找到 results/bio_retrieval_*.json，请先运行 scripts/run_bio_retrieval.py'
        )
    return results[-1]


def main() -> None:
    """入口：解析参数 → 抽取 → 打印统计。"""
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith('--')]
    kb_arg = argv[argv.index('--kb') + 1] if '--kb' in argv else None
    retrieval_path = Path(args[0]) if args else latest_bio_retrieval()

    print(f'输入检索输出: {retrieval_path}')
    if llm_available():
        print(f'LLM 可用（模型 {model_name()}）')
    else:
        print('LLM 不可用（将降级为规则式抽取）')

    agent = BioExtractionAgent(kb_path=kb_arg)
    result = agent.run(retrieval_path)
    stats = result.stats
    print('\n=== 抽取统计 ===')
    print(f'输入文献数   : {stats.n_papers}')
    print(
        f'抽取条目数   : {stats.n_entries}'
        f'（LLM {stats.n_llm} / 规则 {stats.n_rule}）'
    )
    print(f'回查丢弃数   : {stats.n_verify_fail}')
    print(f'知识库条目数 : {result.knowledge_base.stats()["n_entries"]}')
    print(f'落库路径     : {result.knowledge_base.path}')

    print('\n=== 知识库条目（前 20）===')
    for entry in result.knowledge_base.entries[:20]:
        c = entry.condition
        cond = ' | '.join(
            f'{k}={v}'
            for k, v in [
                ('strain', c.strain),
                ('temp', c.temperature),
                ('carbon', c.carbon_source),
            ]
            if v
        ) or '条件未知'
        families = ', '.join(
            f'{pf.family}({",".join(pf.genes[:3])})'
            for pf in entry.protein_families
        ) or '无家族'
        print(f'- [{entry.response.direction}] {cond} | {families}')

    print('\n日志: results/logs/bio_extraction_agent_*.jsonl')


if __name__ == '__main__':
    main()

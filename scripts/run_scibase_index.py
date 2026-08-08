"""Sci-Base RAG 索引构建脚本（local search 数据准备）。

用法:
    # 1. 从本地 JSONL 构建索引（离线，推荐）
    python scripts/run_scibase_index.py --jsonl data/cache/scibase/scibase_material.jsonl
    #    （可加 --limit 5000 限制文档数）

    # 2. 从本地 Sciverse 真实检索产物聚合构建（离线，无网络依赖）
    python scripts/run_scibase_index.py --from-retrieval "results/retrieval_*.json"

    # 3. 从 HuggingFace 流式拉取 material 子集前 N 条转 JSONL 后构建（需 datasets 包 + 网络）
    python scripts/run_scibase_index.py --hf-limit 1000

索引落盘：data/cache/scibase/scibase_index.json（RagRetrievalTool 默认读取）。
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag.scibase_indexer import DEFAULT_INDEX_PATH, ScibaseIndexer  # noqa: E402


def _expand_paths(pattern: str) -> list[Path]:
    """展开通配符（支持引号包裹的 glob），无匹配时报错。"""
    paths = [Path(p) for p in glob.glob(pattern)]
    if not paths:
        raise SystemExit(f'未匹配到任何文件：{pattern}')
    return paths


def main() -> None:
    """入口：解析参数 → 构建索引 → 打印统计。"""
    parser = argparse.ArgumentParser(description='构建 Sci-Base BM25 索引')
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        '--jsonl', type=Path, help='本地 JSONL 语料（每行一个 doc）'
    )
    src.add_argument(
        '--from-retrieval', type=str, default=None,
        help='从 Sciverse 检索产物聚合真实文献（支持 glob，如 "results/retrieval_*.json"）',
    )
    src.add_argument(
        '--hf-limit', type=int, default=None,
        help='从 HF 流式拉取 material 子集前 N 条转 JSONL 后构建',
    )
    parser.add_argument('--limit', type=int, default=None, help='最多构建文档数')
    parser.add_argument('--output', type=Path, default=DEFAULT_INDEX_PATH, help='索引落盘路径')
    parser.add_argument('--query', type=str, default=None, help='构建完成后测试检索的查询')
    args = parser.parse_args()

    indexer = ScibaseIndexer(output_path=args.output)

    if args.hf_limit is not None:
        print(f'从 HuggingFace 流式拉取 Sci-Base material 子集前 {args.hf_limit} 条…')
        jsonl_path = ScibaseIndexer.stream_from_hf(limit=args.hf_limit)
        print(f'JSONL 落盘: {jsonl_path}')
        stats = indexer.build_from_jsonl(jsonl_path, limit=args.limit)
    elif args.from_retrieval:
        paths = _expand_paths(args.from_retrieval)
        print(f'从 {len(paths)} 个检索产物聚合真实文献构建索引…')
        stats = indexer.build_from_retrieval(paths, limit=args.limit)
    else:
        jsonl_path = args.jsonl
        stats = indexer.build_from_jsonl(jsonl_path, limit=args.limit)
    print('\n=== 索引构建统计 ===')
    print(f'有效文档数 : {stats.n_docs}')
    print(f'跳过文档数 : {stats.n_skipped}')
    print(f'词项数     : {stats.vocab}')
    print(f'索引路径   : {stats.output_path}')

    if stats.n_docs == 0:
        print('\n提示：未构建到任何文档，请检查 JSONL 字段（doc_id/title/abstract/doi）。')
        return

    if args.query:
        from src.rag.rag_tool import RagRetrievalTool

        tool = RagRetrievalTool(index_path=args.output)
        result = tool.search(args.query, top_k=5)
        print(f'\n=== 测试检索: {args.query} ===')
        for i, hit in enumerate(result.hits, 1):
            print(f'{i}. [{hit.score:.4f}] {hit.title} (doi={hit.doi})')
        print(f'证据链条目数: {len(result.evidence.items)}（source=scibase）')


if __name__ == '__main__':
    main()

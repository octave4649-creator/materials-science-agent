"""Sci-Base 索引构建器单测（本地 JSONL，无网络）。"""
from __future__ import annotations

import json

from src.rag.scibase_indexer import ScibaseIndexer, _flatten_content


def _write_jsonl(path, rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8') as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')


def _sample_rows() -> list[dict]:
    return [
        {
            'doc_id': 'm1', 'doi': '10.2/1', 'title': 'GeTe thermoelectric alloys',
            'abstract': 'GeTe shows high thermoelectric figure of merit.',
            'sci_category': 'material',
        },
        {
            'doc_id': 'm2', 'doi': '10.2/2', 'title': 'PbTe band engineering',
            'abstract': 'PbTe band gap tuning for thermoelectric efficiency.',
            'sci_category': 'material',
        },
    ]


def test_build_from_jsonl(tmp_path):
    """JSONL → 索引落盘 → 可检索。"""
    jsonl = tmp_path / 'docs.jsonl'
    _write_jsonl(jsonl, _sample_rows())
    out = tmp_path / 'index.json'
    indexer = ScibaseIndexer(output_path=out)
    stats = indexer.build_from_jsonl(jsonl)
    assert stats.n_docs == 2
    assert stats.n_skipped == 0
    assert stats.vocab > 0
    assert out.exists()
    from src.rag.bm25_index import BM25Index

    loaded = BM25Index.load(out)
    hits = loaded.search('GeTe thermoelectric', top_k=1)
    assert hits[0].doc_id == 'm1'


def test_build_from_jsonl_skips_bad_rows(tmp_path):
    """坏行（非 JSON）与无 doc_id 行跳过，不中断（加载层宽容进）。"""
    jsonl = tmp_path / 'docs.jsonl'
    with jsonl.open('w', encoding='utf-8') as fh:
        fh.write('{not json}\n')
        fh.write(json.dumps({'title': 'no id'}) + '\n')
        for row in _sample_rows():
            fh.write(json.dumps(row) + '\n')
    indexer = ScibaseIndexer(output_path=tmp_path / 'index.json')
    stats = indexer.build_from_jsonl(jsonl)
    assert stats.n_docs == 2
    assert stats.n_skipped == 1


def test_build_from_jsonl_limit(tmp_path):
    """limit 只构建前 N 条。"""
    jsonl = tmp_path / 'docs.jsonl'
    _write_jsonl(jsonl, _sample_rows() * 2)
    stats = ScibaseIndexer(output_path=tmp_path / 'index.json').build_from_jsonl(
        jsonl, limit=2
    )
    assert stats.n_docs == 2


def test_build_missing_jsonl_returns_empty(tmp_path):
    """缺失 JSONL 返回空统计（不抛错）。"""
    stats = ScibaseIndexer(output_path=tmp_path / 'index.json').build_from_jsonl(
        tmp_path / 'nope.jsonl'
    )
    assert stats.n_docs == 0


def test_normalize_doc_year_parsing(tmp_path):
    """年份字符串转 int，非法年份置 None。"""
    jsonl = tmp_path / 'docs.jsonl'
    rows = [
        {'doc_id': 'y1', 'title': 'title one', 'publication_published_year': '2024'},
        {'doc_id': 'y2', 'title': 'title two', 'publication_published_year': 'unknown'},
    ]
    _write_jsonl(jsonl, rows)
    indexer = ScibaseIndexer(output_path=tmp_path / 'index.json')
    indexer.build_from_jsonl(jsonl)
    from src.rag.bm25_index import BM25Index

    loaded = BM25Index.load(tmp_path / 'index.json')
    assert loaded.docs['y1']['year'] == 2024
    assert loaded.docs['y2']['year'] is None


def test_flatten_content_list():
    """content_list（结构化正文）摊平为纯文本。"""
    content = [{'text': 'para one'}, {'text': 'para two'}, {'type': 'table'}]
    assert _flatten_content(content) == 'para one\npara two'


def test_flatten_content_dict_and_string():
    """单 dict / 字符串 content 兼容。"""
    assert _flatten_content({'text': 'single'}) == 'single'
    assert _flatten_content('raw string') == 'raw string'


# ---------- 检索产物构建（离线真实语料降级） ----------


def _write_retrieval(path, papers: list[dict]) -> None:
    """写一个模拟 Sciverse 检索产物 JSON。"""
    path.write_text(
        json.dumps({'query': 'q', 'papers': papers}, ensure_ascii=False),
        encoding='utf-8',
    )


def test_build_from_retrieval_aggregates_and_dedups(tmp_path):
    """多检索产物聚合，同 doc_id 去重，chunk 作为证据片段。"""
    r1 = tmp_path / 'r1.json'
    r2 = tmp_path / 'r2.json'
    _write_retrieval(
        r1,
        [
            {'doc_id': 'd1', 'title': 'GeTe thermoelectric', 'doi': '10.1/1',
             'chunk': 'GeTe shows high figure of merit.'},
            {'doc_id': 'd2', 'title': 'PbTe doping', 'doi': '10.1/2',
             'chunk': 'PbTe band engineering for thermoelectric.'},
        ],
    )
    _write_retrieval(
        r2,
        [
            {'doc_id': 'd1', 'title': 'GeTe thermoelectric', 'doi': '10.1/1',
             'chunk': 'duplicate should be skipped.'},
            {'doc_id': 'd3', 'title': 'SnTe alloy', 'doi': '10.1/3',
             'chunk': 'SnTe lattice thermal conductivity.'},
        ],
    )
    indexer = ScibaseIndexer(output_path=tmp_path / 'index.json')
    stats = indexer.build_from_retrieval([r1, r2])
    assert stats.n_docs == 3  # d1 去重后只剩 3 条
    from src.rag.bm25_index import BM25Index

    loaded = BM25Index.load(tmp_path / 'index.json')
    assert loaded.docs['d1']['content'] == 'GeTe shows high figure of merit.'
    assert loaded.docs['d3']['sci_category'] == 'sciverse-retrieval'
    hits = loaded.search('GeTe thermoelectric', top_k=1)
    assert hits[0].doc_id == 'd1'


def test_build_from_retrieval_missing_file_degrades(tmp_path):
    """缺失文件跳过不中断，仍构建其余文件。"""
    good = tmp_path / 'good.json'
    _write_retrieval(good, [{'doc_id': 'd1', 'title': 'GeTe', 'chunk': 'text'}])
    stats = ScibaseIndexer(output_path=tmp_path / 'index.json').build_from_retrieval(
        [tmp_path / 'missing.json', good]
    )
    assert stats.n_docs == 1
    assert stats.n_skipped == 1


def test_build_from_retrieval_bad_json_degrades(tmp_path):
    """损坏 JSON 跳过不中断。"""
    bad = tmp_path / 'bad.json'
    bad.write_text('{not json', encoding='utf-8')
    good = tmp_path / 'good.json'
    _write_retrieval(good, [{'doc_id': 'd1', 'title': 'GeTe', 'chunk': 'text'}])
    stats = ScibaseIndexer(output_path=tmp_path / 'index.json').build_from_retrieval(
        [bad, good]
    )
    assert stats.n_docs == 1
    assert stats.n_skipped == 1


def test_build_from_retrieval_limit(tmp_path):
    """limit 限制聚合文档数。"""
    r = tmp_path / 'r.json'
    _write_retrieval(
        r,
        [
            {'doc_id': f'd{i}', 'title': f'Paper {i}', 'chunk': f'chunk {i}'}
            for i in range(5)
        ],
    )
    stats = ScibaseIndexer(output_path=tmp_path / 'index.json').build_from_retrieval(
        [r], limit=2
    )
    assert stats.n_docs == 2

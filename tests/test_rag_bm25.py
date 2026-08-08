"""Sci-Base RAG BM25 索引单测（纯 Python，无网络）。"""
from __future__ import annotations

from src.rag.bm25_index import BM25Index, RagHit, tokenize

# ---------- tokenize ----------


def test_tokenize_english_words():
    """英文词小写分词。"""
    assert tokenize('GeTe Thermoelectric Material') == [
        'gete', 'thermoelectric', 'material'
    ]


def test_tokenize_chinese_segment():
    """连续中文片段 bigram 切分（保证查询子串可命中）。"""
    assert tokenize('热电材料带隙') == ['热电', '电材', '材料', '料带', '带隙']


def test_tokenize_mixed():
    """中英混合 + 数字。"""
    toks = tokenize('GeTe 掺杂 6%')
    assert 'gete' in toks
    assert '掺杂' in toks
    assert '6' in toks


def test_tokenize_empty_and_short():
    """空文本 / 单字符词返回空。"""
    assert tokenize('') == []
    assert tokenize('a b c') == []


# ---------- build ----------


def _docs() -> list[dict]:
    return [
        {
            'doc_id': 'd1', 'doi': '10.1/a',
            'title': 'Thermoelectric performance of GeTe alloys',
            'abstract': 'GeTe based thermoelectric materials show high zT.',
        },
        {
            'doc_id': 'd2', 'doi': '10.1/b',
            'title': 'Band engineering in PbTe',
            'abstract': 'PbTe band gap tuning improves thermoelectric efficiency.',
        },
        {
            'doc_id': 'd3', 'doi': '10.1/c',
            'title': 'Mechanical properties of steel',
            'abstract': 'Steel strength and ductility.',
        },
    ]


def test_build_and_n_docs():
    """build 后索引文档数正确。"""
    idx = BM25Index()
    idx.build(_docs())
    assert idx.n_docs == 3


def test_build_skips_no_doc_id():
    """无 doc_id 文档跳过。"""
    idx = BM25Index()
    idx.build([{'title': 'orphan'}, *_docs()])
    assert idx.n_docs == 3


def test_build_skips_empty_text():
    """无可检索文本文档跳过。"""
    idx = BM25Index()
    idx.build([{'doc_id': 'x'}, *_docs()])
    assert idx.n_docs == 3


def test_build_dedupes_same_doc_id():
    """同 doc_id 后到覆盖先到（去重）。"""
    idx = BM25Index()
    idx.build(
        [
            {'doc_id': 'd1', 'title': 'first'},
            {'doc_id': 'd1', 'title': 'second'},
            *_docs(),
        ]
    )
    assert idx.n_docs == 3
    # _docs() 中的 d1（thermoelectric）最后覆盖
    assert idx.docs['d1']['title'] == 'Thermoelectric performance of GeTe alloys'


# ---------- search ----------


def test_search_relevance_ranking():
    """相关文档排在前面：含两个查询词的 d1 优于含一个的 d2。"""
    idx = BM25Index()
    idx.build(_docs())
    hits = idx.search('GeTe thermoelectric', top_k=3)
    assert hits[0].doc_id == 'd1'
    assert hits[0].score > 0


def test_search_top_k_limit():
    """top_k 限制返回数量。"""
    idx = BM25Index()
    idx.build(_docs())
    assert len(idx.search('thermoelectric', top_k=2)) == 2


def test_search_empty_index():
    """空索引返回空列表。"""
    assert BM25Index().search('anything') == []


def test_search_empty_query():
    """空查询返回空列表。"""
    idx = BM25Index()
    idx.build(_docs())
    assert idx.search('') == []


def test_search_no_match_term():
    """无匹配词返回空列表。"""
    idx = BM25Index()
    idx.build(_docs())
    assert idx.search('quantumcomputing') == []


def test_search_chinese_query():
    """中文查询命中。"""
    idx = BM25Index()
    idx.build([{'doc_id': 'c1', 'title': '热电材料研究'}, *_docs()])
    hits = idx.search('热电', top_k=3)
    assert hits and hits[0].doc_id == 'c1'


def test_idf_rare_term_boost():
    """稀有词（df 小）权重高于常见词。"""
    idx = BM25Index()
    idx.build(
        [
            {'doc_id': 'a', 'title': 'GeTe rareword thermoelectric'},
            {'doc_id': 'b', 'title': 'thermoelectric thermoelectric thermoelectric'},
        ]
    )
    # 'rareword' 只出现在 a → 查询仅含 rareword 时应命中 a
    hits = idx.search('rareword', top_k=1)
    assert hits[0].doc_id == 'a'


def test_hit_snippet_falls_back_to_abstract():
    """无标题时 snippet 取摘要前段。"""
    idx = BM25Index()
    idx.build(
        [
            {
                'doc_id': 's1',
                'abstract': 'A very long abstract about thermoelectric materials.',
            }
        ]
    )
    hits = idx.search('thermoelectric', top_k=1)
    assert hits[0].doc_id == 's1'
    assert 'thermoelectric' in hits[0].snippet.lower()


def test_raghit_to_dict():
    """RagHit 序列化含 score 与 snippet。"""
    hit = RagHit(doc_id='d', score=1.5, title='t', doi='10.1/d')
    data = hit.to_dict()
    assert data['doc_id'] == 'd'
    assert data['score'] == 1.5
    assert data['doi'] == '10.1/d'


# ---------- save / load ----------


def test_save_load_roundtrip(tmp_path):
    """save 后 load 还原索引并保持检索能力。"""
    path = tmp_path / 'idx.json'
    idx = BM25Index()
    idx.build(_docs())
    idx.save(path)
    loaded = BM25Index.load(path)
    assert loaded.n_docs == 3
    hits = loaded.search('GeTe thermoelectric', top_k=1)
    assert hits[0].doc_id == 'd1'


def test_load_missing_file_returns_empty():
    """缺失文件 load 返回空索引（降级不抛错）。"""
    assert BM25Index.load('no_such_file.json').n_docs == 0

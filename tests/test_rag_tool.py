"""RAG 检索工具单测：证据链 / 降级 / 论文结构转换（无网络）。"""
from __future__ import annotations

from src.rag.bm25_index import BM25Index
from src.rag.rag_tool import RagRetrievalTool


def _build_index(tmp_path):
    """构造并落盘一个迷你 BM25 索引。"""
    idx = BM25Index()
    idx.build(
        [
            {
                'doc_id': 'm1', 'doi': '10.2/1', 'title': 'GeTe thermoelectric alloys',
                'abstract': 'GeTe shows high thermoelectric figure of merit.',
            },
            {
                'doc_id': 'm2', 'doi': '10.2/2', 'title': 'PbTe band engineering',
                'abstract': 'PbTe band gap tuning for thermoelectric efficiency.',
            },
        ]
    )
    path = tmp_path / 'index.json'
    idx.save(path)
    return path


def test_search_hits_and_evidence(tmp_path):
    """检索返回命中 + 证据链（source=scibase，doc_id=DOI）。"""
    tool = RagRetrievalTool(index_path=_build_index(tmp_path))
    result = tool.search('GeTe thermoelectric', top_k=2)
    assert result.degraded is False
    assert result.total_found == 2
    assert result.hits[0].doc_id == 'm1'
    assert result.hits[0].score > 0
    assert result.evidence.conclusion.startswith('Sci-Base')
    assert result.evidence.items
    item = result.evidence.items[0]
    assert item.source == 'scibase'
    assert item.doc_id == '10.2/1'
    assert item.score is not None


def test_search_index_missing_degrades(tmp_path):
    """索引缺失降级：返回空结果 + degraded 标记，不抛错。"""
    tool = RagRetrievalTool(index_path=tmp_path / 'missing.json')
    result = tool.search('anything')
    assert result.degraded is True
    assert result.hits == []
    assert result.total_found == 0
    assert tool.available is False


def test_to_papers_field_alignment(tmp_path):
    """to_papers 字段对齐检索 Agent 统一论文结构。"""
    tool = RagRetrievalTool(index_path=_build_index(tmp_path))
    result = tool.search('GeTe', top_k=1)
    papers = tool.to_papers(result.hits)
    assert len(papers) == 1
    paper = papers[0]
    assert paper['doc_id'] == 'm1'
    assert paper['doi'] == '10.2/1'
    assert paper['source'] == 'scibase'
    assert paper['chunk']  # 证据片段
    assert paper['score'] is not None


def test_search_papers_convenience(tmp_path):
    """search_papers 便捷接口直接返回论文结构。"""
    tool = RagRetrievalTool(index_path=_build_index(tmp_path))
    papers = tool.search_papers('thermoelectric', top_k=2)
    assert len(papers) == 2
    assert all(p['source'] == 'scibase' for p in papers)


def test_available_flag(tmp_path):
    """available 反映索引是否加载成功。"""
    assert RagRetrievalTool(index_path=_build_index(tmp_path)).available is True
    assert RagRetrievalTool(index_path=tmp_path / 'no.json').available is False

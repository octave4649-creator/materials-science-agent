"""生物材料知识抽取 Agent 单测。

mock llm_available / llm_chat_json / model_name，避免真实网络调用
（exp.md 经验 30：外部依赖一律注入/mock，CI 不依赖网络）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.extraction.schemas import SourceRef
from src.proteome.bio_extraction import (
    RESPONSE_KEYWORDS,
    STRAINS,
    BioCondition,
    BioExtractionAgent,
    BioKnowledgeBase,
    BioKnowledgeEntry,
    BioResponse,
    ProteinFamilyEntry,
    _entry_key,
)

# ---------- Schema 测试 ----------


def test_bio_condition_strain_normalizes_case():
    """菌株名大写归一化。"""
    c = BioCondition(strain='bai')
    assert c.strain == 'BAI'


def test_bio_condition_strain_invalid_keeps_uppercase():
    """非法菌株名大写归一化后保留（加载层宽容进，校验留给下游）。"""
    c = BioCondition(strain='not_a_strain')
    assert c.strain == 'NOT_A_STRAIN'


def test_bio_condition_strain_none_stays_none():
    """None 菌株保持 None。"""
    c = BioCondition(strain=None)
    assert c.strain is None


def test_protein_family_entry_coerce_none_genes():
    """genes=null 容忍为空列表。"""
    pf = ProteinFamilyEntry(family='hsp', genes=None)  # type: ignore[arg-type]
    assert pf.genes == []


def test_bio_knowledge_entry_from_dict_roundtrip():
    """from_dict / to_dict 往返一致。"""
    data = {
        'condition': {'strain': 'BAI', 'temperature': '37°C', 'carbon_source': 'glucose'},
        'protein_families': [
            {'family': 'hsp', 'genes': ['HSP26', 'HSP82'], 'response': 'up'}
        ],
        'response': {'direction': 'heat_shock', 'description': '热休克响应', 'phenotype': '耐热'},
        'source': {'doi': '10.1000/x', 'doc_id': 'd1'},
        'confidence': 0.9,
    }
    entry = BioKnowledgeEntry.from_dict(data)
    assert entry.condition.strain == 'BAI'
    assert entry.protein_families[0].genes == ['HSP26', 'HSP82']
    assert entry.response.direction == 'heat_shock'
    out = entry.to_dict()
    assert out['condition']['strain'] == 'BAI'
    assert out['confidence'] == 0.9


def test_bio_knowledge_entry_coerce_none_subobjects():
    """condition/response/source=null 容忍为默认对象。"""
    entry = BioKnowledgeEntry(condition=None, response=None, source=None)  # type: ignore[arg-type]
    assert entry.condition.strain is None
    assert entry.response.direction == 'other'


# ---------- BioKnowledgeBase 测试 ----------


def _make_entry(
    strain: str | None = 'BAI',
    direction: str = 'heat_shock',
    doc_id: str = 'd1',
) -> BioKnowledgeEntry:
    return BioKnowledgeEntry(
        condition=BioCondition(strain=strain, temperature='37°C'),
        protein_families=[
            ProteinFamilyEntry(family='hsp', genes=['HSP26'], response='up')
        ],
        response=BioResponse(direction=direction, description='test'),
        source=SourceRef(doc_id=doc_id),
        confidence=0.8,
    )


def test_kb_add_entry_new(tmp_path: Path):
    """新条目直接添加。"""
    kb = BioKnowledgeBase(path=tmp_path / 'kb.json')
    entry = _make_entry()
    kb.add_entry(entry, evidence_id='d1')
    assert len(kb.entries) == 1
    assert kb.entries[0].source.doc_id == 'd1'


def test_kb_add_entry_merge_same_key(tmp_path: Path):
    """相同 condition+response 合并证据、蛋白家族并集。"""
    kb = BioKnowledgeBase(path=tmp_path / 'kb.json')
    e1 = _make_entry(doc_id='d1')
    e1.protein_families = [ProteinFamilyEntry(family='hsp', genes=['HSP26'])]
    e2 = _make_entry(doc_id='d2')
    e2.protein_families = [ProteinFamilyEntry(family='metabolic', genes=['GAL1'])]
    kb.add_entry(e1, evidence_id='d1')
    kb.add_entry(e2, evidence_id='d2')
    assert len(kb.entries) == 1  # 合并
    families = {pf.family for pf in kb.entries[0].protein_families}
    assert families == {'hsp', 'metabolic'}
    assert 'd2' in (kb.entries[0].source.doc_id or '')


def test_kb_add_entry_different_key_not_merged(tmp_path: Path):
    """不同响应方向不合并。"""
    kb = BioKnowledgeBase(path=tmp_path / 'kb.json')
    kb.add_entry(_make_entry(direction='heat_shock'), evidence_id='d1')
    kb.add_entry(_make_entry(direction='metabolic_switch'), evidence_id='d2')
    assert len(kb.entries) == 2


def test_kb_save_load_roundtrip(tmp_path: Path):
    """落盘后重新加载一致。"""
    path = tmp_path / 'kb.json'
    kb = BioKnowledgeBase(path=path)
    kb.add_entry(_make_entry(), evidence_id='d1')
    kb.save()
    assert path.exists()
    kb2 = BioKnowledgeBase(path=path)
    assert len(kb2.entries) == 1
    assert kb2.entries[0].condition.strain == 'BAI'


def test_kb_load_invalid_json_returns_empty(tmp_path: Path):
    """损坏的 JSON 文件加载返回空。"""
    path = tmp_path / 'kb.json'
    path.write_text('not a json', encoding='utf-8')
    kb = BioKnowledgeBase(path=path)
    assert kb.entries == []


def test_kb_stats(tmp_path: Path):
    """stats 统计家族/方向分布。"""
    kb = BioKnowledgeBase(path=tmp_path / 'kb.json')
    kb.add_entry(_make_entry(direction='heat_shock'), evidence_id='d1')
    kb.add_entry(_make_entry(direction='metabolic_switch'), evidence_id='d2')
    s = kb.stats()
    assert s['n_entries'] == 2
    assert s['direction_distribution'] == {'heat_shock': 1, 'metabolic_switch': 1}


def test_entry_key_distinguishes_conditions():
    """不同条件产生不同 key。"""
    e1 = _make_entry(strain='BAI')
    e2 = _make_entry(strain='BAH')
    assert _entry_key(e1) != _entry_key(e2)


# ---------- BioExtractionAgent 测试 ----------


def _make_paper(
    chunk: str, doc_id: str = 'd1', doi: str = '10.1000/x', page_no: int = 5
) -> dict[str, Any]:
    return {
        'chunk': chunk,
        'doc_id': doc_id,
        'doi': doi,
        'page_no': page_no,
        'title': 'Test Paper',
    }


@pytest.fixture
def no_llm(monkeypatch):
    """禁用 LLM，强制走规则式。"""
    monkeypatch.setattr(
        'src.proteome.bio_extraction.llm_available', lambda: False
    )
    monkeypatch.setattr('src.proteome.bio_extraction.model_name', lambda: None)


@pytest.fixture
def fake_llm(monkeypatch):
    """启用 LLM，llm_chat_json 返回预设 dict（通过 _fake_chat 工厂控制）。"""
    monkeypatch.setattr('src.proteome.bio_extraction.llm_available', lambda: True)
    monkeypatch.setattr(
        'src.proteome.bio_extraction.model_name', lambda: 'test-model'
    )

    def _install(return_value: dict[str, Any] | Exception):
        if isinstance(return_value, Exception):
            def _raise(*a, **kw):
                raise return_value
            monkeypatch.setattr('src.proteome.bio_extraction.llm_chat_json', _raise)
        else:
            monkeypatch.setattr(
                'src.proteome.bio_extraction.llm_chat_json',
                lambda *a, **kw: return_value,
            )

    return _install


def test_run_extracts_with_llm(fake_llm, tmp_path: Path):
    """LLM 抽取成功，落库。"""
    chunk = 'BAI strain at 37°C shows HSP26 upregulation under heat shock.'
    fake_llm(
        {
            'condition': {
                'strain': 'BAI',
                'temperature': '37°C',
                'carbon_source': None,
            },
            'protein_families': [
                {'family': 'hsp', 'genes': ['HSP26'], 'response': 'up'}
            ],
            'response': {
                'direction': 'heat_shock',
                'description': '热休克响应',
                'phenotype': None,
            },
            'confidence': 0.9,
        }
    )
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run({'papers': [_make_paper(chunk)]})
    assert result.stats.n_llm == 1
    assert result.stats.n_rule == 0
    assert len(result.knowledge_base.entries) == 1
    assert result.knowledge_base.entries[0].condition.strain == 'BAI'
    assert result.knowledge_base.entries[0].source.doc_id == 'd1'
    assert result.knowledge_base.entries[0].source.doi == '10.1000/x'


def test_run_llm_failure_degrades_to_rule(fake_llm, tmp_path: Path):
    """LLM 抛异常，降级规则式抽取。"""
    chunk = 'BAI strain grown on glucose shows GAL1 expression changes.'
    fake_llm(RuntimeError('mock llm boom'))
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run({'papers': [_make_paper(chunk)]})
    assert result.stats.n_rule == 1
    assert result.stats.n_llm == 0
    assert len(result.knowledge_base.entries) == 1
    # 规则式抽取置信度固定 0.5
    assert result.knowledge_base.entries[0].confidence == 0.5


def test_run_no_llm_uses_rule(no_llm, tmp_path: Path):
    """无 LLM 时走规则式。"""
    chunk = 'BAH strain at 30°C on galactose, HSP82 expression observed.'
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run({'papers': [_make_paper(chunk)]})
    assert result.stats.n_rule == 1
    assert result.stats.n_llm == 0
    assert len(result.knowledge_base.entries) == 1
    assert result.knowledge_base.entries[0].condition.strain == 'BAH'


def test_run_empty_chunk_skipped(no_llm, tmp_path: Path):
    """空 chunk 跳过。"""
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run({'papers': [_make_paper('')]})
    assert result.stats.n_entries == 0
    assert len(result.knowledge_base.entries) == 0


def test_run_verify_fail_drops_hallucination(fake_llm, tmp_path: Path):
    """LLM 编造菌株（原文不含），回查失败丢弃。"""
    chunk = 'This paper discusses general yeast biology concepts.'  # 无菌株/基因/关键词
    fake_llm(
        {
            'condition': {'strain': 'BAI', 'temperature': None, 'carbon_source': None},
            'protein_families': [
                {'family': 'hsp', 'genes': ['HSP26'], 'response': 'up'}
            ],
            'response': {'direction': 'other', 'description': 'fake'},
            'confidence': 0.8,
        }
    )
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run({'papers': [_make_paper(chunk)]})
    assert result.stats.n_verify_fail == 1
    assert len(result.knowledge_base.entries) == 0


def test_run_verify_pass_by_gene(fake_llm, tmp_path: Path):
    """原文含基因名（但不含菌株），回查通过。"""
    chunk = 'GAL1 expression increases during carbon source switch.'
    fake_llm(
        {
            'condition': {'strain': None, 'carbon_source': 'galactose'},
            'protein_families': [
                {'family': 'metabolic', 'genes': ['GAL1'], 'response': 'up'}
            ],
            'response': {'direction': 'metabolic_switch', 'description': ' GAL 诱导'},
            'confidence': 0.85,
        }
    )
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run({'papers': [_make_paper(chunk)]})
    assert len(result.knowledge_base.entries) == 1


def test_run_verify_pass_by_response_keyword(fake_llm, tmp_path: Path):
    """原文含响应关键词（无菌株无基因），回查通过。"""
    chunk = 'Cells exposed to hydrogen peroxide show oxidative damage.'
    fake_llm(
        {
            'condition': {'strain': None},
            'protein_families': [],
            'response': {'direction': 'oxidative_stress', 'description': '氧化应激'},
            'confidence': 0.7,
        }
    )
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run({'papers': [_make_paper(chunk)]})
    assert len(result.knowledge_base.entries) == 1


def test_rule_extract_no_strain_no_gene_returns_none(no_llm, tmp_path: Path):
    """规则式：无菌株无基因返回 None。"""
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    entry = agent._rule_extract('general text about biology', doc_id='d1')
    assert entry is None


def test_rule_extract_matches_strain_and_gene(no_llm, tmp_path: Path):
    """规则式：匹配菌株+基因+温度+碳源。"""
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    text = 'BAI strain at 37°C on galactose medium, HSP26 and GAL1 detected.'
    entry = agent._rule_extract(text, doc_id='d1')
    assert entry is not None
    assert entry.condition.strain == 'BAI'
    assert entry.condition.temperature == '37°C'
    assert entry.condition.carbon_source == 'galactose'
    families = {pf.family for pf in entry.protein_families}
    assert 'hsp' in families
    assert 'metabolic' in families


def test_rule_extract_direction_from_keywords(no_llm, tmp_path: Path):
    """规则式：响应方向从关键词推断。"""
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    text = 'DHY210 strain under heat shock conditions, HSP82 upregulated.'
    entry = agent._rule_extract(text, doc_id='d1')
    assert entry is not None
    assert entry.response.direction == 'heat_shock'


def test_run_loads_from_json_file(no_llm, tmp_path: Path):
    """run 接受 JSON 文件路径。"""
    chunk = 'CEK strain glucose medium SOD1 expression.'
    retrieval = {
        'papers': [_make_paper(chunk, doc_id='d9')],
    }
    path = tmp_path / 'retrieval.json'
    path.write_text(json.dumps(retrieval), encoding='utf-8')
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run(path)
    assert len(result.knowledge_base.entries) == 1
    assert result.knowledge_base.entries[0].condition.strain == 'CEK'


def test_run_merges_same_condition_across_papers(no_llm, tmp_path: Path):
    """两篇 paper 抽出相同 condition+direction，合并为一条。"""
    chunk1 = 'BAI strain heat shock HSP26.'
    chunk2 = 'BAI strain heat shock HSP82.'  # 同菌株同方向，不同基因
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run(
        {'papers': [_make_paper(chunk1, doc_id='d1'), _make_paper(chunk2, doc_id='d2')]}
    )
    # 同 key 合并
    assert len(result.knowledge_base.entries) == 1
    families = {pf.family for pf in result.knowledge_base.entries[0].protein_families}
    assert families == {'hsp'}


def test_run_stats_track_llm_and_rule(fake_llm, tmp_path: Path):
    """stats 区分 LLM 与规则式条数。"""
    chunk1 = 'BAI heat shock HSP26.'  # LLM 成功
    chunk2 = 'CGD metabolic GAL1.'  # LLM 成功
    fake_llm(
        {
            'condition': {'strain': 'BAI'},
            'protein_families': [{'family': 'hsp', 'genes': ['HSP26']}],
            'response': {'direction': 'heat_shock', 'description': ''},
            'confidence': 0.8,
        }
    )
    agent = BioExtractionAgent(kb_path=tmp_path / 'kb.json')
    result = agent.run(
        {'papers': [_make_paper(chunk1, doc_id='d1'), _make_paper(chunk2, doc_id='d2')]}
    )
    assert result.stats.n_llm == 2
    assert result.stats.n_papers == 2


def test_strains_constant_complete():
    """STRAINS 常量含 5 种菌株。"""
    assert set(STRAINS) == {'BAI', 'BAH', 'DHY210', 'CEK', 'CGD'}


def test_response_keywords_cover_five_directions():
    """RESPONSE_KEYWORDS 覆盖 5 个核心方向。"""
    expected = {
        'heat_shock',
        'metabolic_switch',
        'oxidative_stress',
        'dna_damage',
        'chemical_perturbation',
    }
    assert expected.issubset(set(RESPONSE_KEYWORDS.keys()))

"""证据链数据结构单测：序列化往返。"""
from src.retrieval.evidence import EvidenceChain, EvidenceItem


def test_evidence_item_roundtrip() -> None:
    """EvidenceItem 序列化 → 反序列化后内容一致。"""
    item = EvidenceItem(
        source="sciverse", doc_id="abc", text="evidence", page="3", score=0.9
    )
    restored = EvidenceItem.from_dict(item.to_dict())
    assert restored == item
    assert restored.source == "sciverse"
    assert restored.page == "3"


def test_evidence_item_ignores_unknown_keys() -> None:
    """反序列化时未知字段被忽略，不抛错。"""
    item = EvidenceItem.from_dict({"source": "mp", "doc_id": "m1", "bogus": 1})
    assert item.source == "mp"
    assert item.doc_id == "m1"


def test_evidence_chain_roundtrip() -> None:
    """EvidenceChain 多证据往返。"""
    chain = EvidenceChain(conclusion="结论")
    chain.add(EvidenceItem(source="sciverse", doc_id="d1", text="t1"))
    chain.add(EvidenceItem(source="mp", doc_id="m1", text="t2"))
    chain.validated = True
    restored = EvidenceChain.from_dict(chain.to_dict())
    assert restored.conclusion == "结论"
    assert restored.validated is True
    assert len(restored.items) == 2
    assert restored.items[1].source == "mp"
    assert restored.items[1].doc_id == "m1"

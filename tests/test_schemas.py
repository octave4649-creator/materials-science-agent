"""Schema 测试：序列化往返、非法字段忽略。"""
from __future__ import annotations

from src.extraction.schemas import (
    ExtractionRecord,
    KnowledgeEntry,
    Material,
    PropertyEntry,
)


def test_record_roundtrip() -> None:
    """抽取记录序列化往返一致。"""
    rec = ExtractionRecord(
        material=Material(formula="Ge0.93Ti0.01Bi0.06Te", structure={"space_group": "Fm-3m"}),
        properties=[PropertyEntry(name="zT", value=1.6, unit="", condition="623K")],
    )
    d = rec.to_dict()
    back = ExtractionRecord.from_dict(d)
    assert back.material.formula == "Ge0.93Ti0.01Bi0.06Te"
    assert back.material.structure.space_group == "Fm-3m"
    assert back.properties[0].value == 1.6


def test_record_ignores_unknown_fields() -> None:
    """反序列化自动忽略未知字段。"""
    d = {"material": {"formula": "Bi2Te3"}, "fake_field": "x"}
    rec = ExtractionRecord.from_dict(d)
    assert rec.material.formula == "Bi2Te3"


def test_record_defaults() -> None:
    """缺省字段自动补默认值。"""
    rec = ExtractionRecord.from_dict({"material": {"formula": "PbTe"}})
    assert rec.properties == []
    assert rec.synthesis.temperature is None
    assert rec.confidence is None


def test_knowledge_entry_roundtrip() -> None:
    """知识库条目往返。"""
    entry = KnowledgeEntry(
        record=ExtractionRecord(material=Material(formula="PbTe")),
        evidence_ids=["doc:abc"],
        normalized_formula="PbTe",
    )
    back = KnowledgeEntry.model_validate(entry.model_dump())
    assert back.evidence_ids == ["doc:abc"]
    assert back.merged is False

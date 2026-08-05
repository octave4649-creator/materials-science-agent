"""抽取 Schema 容错测试：LLM 按提示词「未提及字段填 null」时不被静默丢弃。

对齐 `.trae/rules/04-literature-agent.md` 第 3 节 schema 规范：
LLM 输出必须经 schema 校验后方可入库，但校验应容忍合法的 null/缺省形态，
否则整条记录被丢弃（历史 bug：知识库仅剩规则式条目）。
"""
from __future__ import annotations

import pytest

from src.agent.extraction_agent import ExtractionAgent
from src.extraction.schemas import ExtractionRecord


def _llm_raw() -> dict:
    """LLM 典型输出：未提及字段填 null，方法类型非标准（THEORETICAL）。"""
    return {
        "material": {"formula": "PbTe", "composition": None, "structure": None},
        "properties": [
            {
                "name": "figure of merit",
                "value": 1.4,
                "unit": None,
                "condition": "750K",
            }
        ],
        "methods": [{"type": "THEORETICAL", "software": None, "key_params": None}],
        "synthesis": None,
        "source": {"doi": "10.1063/1.4892653", "page": None, "paragraph": "Abstract"},
        "confidence": 0.6,
    }


def test_llm_null_tolerance_parse() -> None:
    """structure/synthesis 为 null、method type 非标准 → 仍可解析为记录。"""
    rec = ExtractionRecord.from_dict(_llm_raw())
    assert rec.material.formula == "PbTe"
    assert rec.material.structure.space_group is None  # null → 默认空结构
    assert rec.properties[0].value == 1.4
    assert rec.methods[0].type == "OTHER"  # THEORETICAL → OTHER
    assert rec.synthesis.temperature is None  # null → 默认空合成信息


def test_parse_llm_output_no_longer_drops() -> None:
    """回归：此前 structure:null 导致 _parse_llm_output 返回 None（静默丢弃）。"""
    rec = ExtractionAgent()._parse_llm_output(
        _llm_raw(), doc_id="d1", doi="10.1063/1.4892653", page=None
    )
    assert rec is not None
    assert rec.material.formula == "PbTe"
    assert rec.source.doc_id == "d1"


def test_properties_null_coerced() -> None:
    """properties: null（而非 []）→ 空列表，不抛异常。"""
    raw = {"material": {"formula": "Bi2Te3", "structure": None}, "properties": None}
    rec = ExtractionRecord.from_dict(raw)
    assert rec.properties == []
    assert rec.material.formula == "Bi2Te3"


def test_material_formula_required() -> None:
    """formula 缺失（null）仍视为非法记录（无公式则无合并键）。"""
    raw = {"material": {"formula": None, "structure": {}}, "properties": []}
    with pytest.raises(Exception):
        ExtractionRecord.from_dict(raw)

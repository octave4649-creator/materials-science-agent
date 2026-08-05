"""材料知识抽取 Schema（五段式）。

与赛题知识抽取要求（成分/结构/性能/方法/条件）一一对应，
对齐 `.trae/rules/04-literature-agent.md` 第 3 节 schema 规范。
pydantic 模型既用于 LLM 输出校验，也用于知识库落库与查询。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# 方法类型枚举：DFT / MD / ML / EXPERIMENT / OTHER
MethodType = Literal["DFT", "MD", "ML", "EXPERIMENT", "OTHER"]


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MaterialStructure(BaseModel):
    """晶体结构描述。"""

    space_group: str | None = Field(default=None, description="空间群（如 Fm-3m）")
    lattice: str | None = Field(default=None, description="晶格参数（如 a=4.05 Å）")
    phase: str | None = Field(default=None, description="相（如 cubic / rhombohedral）")


class Material(BaseModel):
    """材料成分与结构。"""

    formula: str = Field(description="化学式（归一化后，如 Ge0.93Ti0.01Bi0.06Te）")
    composition: str | None = Field(default=None, description="组成描述（如 元素/掺杂描述）")
    structure: MaterialStructure = Field(default_factory=MaterialStructure)

    @field_validator("structure", mode="before")
    @classmethod
    def _coerce_structure(cls, v: Any) -> Any:
        """LLM 按提示词要求「未提及字段填 null」时，容忍 structure: null。"""
        return {} if v is None else v


class PropertyEntry(BaseModel):
    """一条材料性能记录。"""

    name: str = Field(description="性能名（如 zT / band gap / Seebeck coefficient）")
    value: float | None = Field(default=None, description="数值")
    unit: str | None = Field(default=None, description="单位（如 K / eV / S/cm）")
    condition: str | None = Field(default=None, description="条件（如 623K / 5% doping）")


class MethodEntry(BaseModel):
    """一条模拟/实验方法记录。"""

    type: MethodType = Field(description="方法类型：DFT / MD / ML / EXPERIMENT")
    software: str | None = Field(default=None, description="软件（如 VASP / GGA-PBE）")
    key_params: str | None = Field(default=None, description="关键参数（如 500eV cutoff）")

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> str:
        """LLM 常见非标准方法类型（THEORETICAL/COMPUTATIONAL 等）统一归为 OTHER。"""
        return v if isinstance(v, str) and v in MethodType.__args__ else "OTHER"


class SynthesisInfo(BaseModel):
    """合成条件。"""

    precursors: str | None = Field(default=None, description="前驱体")
    temperature: str | None = Field(default=None, description="温度（如 800°C）")
    atmosphere: str | None = Field(default=None, description="气氛（如 Ar）")
    duration: str | None = Field(default=None, description="时间（如 4h）")


class SourceRef(BaseModel):
    """证据来源定位（防幻觉三件套之一：每字段可溯源）。"""

    doi: str | None = Field(default=None, description="DOI")
    page: str | None = Field(default=None, description="页码或段落定位")
    paragraph: str | None = Field(default=None, description="段落号/标题")
    doc_id: str | None = Field(default=None, description="全文哈希 ID（Sciverse doc_id）")


class ExtractionRecord(BaseModel):
    """单篇文献单材料体系的抽取记录（材料知识四元组 + 来源）。"""

    material: Material
    properties: list[PropertyEntry] = Field(default_factory=list)
    methods: list[MethodEntry] = Field(default_factory=list)
    synthesis: SynthesisInfo = Field(default_factory=SynthesisInfo)
    source: SourceRef = Field(default_factory=SourceRef)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="抽取置信度 0-1")
    extracted_at: str = Field(default_factory=_utc_now)

    @field_validator("properties", "methods", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> Any:
        """LLM 填 null 而非空数组时按空列表处理（提示词要求两者皆可）。"""
        return [] if v is None else v

    @field_validator("synthesis", mode="before")
    @classmethod
    def _coerce_synthesis(cls, v: Any) -> Any:
        """容忍 synthesis: null（未提及合成条件）。"""
        return {} if v is None else v

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容 dict（pydantic 直接 model_dump）。"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractionRecord":
        """从 dict 反序列化，非法字段自动忽略。"""
        return cls.model_validate(data)


class KnowledgeEntry(BaseModel):
    """知识库条目：归一化后的材料知识，含证据链信息。

    供 Gap 识别（模块 3）与路线 A 候选生成直接消费。
    """

    record: ExtractionRecord
    evidence_ids: list[str] = Field(default_factory=list, description="证据 ID 列表（doc_id）")
    normalized_formula: str = Field(default="", description="归一化化学式（去重键）")
    merged: bool = Field(default=False, description="是否已与同体系记录合并")

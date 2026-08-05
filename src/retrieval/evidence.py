"""证据链数据结构：EvidenceItem / EvidenceChain。

证据链是赛题红线「结论必须有据可溯」的载体（00-project-rules.md 4.2）。
所有检索 / 抽取 / 分析结果都必须附带 EvidenceChain 后才可入库或输出。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class EvidenceItem:
    """单条证据：一条检索/解析/查询记录的最小可审计单元。"""

    source: str  # 来源（sciverse / mp / oqmd / mineru）
    doc_id: str  # 文档/记录 ID（如 DOI、material_id）
    text: str = ""  # 证据原文片段
    page: str | None = None  # 页码或段落定位
    score: float | None = None  # 检索相关度（可选）
    fetched_at: str = field(default_factory=_utc_now)  # 获取时间

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容 dict，用于落库与审计。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceItem":
        """从 dict 反序列化，自动忽略未知字段。"""
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


@dataclass
class EvidenceChain:
    """证据链：一个结论的全部证据。"""

    conclusion: str  # 结论陈述（如：检索到的候选文献清单）
    items: list[EvidenceItem] = field(default_factory=list)
    validated: bool = False  # 是否经数据库/人工验证
    created_at: str = field(default_factory=_utc_now)

    def add(self, item: EvidenceItem) -> None:
        """追加一条证据。"""
        self.items.append(item)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容 dict。"""
        return {
            "conclusion": self.conclusion,
            "items": [i.to_dict() for i in self.items],
            "validated": self.validated,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceChain":
        """从 dict 反序列化。"""
        chain = cls(
            conclusion=data.get("conclusion", ""),
            validated=data.get("validated", False),
            created_at=data.get("created_at", _utc_now()),
        )
        chain.items = [EvidenceItem.from_dict(i) for i in data.get("items", [])]
        return chain

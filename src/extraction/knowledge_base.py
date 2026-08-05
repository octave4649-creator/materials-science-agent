"""知识库：抽取记录落库（JSON）与查询。

供模块 3（Gap 识别）与路线 A（候选生成）直接消费。
存储格式：JSON 数组（KnowledgeEntry），含证据关联（evidence_ids 回链证据链）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.common.config import DATA_DIR
from src.extraction.extractor import normalize_formula
from src.extraction.schemas import ExtractionRecord, KnowledgeEntry

DEFAULT_KB_PATH = DATA_DIR / "knowledge_base.json"


class KnowledgeBase:
    """材料知识库（JSON 存储）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        """初始化。

        参数:
            path: 存储路径（默认 data/knowledge_base.json）
        """
        self.path = Path(path) if path else DEFAULT_KB_PATH
        self.entries: list[KnowledgeEntry] = []
        if self.path.is_file():
            self._load()

    # ---------- 写入 ----------

    def add_record(
        self, record: ExtractionRecord, *, evidence_id: str | None = None
    ) -> KnowledgeEntry:
        """添加一条抽取记录：同 formula 记录合并证据，异 formula 新增条目。

        参数:
            record: 抽取记录
            evidence_id: 证据 ID（doc_id），回链证据链

        返回:
            新增/更新的知识库条目。
        """
        key = normalize_formula(record.material.formula) or record.material.formula
        for entry in self.entries:
            if entry.normalized_formula == key:
                # 同体系合并：属性/方法并集 + 证据回链
                self._merge_entry(entry, record, evidence_id)
                return entry
        entry = KnowledgeEntry(
            record=record,
            evidence_ids=[evidence_id] if evidence_id else [],
            normalized_formula=key,
        )
        self.entries.append(entry)
        return entry

    @staticmethod
    def _merge_entry(
        entry: KnowledgeEntry, record: ExtractionRecord, evidence_id: str | None
    ) -> None:
        """将新记录合并进已有条目（属性/方法并集、缺失字段补齐）。"""
        target = entry.record
        existing = {(p.name, p.value) for p in target.properties}
        for p in record.properties:
            if (p.name, p.value) not in existing:
                target.properties.append(p)
        existing_m = {(m.type, m.software) for m in target.methods}
        for m in record.methods:
            if (m.type, m.software) not in existing_m:
                target.methods.append(m)
        if not target.synthesis.temperature and record.synthesis.temperature:
            target.synthesis.temperature = record.synthesis.temperature
        if (record.confidence or 0) > (target.confidence or 0):
            target.confidence = record.confidence
        if evidence_id and evidence_id not in entry.evidence_ids:
            entry.evidence_ids.append(evidence_id)
        entry.merged = len(entry.evidence_ids) > 1 or entry.merged

    def save(self) -> None:
        """落盘到 JSON。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [e.model_dump() for e in self.entries]
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load(self) -> None:
        """从 JSON 加载。"""
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = [KnowledgeEntry.model_validate(e) for e in payload]
        except (OSError, json.JSONDecodeError, ValueError):
            self.entries = []

    # ---------- 查询 ----------

    def query_by_formula(self, formula: str) -> list[KnowledgeEntry]:
        """按化学式查询（归一化后精确匹配）。"""
        key = normalize_formula(formula)
        return [e for e in self.entries if e.normalized_formula == key]

    def query_by_element(self, element: str) -> list[KnowledgeEntry]:
        """按元素查询（化学式包含指定元素）。"""
        return [e for e in self.entries if element.lower() in e.normalized_formula.lower()]

    def stats(self) -> dict[str, Any]:
        """知识库统计：条目数、体系数、证据总数、性能类型分布。"""
        n_props: dict[str, int] = {}
        for e in self.entries:
            for p in e.record.properties:
                n_props[p.name] = n_props.get(p.name, 0) + 1
        return {
            "n_entries": len(self.entries),
            "n_evidence_ids": sum(len(e.evidence_ids) for e in self.entries),
            "property_types": n_props,
            "path": str(self.path),
        }

    def to_dict(self) -> dict[str, Any]:
        """完整导出（审计/评测用）。"""
        return {
            "entries": [e.model_dump() for e in self.entries],
            "stats": self.stats(),
        }

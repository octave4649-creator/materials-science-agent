"""调研报告 Schema（模块 4 输出）。

章节结构对齐 `.trae/rules/04-literature-agent.md` 第 5.1 节模板：
研究问题与范围 / 检索策略 / 知识抽取 / Gap 清单 / 文献综述 / 结论建议 / 附录。
每条结论带引用编号 [n]，回链参考文献（证据链强制，00-project-rules.md 4.1）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# 报告章节键（顺序即报告顺序，对齐模板）
SECTION_ORDER = [
    "abstract",      # 摘要
    "scope",         # 1. 研究问题与范围
    "method",        # 2. 检索策略与数据来源
    "extraction",    # 3. 知识抽取结果
    "gaps",          # 4. Research Gap 清单
    "review",        # 5. 文献综述
    "validation",    # 6. 数据库交叉验证（模块 6 产物）
    "conclusion",    # 7. 结论与建议
    "references",    # 参考文献
    "appendix",      # 附录：文献清单
]

# 章节默认标题
SECTION_TITLES = {
    "abstract": "摘要",
    "scope": "1. 研究问题与范围",
    "method": "2. 检索策略与数据来源",
    "extraction": "3. 知识抽取结果",
    "gaps": "4. Research Gap 清单",
    "review": "5. 文献综述",
    "validation": "6. 数据库交叉验证",
    "conclusion": "7. 结论与建议",
    "references": "参考文献",
    "appendix": "附录：文献清单",
}


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReportSection(BaseModel):
    """一个报告章节。

    属性:
        key: 章节键（SECTION_ORDER 之一）
        title: 章节标题（如「1. 研究问题与范围」）
        content: Markdown 正文
        refs: 本章节引用的参考文献编号 [n] 列表
    """

    key: str = Field(description="章节键")
    title: str = Field(description="章节标题")
    content: str = Field(default="", description="Markdown 正文")
    refs: list[int] = Field(default_factory=list, description="引用编号列表")


class ReportMeta(BaseModel):
    """报告元信息（版本快照，可复现）。"""

    domain: str = Field(default="materials", description="调研领域")
    question: str | None = Field(default=None, description="研究问题")
    n_papers: int = Field(default=0, description="检索文献数")
    n_kb_entries: int = Field(default=0, description="知识库条目数")
    n_gaps: int = Field(default=0, description="Gap 数")
    input_hashes: dict[str, str] = Field(
        default_factory=dict, description="输入文件 sha256 快照"
    )
    llm_abstract: bool = Field(default=False, description="摘要是否 LLM 生成")
    self_check: dict[str, bool] = Field(
        default_factory=dict, description="结构化自检结果"
    )


class ReportDocument(BaseModel):
    """完整调研报告。

    属性:
        title: 报告标题
        sections: 章节列表（顺序按 SECTION_ORDER）
        meta: 元信息（版本快照）
        generated_at: 生成时间（UTC ISO）
    """

    title: str = Field(default="文献调研报告", description="报告标题")
    sections: list[ReportSection] = Field(default_factory=list)
    meta: ReportMeta = Field(default_factory=ReportMeta)
    generated_at: str = Field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（落盘/审计）。"""
        return self.model_dump()

    def section_map(self) -> dict[str, ReportSection]:
        """章节键 → 章节（快速查找）。"""
        return {s.key: s for s in self.sections}

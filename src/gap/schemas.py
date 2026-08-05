"""Research Gap 数据结构（模块 3 输出）。

Gap 类型对齐 `.trae/rules/04-literature-agent.md` 第 4.1 节：
未探索方向 / 矛盾结论 / 缺失知识连接 / 方法空白。
每个 Gap 必须带证据链（evidence_ids 回链知识库 doc_id）与新颖性判定。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# Gap 类型（对齐规则文件第 4.1 节）
GapType = Literal["未探索方向", "矛盾结论", "缺失知识连接", "方法空白"]
# 新颖性判定：区分「新知」与「已知」（赛题评估要点）
Novelty = Literal["已知", "部分已知", "新知"]


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GapCandidate(BaseModel):
    """一条 Research Gap。

    属性:
        gap_type: Gap 类型（未探索方向/矛盾结论/缺失知识连接/方法空白）
        statement: Gap 描述（可证伪的科学陈述）
        rationale: 科学解释/依据（为什么是 Gap）
        formulas: 相关材料体系（归一化化学式）
        evidence_ids: 证据链（知识库 doc_id 回链），禁止无证据 Gap
        novelty: 新颖性（已知/部分已知/新知）
        operability: 可操作性（能否转化为路线 A 搜索种子）
        confidence: 置信度 0-1
        source: 产生方式（coverage / contradiction / llm）
    """

    gap_type: GapType = Field(description="Gap 类型")
    statement: str = Field(description="Gap 描述（可证伪科学陈述）")
    rationale: str | None = Field(default=None, description="科学解释/依据")
    formulas: list[str] = Field(default_factory=list, description="相关材料体系")
    evidence_ids: list[str] = Field(default_factory=list, description="证据 doc_id 回链")
    novelty: Novelty = Field(default="部分已知", description="新颖性判定")
    operability: str | None = Field(default=None, description="可操作性说明")
    verification: str | None = Field(
        default=None, description="新颖性验证说明（Sciverse 回查结果摘要）"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度")
    source: str = Field(default="coverage", description="产生方式")

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（落盘/审计）。"""
        return self.model_dump()


class GapReport(BaseModel):
    """Gap 识别结果：Gap 清单 + 统计。

    属性:
        domain: 调研领域（如 thermoelectric）
        n_entries: 输入知识库条目数
        gaps: Gap 清单
        generated_at: 生成时间（UTC ISO）
    """

    domain: str = Field(default="materials", description="调研领域")
    n_entries: int = Field(default=0, description="输入知识库条目数")
    gaps: list[GapCandidate] = Field(default_factory=list, description="Gap 清单")
    generated_at: str = Field(default_factory=_utc_now, description="生成时间")

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（落盘/审计）。"""
        return self.model_dump()

    def stats(self) -> dict[str, int]:
        """Gap 统计：按类型与新颖性分布（评测用）。"""
        by_type: dict[str, int] = {}
        by_novelty: dict[str, int] = {}
        for g in self.gaps:
            by_type[g.gap_type] = by_type.get(g.gap_type, 0) + 1
            by_novelty[g.novelty] = by_novelty.get(g.novelty, 0) + 1
        return {"n_gaps": len(self.gaps), "by_type": by_type, "by_novelty": by_novelty}

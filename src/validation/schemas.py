"""模块 6 数据库交叉验证 Schema。

对齐 `.trae/rules/03-materials-databases.md` 第 7 节交叉验证流程：
文献抽取 → 数据库查询 → 一致性检查 → 新颖性判断 → 证据链记录。
三类判定：已知（与库一致）/ 新知（库中无/超出已知）/ 反例（矛盾，负结果也入库）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# 判定类型：已知 / 新知 / 反例 / 验证失败
VerdictType = Literal["已知", "新知", "反例", "验证失败"]

# 数据库标识（主库 oqmd/mp；可选增强 nomad/aflow，见 nomad_client/aflow_client）
DatabaseId = Literal["oqmd", "mp", "nomad", "aflow"]


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DBEntry(BaseModel):
    """数据库单条记录（归一化字段）。"""

    db: DatabaseId = Field(description="来源数据库（oqmd / mp）")
    formula: str = Field(description="库中公式（如 PbTe）")
    entry_id: str | None = Field(default=None, description="库条目 ID")
    delta_e: float | None = Field(default=None, description="形成能 eV/atom（负值稳定）")
    stability: float | None = Field(default=None, description="energy above hull eV/atom")
    band_gap: float | None = Field(default=None, description="带隙 eV")
    is_stable: bool | None = Field(default=None, description="稳定性标记（按各库口径）")
    spacegroup: str | None = Field(default=None, description="晶体空间群（AFLOW 提供）")
    source_url: str | None = Field(default=None, description="可回溯链接")


class PropertyCheck(BaseModel):
    """单属性一致性检查（文献/期望 vs 数据库）。"""

    property: str = Field(description="属性名（stability / band_gap / delta_e）")
    expected: float | str | None = Field(default=None, description="文献/期望值或约束")
    db_value: float | str | None = Field(default=None, description="数据库值")
    consistent: bool = Field(description="是否一致")
    note: str = Field(default="", description="说明（如 DFT 带隙低估 30-50%）")


class VerificationResult(BaseModel):
    """单个候选的交叉验证结论。"""

    candidate_formula: str = Field(description="候选名义化学式")
    host: str = Field(description="母体（分数掺杂宿主时保留原样，证据链可回溯）")
    parent_formula: str | None = Field(
        default=None,
        description="由分数宿主解析出的整数母体（A/B 位拆分后重验用）",
    )
    dopant: str | None = Field(default=None, description="掺杂元素")
    concentration: float | None = Field(default=None, description="掺杂浓度 %")
    verdict: VerdictType = Field(description="三类判定：已知 / 新知 / 反例 / 验证失败")
    reason: str = Field(default="", description="判定理由")
    checks: list[PropertyCheck] = Field(default_factory=list)
    entries: list[DBEntry] = Field(default_factory=list, description="命中的数据库记录")
    novel_dopant: bool = Field(default=False, description="掺杂成分是否超出库中已知（潜在新知）")
    queried_at: str = Field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容 dict。"""
        return self.model_dump()

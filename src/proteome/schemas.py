"""蛋白质组学数据 Schema。

对齐 `.trae/rules/05-route-a-SPR.md` 第 6 节生物材料构效关系框架，
定义菌株、样本、特征工程中间产物等核心数据结构。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# 菌株枚举
StrainName = Literal["BAI", "BAH", "DHY210", "CEK", "CGD"]
STRAINS: tuple[str, ...] = ("BAI", "BAH", "DHY210", "CEK", "CGD")

# 温度枚举
Temperature = Literal["30", "37"]
TEMPERATURES: tuple[str, ...] = ("30", "37")

# 碳源枚举
CarbonSource = Literal["glucose", "galactose"]
CARBON_SOURCES: tuple[str, ...] = ("glucose", "galactose")

# 数据集划分
DataSplit = Literal[
    "train",
    "val_strain_only",
    "val_chem_only",
    "val_both",
    "val_time",
    "test",
]
SPLITS: tuple[str, ...] = (
    "train",
    "val_strain_only",
    "val_chem_only",
    "val_both",
    "val_time",
    "test",
)


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SampleMetadata(BaseModel):
    """样本元数据（对应 WAYB/WAYC metadata CSV 的 15 列）。

    字段对齐项目规范 5.3 节：菌株/温度/碳源/化学扰动/时间等。
    字符串字段使用 str 类型以兼容 CSV 解析（空值/未知值容错），
    严格校验由下游验证模块完成。
    """

    sample_id: str = Field(description="样本唯一 ID")
    strain: str = Field(description="酵母菌株名（如 BAI/BAH/DHY210/CEK/CGD）")
    temperature: str = Field(description="培养温度（℃，如 30/37）")
    carbon_source: str = Field(default="", description="碳源类型（glucose/galactose）")
    pert_id: str = Field(default="", description="化学扰动 ID（如 #1, #2, ... #41）")
    time_point: float = Field(default=0.0, description="时间点（小时）")
    split: str = Field(default="", description="数据集划分（train/val_*/test）")
    replicate: int = Field(default=1, description="生物学重复编号")
    extra: dict[str, Any] = Field(default_factory=dict, description="其他元数据字段（可扩展）")


class ProteomeSample(BaseModel):
    """单个蛋白质组学样本：元数据 + 表达量向量。"""

    metadata: SampleMetadata
    expression: dict[str, float] = Field(
        description="基因名 → 表达量映射（5243 维）",
    )
    n_features: int = Field(description="表达向量维度", ge=0)

    def to_vector(self, gene_order: list[str] | None = None) -> list[float]:
        """按指定基因顺序返回表达向量。

        Args:
            gene_order: 基因名列表，None 时使用 expression 的迭代顺序。

        Returns:
            表达量列表。
        """
        if gene_order is None:
            return list(self.expression.values())
        return [self.expression.get(gene, 0.0) for gene in gene_order]


class StrainCondition(BaseModel):
    """菌株-条件组合（生物材料的「材料-条件」描述符）。

    对应传统材料中的「材料 + 合成条件」概念，
    作为构效关系发现的基本搜索单元。
    字符串字段使用 str 类型以兼容 CSV 解析。
    """

    strain: str = Field(description="酵母菌株名")
    temperature: str = Field(description="培养温度（℃）")
    carbon_source: str = Field(description="碳源类型")
    pert_id: str = Field(default="", description="化学扰动 ID（对照组为空）")
    sample_ids: list[str] = Field(default_factory=list)
    n_replicates: int = Field(default=0)
    avg_expression: dict[str, float] = Field(
        default_factory=dict, description="平均表达谱（基因名 → 均值）"
    )
    std_expression: dict[str, float] = Field(
        default_factory=dict, description="表达标准差（基因名 → 标准差）"
    )


class BioFeatureDescriptor(BaseModel):
    """生物材料特征描述符（菌株-条件级别的聚合特征）。

    将 5243 维原始表达量聚合为有限维度的「材料特征」，
    供搜索算法使用（对应传统材料的成分/结构描述符）。
    """

    strain: str
    temperature: str
    carbon_source: str
    pert_id: str = ""
    # 聚合特征
    hsp_score: float = Field(default=0.0, description="热休克蛋白家族综合得分")
    metabolic_score: float = Field(default=0.0, description="代谢通路活性得分")
    oxidative_score: float = Field(default=0.0, description="氧化应激响应得分")
    dna_repair_score: float = Field(default=0.0, description="DNA 修复通路得分")
    growth_rate: float = Field(default=0.0, description="生长速率指标")
    # 差异表达特征
    diff_vs_control: dict[str, float] = Field(
        default_factory=dict,
        description="相对于对照组的差异表达倍数（基因名 → log2FC）",
    )
    feature_vector: list[float] = Field(
        default_factory=list,
        description="聚合后的特征向量（供搜索算法使用）",
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class BioCandidate(BaseModel):
    """生物材料候选（兼容搜索算法 Candidate 接口）。

    对应传统材料 Candidate（host/dopant/concentration），
    生物材料版本使用菌株+条件组合作为候选描述。
    """

    strain: str
    temperature: str
    carbon_source: str
    pert_id: str = Field(default="", description="化学扰动 ID")
    formula: str = Field(description="名义描述（如 BAI_30C_glucose_#5，用于日志和输出）")
    rationale: str = Field(default="", description="LLM 生成/评估理由（生物学解释）")
    source: str = Field(default="random", description="候选来源：llm_seed / search / random")
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="评估分数：scientific / feasibility / support",
    )
    verdict: Literal["keep", "drop", "pending"] = Field(default="pending")

    def score_avg(self) -> float:
        vals = [v for v in self.scores.values() if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ProteomeDataset(BaseModel):
    """WAYB/WAYC 完整数据集容器。"""

    samples: list[ProteomeSample] = Field(default_factory=list)
    strains: list[str] = Field(default_factory=list)
    temperatures: list[str] = Field(default_factory=list)
    carbon_sources: list[str] = Field(default_factory=list)
    perturbations: list[str] = Field(default_factory=list)
    gene_names: list[str] = Field(default_factory=list, description="基因名列表（有序）")
    n_samples: int = Field(default=0)
    created_at: str = Field(default_factory=_utc_now)

    def get_strain_conditions(self) -> list[StrainCondition]:
        """返回所有菌株-条件组合。"""
        from collections import defaultdict

        groups: dict[tuple, list[ProteomeSample]] = defaultdict(list)
        for sample in self.samples:
            key = (
                sample.metadata.strain,
                sample.metadata.temperature,
                sample.metadata.carbon_source,
                sample.metadata.pert_id,
            )
            groups[key].append(sample)

        conditions: list[StrainCondition] = []
        for (strain, temp, carbon, pert), group_samples in groups.items():
            sample_ids = [s.metadata.sample_id for s in group_samples]
            n_rep = len(group_samples)
            conditions.append(
                StrainCondition(
                    strain=strain,
                    temperature=temp,
                    carbon_source=carbon,
                    pert_id=pert,
                    sample_ids=sample_ids,
                    n_replicates=n_rep,
                )
            )
        return conditions

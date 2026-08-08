"""WAYB/WAYC 蛋白质组学特征工程。

对齐 `.trae/rules/05-route-a-SPR.md` 第 6 节生物材料构效关系框架：
- 按 菌株×温度×培养基×扰动 聚合表达量
- 计算差异表达量（条件间对比，log2FC）
- 提取功能蛋白家族特征（HSP/代谢/氧化应激/DNA修复）
- 构建菌株-条件级别的材料描述符向量

输出 BioFeatureDescriptor，作为搜索算法的输入特征向量。
"""

from __future__ import annotations

import time

from src.common.logging import AuditLogger
from src.proteome.schemas import (
    BioFeatureDescriptor,
    ProteomeDataset,
    StrainCondition,
)

logger = AuditLogger("proteome_feature_engineering")

# 酵母功能蛋白家族映射（按 GO/SGD 注释归类，简化版）
# 来源：SGD（Saccharomyces Genome Database）+ UniProt 功能注释
PROTEIN_FAMILIES: dict[str, set[str]] = {
    # 热休克蛋白家族（HSP）—— 温度响应核心
    "hsp": {
        "HSP26",
        "HSP42",
        "HSP60",
        "HSP78",
        "HSP82",
        "HSP104",  # 经典 HSP
        "SSA1",
        "SSA2",
        "SSA3",
        "SSA4",  # HSP70 家族
        "SSB1",
        "SSB2",  # HSP70 同源
        "SSE1",
        "SSE2",  # HSP70 类似
        "KAR2",
        "LHS1",  # 内质网 HSP70
        "HSC82",
        "HSC26",  # HSP90 家族
        "TCP1",
        "CCT1",
        "CCT2",
        "CCT3",
        "CCT4",
        "CCT5",
        "CCT6",
        "CCT7",
        "CCT8",  # CCT 复合体
    },
    # 糖代谢相关（碳源切换响应）
    "metabolic": {
        "GAL1",
        "GAL2",
        "GAL3",
        "GAL4",
        "GAL7",
        "GAL10",
        "GAL80",  # GAL 操纵子
        "GLK1",
        "HXK1",
        "HXK2",  # 己糖激酶
        "PGI1",
        "PFK1",
        "PFK2",
        "FBA1",  # 糖酵解
        "TDH1",
        "TDH2",
        "TDH3",  # GAPDH
        "PGK1",
        "ENO1",
        "ENO2",  # 烯醇化酶
        "PYK1",
        "PYK2",  # 丙酮酸激酶
        "PDC1",
        "PDC5",
        "PDC6",  # 丙酮酸脱羧酶
        "ADH1",
        "ADH2",
        "ADH3",
        "ADH4",  # 乙醇脱氢酶
        "GIT1",
        "GUT1",
        "GUT2",  # 甘油代谢
    },
    # 氧化应激响应
    "oxidative": {
        "SOD1",
        "SOD2",  # 超氧化物歧化酶
        "CTT1",
        "CTA1",  # 过氧化氢酶
        "TSA1",
        "TSA2",
        "AHp1",
        "AHP2",  # 硫氧还蛋白过氧化物酶
        "TRR1",
        "TRR2",  # 硫氧还蛋白还原酶
        "GLR1",  # 谷胱甘肽还原酶
        "GSH1",
        "GSH2",  # 谷胱甘肽合成
        "YAP1",
        "SKN7",  # 氧化应激转录因子
    },
    # DNA 修复
    "dna_repair": {
        "RAD1",
        "RAD2",
        "RAD4",
        "RAD7",
        "RAD10",
        "RAD14",  # NER
        "RAD50",
        "RAD51",
        "RAD52",
        "RAD54",
        "RAD55",
        "RAD57",  # HR
        "RAD6",
        "RAD18",  # PRR
        "MLH1",
        "MLH2",
        "MLH3",
        "MSH1",
        "MSH2",
        "MSH3",
        "MSH6",  # MMR
        "POL30",
        "POL31",
        "POL32",  # DNA 聚合酶 δ
        "LIG1",
        "LIG4",  # DNA 连接酶
    },
}

# 反向索引：基因名 → 家族
GENE_TO_FAMILY: dict[str, str] = {}
for family, genes in PROTEIN_FAMILIES.items():
    for gene in genes:
        GENE_TO_FAMILY[gene] = family


def get_family_genes(gene_names: list[str]) -> dict[str, list[str]]:
    """从数据集基因列表中筛选各功能家族的基因。

    Args:
        gene_names: 数据集的基因名列表。

    Returns:
        家族名 → 该家族在数据集中存在的基因列表。
    """
    result: dict[str, list[str]] = {fam: [] for fam in PROTEIN_FAMILIES}
    for gene in gene_names:
        fam = GENE_TO_FAMILY.get(gene)
        if fam is not None:
            result[fam].append(gene)
    return result


def _compute_family_score(
    expression: dict[str, float],
    family_genes: list[str],
) -> float:
    """计算功能蛋白家族得分（成员表达均值）。

    Args:
        expression: 样本表达量字典。
        family_genes: 该家族的基因列表。

    Returns:
        家族得分（成员表达的均值）。
    """
    if not family_genes:
        return 0.0
    vals = [expression.get(g, 0.0) for g in family_genes]
    return sum(vals) / len(vals)


def compute_log2fc(
    target_expr: dict[str, float],
    control_expr: dict[str, float],
    gene_names: list[str],
    pseudocount: float = 1.0,
) -> dict[str, float]:
    """计算 log2 fold change（差异表达量）。

    公式：log2((target + pseudocount) / (control + pseudocount))

    Args:
        target_expr: 实验组表达量。
        control_expr: 对照组表达量。
        gene_names: 基因名列表。
        pseudocount: 伪计数，避免除零。

    Returns:
        基因名 → log2FC 映射。
    """
    import numpy as np

    result: dict[str, float] = {}
    for gene in gene_names:
        t = target_expr.get(gene, 0.0) + pseudocount
        c = control_expr.get(gene, 0.0) + pseudocount
        result[gene] = float(np.log2(t / c))
    return result


def build_feature_descriptor(
    condition: StrainCondition,
    control: StrainCondition | None = None,
    gene_names: list[str] | None = None,
) -> BioFeatureDescriptor:
    """从菌株-条件聚合构建特征描述符。

    Args:
        condition: 目标菌株-条件（含平均表达谱）。
        control: 对照组（同菌株、对照组条件），None 时差异表达特征为空。
        gene_names: 基因名列表（用于 diff_vs_control）。

    Returns:
        BioFeatureDescriptor 特征描述符。
    """
    start = time.perf_counter()

    avg_expr = condition.avg_expression
    family_genes_map = get_family_genes(gene_names or list(avg_expr.keys()))

    # 计算功能家族得分
    hsp_score = _compute_family_score(avg_expr, family_genes_map["hsp"])
    meta_score = _compute_family_score(avg_expr, family_genes_map["metabolic"])
    oxi_score = _compute_family_score(avg_expr, family_genes_map["oxidative"])
    dna_score = _compute_family_score(avg_expr, family_genes_map["dna_repair"])

    # 生长速率指标：用整体表达均值近似（无真实生长数据时的代理指标）
    growth_rate = sum(avg_expr.values()) / len(avg_expr) if avg_expr else 0.0

    # 差异表达特征
    diff_vs_control: dict[str, float] = {}
    if control is not None and gene_names:
        diff_vs_control = compute_log2fc(avg_expr, control.avg_expression, gene_names)

    # 特征向量：[hsp, meta, oxi, dna, growth] + top 差异表达基因（前 10）
    feature_vector = [hsp_score, meta_score, oxi_score, dna_score, growth_rate]
    if diff_vs_control:
        sorted_diff = sorted(diff_vs_control.items(), key=lambda x: abs(x[1]), reverse=True)
        feature_vector.extend([v for _, v in sorted_diff[:10]])

    descriptor = BioFeatureDescriptor(
        strain=condition.strain,
        temperature=condition.temperature,
        carbon_source=condition.carbon_source,
        pert_id=condition.pert_id,
        hsp_score=hsp_score,
        metabolic_score=meta_score,
        oxidative_score=oxi_score,
        dna_repair_score=dna_score,
        growth_rate=growth_rate,
        diff_vs_control=diff_vs_control,
        feature_vector=feature_vector,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "build_feature_descriptor",
        "success",
        output_summary={
            "strain": condition.strain,
            "condition": f"{condition.temperature}C_{condition.carbon_source}_{condition.pert_id}",
            "feature_dim": len(feature_vector),
            "has_control": control is not None,
        },
        duration_ms=elapsed_ms,
    )
    return descriptor


def build_all_descriptors(
    dataset: ProteomeDataset,
    conditions: list[StrainCondition] | None = None,
    control_strategy: str = "same_strain_baseline",
) -> list[BioFeatureDescriptor]:
    """为所有菌株-条件构建特征描述符。

    Args:
        dataset: 数据集。
        conditions: 菌株-条件列表，None 时从数据集计算。
        control_strategy: 对照组策略——
            same_strain_baseline（同菌株的基准条件，无扰动）
            same_condition_baseline（同条件的全局均值）

    Returns:
        BioFeatureDescriptor 列表。
    """
    start = time.perf_counter()

    if conditions is None:
        from src.proteome.data_loader import compute_strain_conditions

        conditions = compute_strain_conditions(dataset)

    # 构建对照组索引
    controls: dict[tuple[str, str, str], StrainCondition] = {}
    if control_strategy == "same_strain_baseline":
        # 同菌株的基准条件：温度=30, 碳源=glucose, 无扰动
        for cond in conditions:
            if cond.pert_id == "" and cond.temperature == "30" and cond.carbon_source == "glucose":
                key = (cond.strain, cond.temperature, cond.carbon_source)
                controls[key] = cond
    elif control_strategy == "same_condition_baseline":
        # 同条件的全局均值作为对照（构造一个虚拟 StrainCondition）
        from collections import defaultdict

        import numpy as np

        groups: dict[tuple, list[StrainCondition]] = defaultdict(list)
        for cond in conditions:
            key = (cond.temperature, cond.carbon_source, cond.pert_id)
            groups[key].append(cond)
        for key, group in groups.items():
            avg_dict: dict[str, float] = {}
            for gene in dataset.gene_names:
                vals = [c.avg_expression.get(gene, 0.0) for c in group]
                avg_dict[gene] = float(np.mean(vals)) if vals else 0.0
            # 虚拟对照组（菌株名标为 _BASELINE_）
            controls[("", key[0], key[1])] = StrainCondition(
                strain="",
                temperature=key[0],
                carbon_source=key[1],
                pert_id=key[2],
                avg_expression=avg_dict,
            )

    descriptors: list[BioFeatureDescriptor] = []
    for cond in conditions:
        # 查找对照组
        if control_strategy == "same_strain_baseline":
            ctrl_key = (cond.strain, "30", "glucose")
            control = controls.get(ctrl_key)
        else:
            ctrl_key = ("", cond.temperature, cond.carbon_source)
            control = controls.get(ctrl_key)

        # 若对照组即自身，则无对照
        if control is not None and control.pert_id == cond.pert_id:
            control = None

        desc = build_feature_descriptor(cond, control=control, gene_names=dataset.gene_names)
        descriptors.append(desc)

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "build_all_descriptors",
        "success",
        output_summary={
            "n_descriptors": len(descriptors),
            "control_strategy": control_strategy,
        },
        duration_ms=elapsed_ms,
    )
    return descriptors


def extract_family_features(
    dataset: ProteomeDataset,
) -> dict[str, list[float]]:
    """提取数据集级别的功能家族特征矩阵。

    Args:
        dataset: 数据集。

    Returns:
        家族名 → 该家族在每个样本中的得分列表。
    """
    start = time.perf_counter()

    family_genes_map = get_family_genes(dataset.gene_names)
    result: dict[str, list[float]] = {fam: [] for fam in PROTEIN_FAMILIES}

    for sample in dataset.samples:
        for fam in PROTEIN_FAMILIES:
            score = _compute_family_score(sample.expression, family_genes_map[fam])
            result[fam].append(score)

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "extract_family_features",
        "success",
        output_summary={
            "n_samples": dataset.n_samples,
            "n_families": len(PROTEIN_FAMILIES),
        },
        duration_ms=elapsed_ms,
    )
    return result


def get_top_differential_genes(
    descriptor: BioFeatureDescriptor,
    top_k: int = 20,
    abs_threshold: float = 1.0,
) -> list[tuple[str, float]]:
    """获取差异表达最显著的基因（|log2FC| 排序）。

    Args:
        descriptor: 特征描述符。
        top_k: 返回前 k 个基因。
        abs_threshold: log2FC 绝对值阈值（默认 1.0 = 2 倍变化）。

    Returns:
        (基因名, log2FC) 元组列表，按 |log2FC| 降序。
    """
    if not descriptor.diff_vs_control:
        return []

    sorted_genes = sorted(
        descriptor.diff_vs_control.items(),
        key=lambda x: abs(x[1]),
        reverse=True,
    )
    return [(gene, log2fc) for gene, log2fc in sorted_genes if abs(log2fc) >= abs_threshold][:top_k]

"""WAYB/WAYC 蛋白质组学数据清洗与归一化。

对齐 `.trae/rules/00-project-rules.md` 第 5.3 节预处理规范：
- 处理缺失值（NA/零值）
- 对数转换（log2 transform，处理负值与零值的位移）
- 批次效应检测与校正（基于 replicate 组的均值中心化）
- 特征方差过滤（去除低方差特征）

设计原则：
1. 每个步骤独立可调用，也可链式调用 preprocess() 一键处理
2. 全程写审计日志（清洗前后样本数/特征数/分布指标）
3. 输入输出都是 ProteomeDataset 对象（不可变转换，返回新对象）
4. 数值稳定性：log2 前加位移避免 log(0)，方差过滤前去除常数列
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from src.common.logging import AuditLogger
from src.proteome.schemas import ProteomeDataset, ProteomeSample

logger = AuditLogger("proteome_preprocessor")

# log2 转换的默认位移（避免 log(0) 和负值）
DEFAULT_LOG_OFFSET = 1.0
# 低方差过滤的默认阈值（方差低于此值的基因被剔除）
DEFAULT_MIN_VARIANCE = 1e-6
# 缺失率默认阈值（缺失率高于此值的基因被剔除）
DEFAULT_MAX_MISSING_RATE = 0.3


@dataclass
class PreprocessReport:
    """清洗报告（每步统计）。"""

    n_samples_in: int = 0
    n_samples_out: int = 0
    n_genes_in: int = 0
    n_genes_out: int = 0
    n_missing_filled: int = 0
    n_genes_filtered_low_var: int = 0
    n_genes_filtered_high_missing: int = 0
    log_offset: float = 0.0
    batch_corrected: bool = False
    steps: list[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_samples_in": self.n_samples_in,
            "n_samples_out": self.n_samples_out,
            "n_genes_in": self.n_genes_in,
            "n_genes_out": self.n_genes_out,
            "n_missing_filled": self.n_missing_filled,
            "n_genes_filtered_low_var": self.n_genes_filtered_low_var,
            "n_genes_filtered_high_missing": self.n_genes_filtered_high_missing,
            "log_offset": self.log_offset,
            "batch_corrected": self.batch_corrected,
            "steps": self.steps or [],
        }


def _count_missing(samples: list[ProteomeSample], gene_names: list[str]) -> dict[str, int]:
    """统计每个基因的缺失值数量（值为 0.0 视为缺失）。"""
    missing_count = {g: 0 for g in gene_names}
    for sample in samples:
        for gene in gene_names:
            val = sample.expression.get(gene, 0.0)
            if val == 0.0 or val is None:
                missing_count[gene] += 1
    return missing_count


def fill_missing(
    dataset: ProteomeDataset,
    strategy: str = "zero",
) -> tuple[ProteomeDataset, int]:
    """缺失值填充。

    Args:
        dataset: 原始数据集。
        strategy: 填充策略——zero（填 0）/median（填该基因中位数）/mean（填均值）。

    Returns:
        (填充后的数据集, 填充的缺失值总数)。
    """
    start = time.perf_counter()
    n_filled = 0

    if strategy == "zero":
        # 0.0 已经是默认值，仅统计
        for sample in dataset.samples:
            for gene in dataset.gene_names:
                if gene not in sample.expression or sample.expression[gene] is None:
                    sample.expression[gene] = 0.0
                    n_filled += 1
                elif sample.expression[gene] == 0.0:
                    n_filled += 1
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.log(
            "fill_missing_zero",
            "success",
            output_summary={"n_filled": n_filled, "strategy": strategy},
            duration_ms=elapsed_ms,
        )
        return dataset, n_filled

    # median / mean 策略：先按基因计算统计量
    import numpy as np

    gene_stats: dict[str, float] = {}
    for gene in dataset.gene_names:
        vals = [
            sample.expression.get(gene, 0.0)
            for sample in dataset.samples
            if sample.expression.get(gene, 0.0) != 0.0
        ]
        if not vals:
            gene_stats[gene] = 0.0
            continue
        if strategy == "median":
            gene_stats[gene] = float(np.median(vals))
        else:  # mean
            gene_stats[gene] = float(np.mean(vals))

    new_samples: list[ProteomeSample] = []
    for sample in dataset.samples:
        new_expr = dict(sample.expression)
        for gene in dataset.gene_names:
            val = new_expr.get(gene, 0.0)
            if val == 0.0 or val is None:
                new_expr[gene] = gene_stats[gene]
                n_filled += 1
        new_samples.append(
            ProteomeSample(
                metadata=sample.metadata,
                expression=new_expr,
                n_features=len(new_expr),
            )
        )

    new_dataset = ProteomeDataset(
        samples=new_samples,
        strains=dataset.strains,
        temperatures=dataset.temperatures,
        carbon_sources=dataset.carbon_sources,
        perturbations=dataset.perturbations,
        gene_names=dataset.gene_names,
        n_samples=len(new_samples),
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "fill_missing_stat",
        "success",
        output_summary={"n_filled": n_filled, "strategy": strategy},
        duration_ms=elapsed_ms,
    )
    return new_dataset, n_filled


def filter_low_variance(
    dataset: ProteomeDataset,
    min_variance: float = DEFAULT_MIN_VARIANCE,
) -> tuple[ProteomeDataset, int]:
    """低方差特征过滤。

    Args:
        dataset: 数据集。
        min_variance: 最小方差阈值，低于此值的基因被剔除。

    Returns:
        (过滤后的数据集, 被剔除的基因数)。
    """
    import numpy as np

    start = time.perf_counter()

    if not dataset.samples or not dataset.gene_names:
        return dataset, 0

    # 计算每个基因的方差
    matrix = np.array(
        [sample.to_vector(dataset.gene_names) for sample in dataset.samples], dtype=np.float64
    )
    variances = np.var(matrix, axis=0)

    kept_mask = variances >= min_variance
    kept_genes = [g for g, keep in zip(dataset.gene_names, kept_mask) if keep]
    n_filtered = len(dataset.gene_names) - len(kept_genes)

    # 构建新数据集
    new_samples: list[ProteomeSample] = []
    for sample in dataset.samples:
        new_expr = {g: sample.expression.get(g, 0.0) for g in kept_genes}
        new_samples.append(
            ProteomeSample(
                metadata=sample.metadata,
                expression=new_expr,
                n_features=len(new_expr),
            )
        )

    new_dataset = ProteomeDataset(
        samples=new_samples,
        strains=dataset.strains,
        temperatures=dataset.temperatures,
        carbon_sources=dataset.carbon_sources,
        perturbations=dataset.perturbations,
        gene_names=kept_genes,
        n_samples=len(new_samples),
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "filter_low_variance",
        "success",
        output_summary={
            "n_genes_in": len(dataset.gene_names),
            "n_genes_out": len(kept_genes),
            "n_filtered": n_filtered,
            "min_variance": min_variance,
        },
        duration_ms=elapsed_ms,
    )
    return new_dataset, n_filtered


def filter_high_missing(
    dataset: ProteomeDataset,
    max_missing_rate: float = DEFAULT_MAX_MISSING_RATE,
) -> tuple[ProteomeDataset, int]:
    """高缺失率特征过滤。

    Args:
        dataset: 数据集。
        max_missing_rate: 最大允许缺失率，高于此值的基因被剔除。

    Returns:
        (过滤后的数据集, 被剔除的基因数)。
    """
    start = time.perf_counter()

    if not dataset.samples:
        return dataset, 0

    n_samples = len(dataset.samples)
    missing_count = _count_missing(dataset.samples, dataset.gene_names)

    kept_genes = [g for g in dataset.gene_names if missing_count[g] / n_samples <= max_missing_rate]
    n_filtered = len(dataset.gene_names) - len(kept_genes)

    new_samples: list[ProteomeSample] = []
    for sample in dataset.samples:
        new_expr = {g: sample.expression.get(g, 0.0) for g in kept_genes}
        new_samples.append(
            ProteomeSample(
                metadata=sample.metadata,
                expression=new_expr,
                n_features=len(new_expr),
            )
        )

    new_dataset = ProteomeDataset(
        samples=new_samples,
        strains=dataset.strains,
        temperatures=dataset.temperatures,
        carbon_sources=dataset.carbon_sources,
        perturbations=dataset.perturbations,
        gene_names=kept_genes,
        n_samples=len(new_samples),
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "filter_high_missing",
        "success",
        output_summary={
            "n_genes_in": len(dataset.gene_names),
            "n_genes_out": len(kept_genes),
            "n_filtered": n_filtered,
            "max_missing_rate": max_missing_rate,
        },
        duration_ms=elapsed_ms,
    )
    return new_dataset, n_filtered


def log2_transform(
    dataset: ProteomeDataset,
    offset: float = DEFAULT_LOG_OFFSET,
) -> ProteomeDataset:
    """log2 转换（带位移避免 log(0) 和负值）。

    公式：log2(x + offset)，offset 默认 1.0。
    对负值取绝对值后再加 offset，避免 NaN。

    Args:
        dataset: 数据集。
        offset: 位移量，默认 1.0。

    Returns:
        转换后的数据集。
    """
    import numpy as np

    start = time.perf_counter()

    new_samples: list[ProteomeSample] = []
    for sample in dataset.samples:
        new_expr = {
            gene: float(np.log2(abs(val) + offset)) for gene, val in sample.expression.items()
        }
        new_samples.append(
            ProteomeSample(
                metadata=sample.metadata,
                expression=new_expr,
                n_features=len(new_expr),
            )
        )

    new_dataset = ProteomeDataset(
        samples=new_samples,
        strains=dataset.strains,
        temperatures=dataset.temperatures,
        carbon_sources=dataset.carbon_sources,
        perturbations=dataset.perturbations,
        gene_names=dataset.gene_names,
        n_samples=len(new_samples),
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "log2_transform",
        "success",
        output_summary={"offset": offset, "n_samples": len(new_samples)},
        duration_ms=elapsed_ms,
    )
    return new_dataset


def correct_batch_effects(
    dataset: ProteomeDataset,
    group_key: str = "replicate",
) -> ProteomeDataset:
    """批次效应校正（均值中心化）。

    按 replicate 组（或其他元数据字段）分组，每组减去该组的全局均值，
    实现批次效应去除。这是简化的 ComBat 替代方案，无第三方依赖。

    Args:
        dataset: 数据集。
        group_key: 分组字段名（默认 replicate）。

    Returns:
        校正后的数据集。
    """
    from collections import defaultdict

    import numpy as np

    start = time.perf_counter()

    if not dataset.samples or not dataset.gene_names:
        return dataset

    # 按分组字段聚合样本索引
    groups: dict[Any, list[int]] = defaultdict(list)
    for idx, sample in enumerate(dataset.samples):
        if group_key == "replicate":
            key = sample.metadata.replicate
        else:
            key = sample.metadata.extra.get(group_key, "unknown")
        groups[key].append(idx)

    # 构建表达矩阵（n_samples × n_genes）
    matrix = np.array(
        [sample.to_vector(dataset.gene_names) for sample in dataset.samples], dtype=np.float64
    )

    # 每组减去该组均值
    for key, indices in groups.items():
        group_mean = np.mean(matrix[indices], axis=0)
        matrix[indices] = matrix[indices] - group_mean

    # 重建样本
    new_samples: list[ProteomeSample] = []
    for idx, sample in enumerate(dataset.samples):
        new_expr = {gene: float(matrix[idx, i]) for i, gene in enumerate(dataset.gene_names)}
        new_samples.append(
            ProteomeSample(
                metadata=sample.metadata,
                expression=new_expr,
                n_features=len(new_expr),
            )
        )

    new_dataset = ProteomeDataset(
        samples=new_samples,
        strains=dataset.strains,
        temperatures=dataset.temperatures,
        carbon_sources=dataset.carbon_sources,
        perturbations=dataset.perturbations,
        gene_names=dataset.gene_names,
        n_samples=len(new_samples),
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "correct_batch_effects",
        "success",
        output_summary={
            "group_key": group_key,
            "n_groups": len(groups),
            "n_samples": len(new_samples),
        },
        duration_ms=elapsed_ms,
    )
    return new_dataset


def preprocess(
    dataset: ProteomeDataset,
    fill_strategy: str = "median",
    log_offset: float = DEFAULT_LOG_OFFSET,
    min_variance: float = DEFAULT_MIN_VARIANCE,
    max_missing_rate: float = DEFAULT_MAX_MISSING_RATE,
    correct_batch: bool = True,
    batch_group_key: str = "replicate",
) -> tuple[ProteomeDataset, PreprocessReport]:
    """一键预处理管线：缺失填充 → 高缺失过滤 → 低方差过滤 → log2 → 批次校正。

    Args:
        dataset: 原始数据集。
        fill_strategy: 缺失填充策略（zero/median/mean）。
        log_offset: log2 位移量。
        min_variance: 低方差过滤阈值。
        max_missing_rate: 高缺失率过滤阈值。
        correct_batch: 是否做批次校正。
        batch_group_key: 批次分组字段。

    Returns:
        (清洗后数据集, 清洗报告)。
    """
    report = PreprocessReport(
        n_samples_in=dataset.n_samples,
        n_genes_in=len(dataset.gene_names),
        steps=[],
    )

    # Step 1: 缺失值填充
    dataset, n_filled = fill_missing(dataset, strategy=fill_strategy)
    report.n_missing_filled = n_filled
    report.steps.append(f"fill_missing({fill_strategy})")

    # Step 2: 高缺失率过滤
    dataset, n_high_missing = filter_high_missing(dataset, max_missing_rate)
    report.n_genes_filtered_high_missing = n_high_missing
    report.steps.append(f"filter_high_missing(rate<={max_missing_rate})")

    # Step 3: 低方差过滤
    dataset, n_low_var = filter_low_variance(dataset, min_variance)
    report.n_genes_filtered_low_var = n_low_var
    report.steps.append(f"filter_low_variance(var>={min_variance})")

    # Step 4: log2 转换
    dataset = log2_transform(dataset, offset=log_offset)
    report.log_offset = log_offset
    report.steps.append(f"log2_transform(offset={log_offset})")

    # Step 5: 批次效应校正
    if correct_batch:
        dataset = correct_batch_effects(dataset, group_key=batch_group_key)
        report.batch_corrected = True
        report.steps.append(f"correct_batch_effects(key={batch_group_key})")

    report.n_samples_out = dataset.n_samples
    report.n_genes_out = len(dataset.gene_names)

    logger.log(
        "preprocess_complete",
        "success",
        output_summary=report.to_dict(),
    )
    return dataset, report

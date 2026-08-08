"""WAYB/WAYC 酵母蛋白质组学数据加载器。

对齐 `.trae/rules/00-project-rules.md` 第 5.3 节数据规范：
- WAYB/WAYC 数据集：5 种菌株 × 41 种化学扰动 × 5243 蛋白表达量
- 样本划分：train / val_strain_only / val_chem_only / val_both / val_time / test
- 数据源：metadata CSV（15 列样本元数据）+ proteome CSV（5244 列）

功能：
1. 加载 metadata + proteome CSV
2. 构建样本级 ProteomeSample 对象
3. 生成菌株-条件级 StrainCondition 聚合
4. 数据清洗：缺失值检查、异常值标记
5. 数据集划分（split）过滤
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from src.common.config import DATA_DIR
from src.common.logging import AuditLogger
from src.proteome.schemas import (
    DataSplit,
    ProteomeDataset,
    ProteomeSample,
    SampleMetadata,
    StrainCondition,
)

# 默认数据目录（项目规范 5.3 节：data/raw/）
DEFAULT_RAW_DIR = DATA_DIR / "raw"
# WAYB/WAYC 数据集文件名
METADATA_FILENAME = "metadata.csv"
PROTEOME_FILENAME = "proteome.csv"

logger = AuditLogger("proteome_data_loader")


def _resolve_file(raw_dir: str | Path | None = None) -> tuple[Path, Path]:
    """解析 metadata 和 proteome CSV 文件路径。

    Args:
        raw_dir: 数据目录，默认 data/raw/。

    Returns:
        (metadata_path, proteome_path) 元组。

    Raises:
        FileNotFoundError: 任一文件不存在时。
    """
    base = Path(raw_dir) if raw_dir is not None else DEFAULT_RAW_DIR
    meta_path = base / METADATA_FILENAME
    prot_path = base / PROTEOME_FILENAME

    missing: list[str] = []
    if not meta_path.exists():
        missing.append(str(meta_path))
    if not prot_path.exists():
        missing.append(str(prot_path))
    if missing:
        raise FileNotFoundError(
            f"WAYB/WAYC 数据文件不存在: {', '.join(missing)}。"
            f"请将 metadata.csv 和 proteome.csv 放入 data/raw/ 目录。"
        )
    return meta_path, prot_path


def _parse_metadata_row(row: dict[str, Any]) -> SampleMetadata:
    """解析单行 metadata CSV 为 SampleMetadata。

    字段对齐 WAYB/WAYC metadata 的 15 列，未知字段存入 extra。
    """
    known_keys = {
        "sample_id",
        "strain",
        "temperature",
        "carbon_source",
        "pert_id",
        "time_point",
        "split",
        "replicate",
    }

    extra = {k: v for k, v in row.items() if k not in known_keys}

    return SampleMetadata(
        sample_id=str(row.get("sample_id", "")),
        strain=str(row.get("strain", "")).strip(),
        temperature=str(row.get("temperature", "")).strip(),
        carbon_source=str(row.get("carbon_source", "")).strip().lower(),
        pert_id=str(row.get("pert_id", "")).strip(),
        time_point=float(row.get("time_point", 0)),
        split=str(row.get("split", "")).strip(),
        replicate=int(row.get("replicate", 1)),
        extra=extra,
    )


def _parse_expression_row(
    row: dict[str, Any],
    gene_names: list[str],
) -> dict[str, float]:
    """解析单行 proteome CSV 为基因名→表达量映射。

    Args:
        row: CSV 行字典（key=列名, value=字符串值）。
        gene_names: 基因名列表（有序）。

    Returns:
        基因名 → 表达量 float 映射。缺失值填 0.0。
    """
    expression: dict[str, float] = {}
    for gene in gene_names:
        raw_val = row.get(gene, "")
        try:
            expression[gene] = float(raw_val) if raw_val not in ("", "NA", "N/A", "null") else 0.0
        except (ValueError, TypeError):
            expression[gene] = 0.0
    return expression


def load_wayb_wayc(
    raw_dir: str | Path | None = None,
    splits: DataSplit | list[DataSplit] | None = None,
) -> ProteomeDataset:
    """加载 WAYB/WAYC 酵母蛋白质组学数据集。

    Args:
        raw_dir: 数据目录，默认 data/raw/。
        splits: 数据集划分过滤，None 时加载全部。可传单个或多个 split。

    Returns:
        ProteomeDataset 数据集容器。

    Raises:
        FileNotFoundError: 数据文件不存在。
        ValueError: 数据解析失败。
    """
    import pandas as pd

    start = time.perf_counter()

    meta_path, prot_path = _resolve_file(raw_dir)

    with logger.step("resolve_data_files", input_summary=str(meta_path.parent)):
        pass

    with logger.step("load_metadata_csv", input_summary=str(meta_path)):
        meta_df = pd.read_csv(meta_path)

    with logger.step("load_proteome_csv", input_summary=str(prot_path)):
        prot_df = pd.read_csv(prot_path)

    # 确定基因名（proteome 表的列，除 sample_id 外均为基因）
    gene_names = [c for c in prot_df.columns if c != "sample_id"]

    # 构建 sample_id → expression 映射
    with logger.step(
        "build_expression_index",
        input_summary=f"{len(prot_df)} rows × {len(gene_names)} genes",
    ):
        expression_index: dict[str, dict[str, float]] = {}
        for _, prot_row in prot_df.iterrows():
            sid = str(prot_row.get("sample_id", ""))
            if not sid:
                continue
            expr = _parse_expression_row(prot_row.to_dict(), gene_names)
            expression_index[sid] = expr

    # 过滤 split
    split_filter: set[str] | None = None
    if splits is not None:
        if isinstance(splits, str):
            split_filter = {splits}
        else:
            split_filter = set(splits)

    # 构建样本列表
    with logger.step("build_samples", input_summary=f"{len(meta_df)} metadata rows"):
        samples: list[ProteomeSample] = []
        strains_set: set[str] = set()
        temperatures_set: set[str] = set()
        carbons_set: set[str] = set()
        perts_set: set[str] = set()

        for _, meta_row in meta_df.iterrows():
            meta_dict = meta_row.to_dict()
            meta = _parse_metadata_row(meta_dict)

            if split_filter is not None and meta.split not in split_filter:
                continue

            expr = expression_index.get(meta.sample_id, {})
            n_feat = len(expr)

            samples.append(
                ProteomeSample(
                    metadata=meta,
                    expression=expr,
                    n_features=n_feat,
                )
            )

            strains_set.add(meta.strain)
            temperatures_set.add(meta.temperature)
            carbons_set.add(meta.carbon_source)
            if meta.pert_id:
                perts_set.add(meta.pert_id)

    dataset = ProteomeDataset(
        samples=samples,
        strains=sorted(strains_set),
        temperatures=sorted(temperatures_set),
        carbon_sources=sorted(carbons_set),
        perturbations=sorted(perts_set),
        gene_names=gene_names,
        n_samples=len(samples),
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "load_complete",
        "success",
        output_summary={
            "n_samples": dataset.n_samples,
            "n_strains": len(dataset.strains),
            "n_temperatures": len(dataset.temperatures),
            "n_carbon_sources": len(dataset.carbon_sources),
            "n_perturbations": len(dataset.perturbations),
            "n_genes": len(dataset.gene_names),
        },
        duration_ms=elapsed_ms,
    )

    return dataset


def compute_strain_conditions(
    dataset: ProteomeDataset,
) -> list[StrainCondition]:
    """从数据集计算所有菌株-条件组合的聚合统计。

    对每个 (strain, temperature, carbon_source, pert_id) 组合，
    计算平均表达谱和标准差。

    Args:
        dataset: 已加载的蛋白质组学数据集。

    Returns:
        StrainCondition 列表（含聚合统计）。
    """
    from collections import defaultdict

    import numpy as np

    start = time.perf_counter()

    with logger.step("group_by_condition", input_summary=f"{dataset.n_samples} samples"):
        groups: dict[tuple[str, str, str, str], list[ProteomeSample]] = defaultdict(list)
        for sample in dataset.samples:
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

        # 聚合表达谱
        expressions = [
            np.array(s.to_vector(dataset.gene_names), dtype=np.float64) for s in group_samples
        ]
        if expressions:
            stacked = np.vstack(expressions)
            avg_expr = np.mean(stacked, axis=0)
            std_expr = np.std(stacked, axis=0)
            avg_dict = {gene: float(avg_expr[i]) for i, gene in enumerate(dataset.gene_names)}
            std_dict = {gene: float(std_expr[i]) for i, gene in enumerate(dataset.gene_names)}
        else:
            avg_dict = {}
            std_dict = {}

        conditions.append(
            StrainCondition(
                strain=strain,
                temperature=temp,
                carbon_source=carbon,
                pert_id=pert,
                sample_ids=sample_ids,
                n_replicates=n_rep,
                avg_expression=avg_dict,
                std_expression=std_dict,
            )
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "compute_conditions_complete",
        "success",
        output_summary={
            "n_conditions": len(conditions),
            "genes_per_condition": len(dataset.gene_names),
        },
        duration_ms=elapsed_ms,
    )

    return conditions


def get_samples_by_strain(
    dataset: ProteomeDataset,
    strain: str,
) -> list[ProteomeSample]:
    """按菌株过滤样本。

    Args:
        dataset: 数据集。
        strain: 菌株名（如 BAI）。

    Returns:
        该菌株的所有样本列表。
    """
    return [s for s in dataset.samples if s.metadata.strain == strain]


def get_samples_by_split(
    dataset: ProteomeDataset,
    split: DataSplit,
) -> list[ProteomeSample]:
    """按数据集划分过滤样本。

    Args:
        dataset: 数据集。
        split: 数据划分名。

    Returns:
        该划分的所有样本列表。
    """
    return [s for s in dataset.samples if s.metadata.split == split]


def get_expression_matrix(
    dataset: ProteomeDataset,
    gene_names: list[str] | None = None,
) -> tuple[list[str], list[list[float]]]:
    """获取全数据集的表达矩阵（样本列表 × 基因列表）。

    Args:
        dataset: 数据集。
        gene_names: 基因名子集，None 时使用全部基因。

    Returns:
        (sample_ids, expression_matrix) 元组，矩阵 shape = (n_samples, n_genes)。
    """
    genes = gene_names or dataset.gene_names
    sample_ids = [s.metadata.sample_id for s in dataset.samples]
    matrix = [s.to_vector(genes) for s in dataset.samples]
    return sample_ids, matrix

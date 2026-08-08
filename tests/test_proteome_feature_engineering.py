"""T1.3 特征工程测试。

遵循 `.trae/rules/00-project-rules.md` 第 3.4 节测试规范：
纯 Python + numpy，无第三方依赖；内存 mock 数据集。
"""

from __future__ import annotations

import pytest

from src.proteome.feature_engineering import (
    PROTEIN_FAMILIES,
    build_all_descriptors,
    build_feature_descriptor,
    compute_log2fc,
    extract_family_features,
    get_family_genes,
    get_top_differential_genes,
)
from src.proteome.schemas import (
    BioFeatureDescriptor,
    ProteomeDataset,
    ProteomeSample,
    SampleMetadata,
    StrainCondition,
)

# ---------- Fixtures ----------


def _make_meta(sample_id: str, strain: str = "BAI", replicate: int = 1) -> SampleMetadata:
    return SampleMetadata(
        sample_id=sample_id,
        strain=strain,
        temperature="30",
        carbon_source="glucose",
        pert_id="#1",
        split="train",
        replicate=replicate,
    )


def _make_sample(
    sample_id: str,
    gene_values: dict[str, float],
    strain: str = "BAI",
) -> ProteomeSample:
    return ProteomeSample(
        metadata=_make_meta(sample_id, strain),
        expression=dict(gene_values),
        n_features=len(gene_values),
    )


@pytest.fixture
def family_dataset() -> ProteomeDataset:
    """含 HSP 和代谢基因的数据集。"""
    gene_names = ["HSP26", "HSP82", "GAL1", "GAL10", "SOD1", "RAD51", "OTHER1"]
    samples = [
        _make_sample("s1", {g: float(i * 2) for i, g in enumerate(gene_names)}),
        _make_sample("s2", {g: float(i * 2 + 1) for i, g in enumerate(gene_names)}),
        _make_sample("s3", {g: float(i * 2 + 2) for i, g in enumerate(gene_names)}),
    ]
    return ProteomeDataset(
        samples=samples,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1"],
        gene_names=gene_names,
        n_samples=3,
    )


@pytest.fixture
def control_and_target_conditions() -> tuple[StrainCondition, StrainCondition, list[str]]:
    """对照组与实验组（同菌株不同扰动）。"""
    gene_names = ["HSP26", "HSP82", "GAL1", "OTHER1"]
    control = StrainCondition(
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
        pert_id="",
        sample_ids=["c1", "c2"],
        n_replicates=2,
        avg_expression={"HSP26": 2.0, "HSP82": 4.0, "GAL1": 6.0, "OTHER1": 8.0},
        std_expression={"HSP26": 0.5, "HSP82": 0.5, "GAL1": 0.5, "OTHER1": 0.5},
    )
    target = StrainCondition(
        strain="BAI",
        temperature="37",
        carbon_source="glucose",
        pert_id="#5",
        sample_ids=["t1", "t2"],
        n_replicates=2,
        avg_expression={"HSP26": 8.0, "HSP82": 16.0, "GAL1": 6.0, "OTHER1": 8.0},
        std_expression={"HSP26": 1.0, "HSP82": 1.0, "GAL1": 1.0, "OTHER1": 1.0},
    )
    return control, target, gene_names


# ---------- get_family_genes ----------


def test_get_family_genes_identifies_known(family_dataset: ProteomeDataset) -> None:
    family_map = get_family_genes(family_dataset.gene_names)
    assert "HSP26" in family_map["hsp"]
    assert "HSP82" in family_map["hsp"]
    assert "GAL1" in family_map["metabolic"]
    assert "GAL10" in family_map["metabolic"]
    assert "SOD1" in family_map["oxidative"]
    assert "RAD51" in family_map["dna_repair"]
    assert "OTHER1" not in family_map["hsp"]


def test_get_family_genes_unknown_only() -> None:
    family_map = get_family_genes(["UNKNOWN1", "UNKNOWN2"])
    for fam in PROTEIN_FAMILIES:
        assert family_map[fam] == []


# ---------- compute_log2fc ----------


def test_compute_log2fc_basic() -> None:
    target = {"G1": 8.0, "G2": 2.0, "G3": 4.0}
    control = {"G1": 2.0, "G2": 2.0, "G3": 1.0}
    gene_names = ["G1", "G2", "G3"]
    fc = compute_log2fc(target, control, gene_names, pseudocount=1.0)
    # G1: log2(9/3) = log2(3) ≈ 1.585
    # G2: log2(3/3) = 0
    # G3: log2(5/2) ≈ 1.322
    assert abs(fc["G1"] - 1.585) < 0.01
    assert abs(fc["G2"] - 0.0) < 0.01
    assert abs(fc["G3"] - 1.322) < 0.01


def test_compute_log2fc_zero_values() -> None:
    """零值加 pseudocount 不应产生 NaN。"""
    import math

    target = {"G1": 0.0}
    control = {"G1": 0.0}
    fc = compute_log2fc(target, control, ["G1"], pseudocount=1.0)
    assert not math.isnan(fc["G1"])
    assert fc["G1"] == 0.0  # log2(1/1) = 0


# ---------- build_feature_descriptor ----------


def test_build_feature_descriptor_no_control(
    control_and_target_conditions: tuple,
) -> None:
    control, target, gene_names = control_and_target_conditions
    desc = build_feature_descriptor(target, control=None, gene_names=gene_names)
    assert isinstance(desc, BioFeatureDescriptor)
    assert desc.strain == "BAI"
    assert desc.temperature == "37"
    assert desc.hsp_score > 0
    assert desc.metabolic_score > 0
    assert desc.diff_vs_control == {}  # 无对照
    assert len(desc.feature_vector) == 5  # 5 个家族得分


def test_build_feature_descriptor_with_control(
    control_and_target_conditions: tuple,
) -> None:
    control, target, gene_names = control_and_target_conditions
    desc = build_feature_descriptor(target, control=control, gene_names=gene_names)
    assert len(desc.diff_vs_control) == 4
    # HSP26 在 target=8.0, control=2.0 → log2((8+1)/(2+1)) = log2(3) > 0
    assert desc.diff_vs_control["HSP26"] > 0
    # OTHER1 在 target=8.0, control=8.0 → log2(9/9) = 0
    assert abs(desc.diff_vs_control["OTHER1"]) < 1e-9
    # 特征向量：5 家族得分 + 10 top diff（实际 4 基因）
    assert len(desc.feature_vector) == 5 + 4


def test_build_feature_descriptor_empty() -> None:
    """空表达谱的边界情况。"""
    empty_cond = StrainCondition(
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
    )
    desc = build_feature_descriptor(empty_cond, control=None, gene_names=[])
    assert desc.hsp_score == 0.0
    assert desc.growth_rate == 0.0


# ---------- build_all_descriptors ----------


def test_build_all_descriptors(family_dataset: ProteomeDataset) -> None:
    # 添加对照组（无扰动）
    for s in family_dataset.samples:
        s.metadata.pert_id = ""
    descriptors = build_all_descriptors(family_dataset)
    assert len(descriptors) > 0
    for desc in descriptors:
        assert isinstance(desc, BioFeatureDescriptor)


def test_build_all_descriptors_with_baseline(family_dataset: ProteomeDataset) -> None:
    """same_strain_baseline 策略：同菌株无扰动为对照。"""
    descriptors = build_all_descriptors(
        family_dataset,
        control_strategy="same_condition_baseline",
    )
    assert len(descriptors) > 0


# ---------- extract_family_features ----------


def test_extract_family_features(family_dataset: ProteomeDataset) -> None:
    family_features = extract_family_features(family_dataset)
    assert "hsp" in family_features
    assert "metabolic" in family_features
    assert "oxidative" in family_features
    assert "dna_repair" in family_features
    assert len(family_features["hsp"]) == family_dataset.n_samples
    # HSP26=0, HSP82=2 → 均值 1.0（s1）
    assert family_features["hsp"][0] > 0


# ---------- get_top_differential_genes ----------


def test_get_top_differential_genes(control_and_target_conditions: tuple) -> None:
    control, target, gene_names = control_and_target_conditions
    desc = build_feature_descriptor(target, control=control, gene_names=gene_names)
    top_genes = get_top_differential_genes(desc, top_k=2, abs_threshold=0.5)
    assert len(top_genes) <= 2
    # HSP26/HSP82 倍数变化最大（target/control = 4x），应排在前两位
    top_gene_names = {g for g, _ in top_genes}
    assert "HSP26" in top_gene_names or "HSP82" in top_gene_names


def test_get_top_differential_genes_no_diff() -> None:
    desc = BioFeatureDescriptor(
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
        formula="BAI_30C_glucose",
    )
    assert get_top_differential_genes(desc) == []


def test_get_top_differential_genes_threshold(control_and_target_conditions: tuple) -> None:
    """高阈值过滤掉不显著基因。"""
    control, target, gene_names = control_and_target_conditions
    desc = build_feature_descriptor(target, control=control, gene_names=gene_names)
    # OTHER1 log2FC=0 应被阈值过滤
    top_genes = get_top_differential_genes(desc, top_k=10, abs_threshold=0.5)
    gene_names_in_top = [g for g, _ in top_genes]
    assert "OTHER1" not in gene_names_in_top

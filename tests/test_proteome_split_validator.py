"""T1.4 数据集划分验证器测试。

遵循 `.trae/rules/00-project-rules.md` 第 3.4 节测试规范。
"""

from __future__ import annotations

import pytest

from src.proteome.schemas import (
    ProteomeDataset,
    ProteomeSample,
    SampleMetadata,
)
from src.proteome.split_validator import (
    EXPECTED_SPLIT_COUNTS,
    VALID_SPLITS,
    SplitReport,
    check_pert_split_consistency,
    check_strain_split_consistency,
    generate_split_summary,
    validate_splits,
)

# ---------- Fixtures ----------


def _make_sample(
    sample_id: str,
    strain: str,
    pert_id: str,
    split: str,
    temperature: str = "30",
    carbon_source: str = "glucose",
) -> ProteomeSample:
    return ProteomeSample(
        metadata=SampleMetadata(
            sample_id=sample_id,
            strain=strain,
            temperature=temperature,
            carbon_source=carbon_source,
            pert_id=pert_id,
            split=split,
        ),
        expression={},
        n_features=0,
    )


@pytest.fixture
def valid_dataset() -> ProteomeDataset:
    """合法划分的数据集：4 个 split，无泄漏。"""
    samples = [
        # train：BAI/BAH × #1/#2
        _make_sample("t1", "BAI", "#1", "train"),
        _make_sample("t2", "BAI", "#2", "train"),
        _make_sample("t3", "BAH", "#1", "train"),
        _make_sample("t4", "BAH", "#2", "train"),
        # val_strain_only：DHY210（新菌株）
        _make_sample("v1", "DHY210", "#1", "val_strain_only"),
        _make_sample("v2", "DHY210", "#2", "val_strain_only"),
        # val_chem_only：#3（新扰动）
        _make_sample("vc1", "BAI", "#3", "val_chem_only"),
        _make_sample("vc2", "BAH", "#3", "val_chem_only"),
        # test：与 train 不重叠
        _make_sample("te1", "BAI", "#4", "test"),
        _make_sample("te2", "BAH", "#5", "test"),
    ]
    return ProteomeDataset(
        samples=samples,
        strains=["BAI", "BAH", "DHY210"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1", "#2", "#3", "#4", "#5"],
        gene_names=[],
        n_samples=len(samples),
    )


@pytest.fixture
def leaky_dataset() -> ProteomeDataset:
    """有数据泄漏的数据集：test 含 train 的 (strain, pert_id) 对。"""
    samples = [
        _make_sample("t1", "BAI", "#1", "train"),
        _make_sample("t2", "BAH", "#2", "train"),
        # test 含 (BAI, #1) → 泄漏
        _make_sample("te1", "BAI", "#1", "test"),
        _make_sample("te2", "BAH", "#3", "test"),
    ]
    return ProteomeDataset(
        samples=samples,
        strains=["BAI", "BAH"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1", "#2", "#3"],
        gene_names=[],
        n_samples=len(samples),
    )


@pytest.fixture
def invalid_split_dataset() -> ProteomeDataset:
    """含非法 split 名称的数据集。"""
    samples = [
        _make_sample("s1", "BAI", "#1", "train"),
        _make_sample("s2", "BAI", "#2", "unknown_split"),  # 非法
        _make_sample("s3", "BAI", "#3", ""),  # 缺失
    ]
    return ProteomeDataset(
        samples=samples,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1", "#2", "#3"],
        gene_names=[],
        n_samples=len(samples),
    )


# ---------- validate_splits ----------


def test_validate_splits_valid_dataset(valid_dataset: ProteomeDataset) -> None:
    report = validate_splits(valid_dataset, expected_counts={}, check_leakage=True)
    assert isinstance(report, SplitReport)
    assert report.n_samples == 10
    assert report.n_missing_split == 0
    assert report.n_invalid_splits == 0
    # 用空 expected_counts 避免 20% 偏差警告
    assert "train" in report.split_counts
    assert report.split_counts["train"] == 4


def test_validate_splits_detects_leakage(leaky_dataset: ProteomeDataset) -> None:
    report = validate_splits(leaky_dataset, expected_counts={}, check_leakage=True)
    assert len(report.leakage_pairs) > 0
    assert ("BAI", "#1") in report.leakage_pairs
    assert report.is_valid is False
    assert any("泄漏" in issue for issue in report.issues)


def test_validate_splits_no_leakage_check(valid_dataset: ProteomeDataset) -> None:
    """关闭泄漏检测时不应报告泄漏。"""
    report = validate_splits(valid_dataset, expected_counts={}, check_leakage=False)
    assert report.leakage_pairs == []


def test_validate_splits_invalid_split(invalid_split_dataset: ProteomeDataset) -> None:
    report = validate_splits(invalid_split_dataset, expected_counts={})
    assert report.n_invalid_splits == 1  # "unknown_split"
    assert report.n_missing_split == 1  # 空字符串
    assert report.is_valid is False


def test_validate_splits_expected_counts_warning() -> None:
    """预期样本数偏差 > 20% 应告警。"""
    samples = [_make_sample("s1", "BAI", "#1", "train")]
    ds = ProteomeDataset(
        samples=samples,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1"],
        gene_names=[],
        n_samples=1,
    )
    report = validate_splits(ds, expected_counts={"train": 1000})
    # 1 vs 1000，偏差 > 20%
    assert any("偏差" in issue for issue in report.issues)


# ---------- check_strain_split_consistency ----------


def test_check_strain_split_consistency_valid(valid_dataset: ProteomeDataset) -> None:
    result = check_strain_split_consistency(valid_dataset)
    assert "DHY210" in result["unique_val_strains"]
    assert result["is_consistent"] is True


def test_check_strain_split_consistency_no_unique() -> None:
    """val_strain_only 菌株与 train 完全重叠时 is_consistent=False。"""
    samples = [
        _make_sample("t1", "BAI", "#1", "train"),
        _make_sample("v1", "BAI", "#2", "val_strain_only"),
    ]
    ds = ProteomeDataset(
        samples=samples,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1", "#2"],
        gene_names=[],
        n_samples=2,
    )
    result = check_strain_split_consistency(ds)
    assert result["is_consistent"] is False
    assert result["unique_val_strains"] == []


# ---------- check_pert_split_consistency ----------


def test_check_pert_split_consistency_valid(valid_dataset: ProteomeDataset) -> None:
    result = check_pert_split_consistency(valid_dataset)
    assert "#3" in result["unique_val_perts"]
    assert result["is_consistent"] is True


def test_check_pert_split_consistency_no_unique() -> None:
    """val_chem_only 扰动与 train 完全重叠时 is_consistent=False。"""
    samples = [
        _make_sample("t1", "BAI", "#1", "train"),
        _make_sample("v1", "BAI", "#1", "val_chem_only"),
    ]
    ds = ProteomeDataset(
        samples=samples,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1"],
        gene_names=[],
        n_samples=2,
    )
    result = check_pert_split_consistency(ds)
    assert result["is_consistent"] is False


# ---------- generate_split_summary ----------


def test_generate_split_summary_valid(valid_dataset: ProteomeDataset) -> None:
    report = validate_splits(valid_dataset, expected_counts={})
    summary = generate_split_summary(report)
    assert "数据集划分验证报告" in summary
    assert "总样本数：10" in summary
    assert "菌株分布" in summary


def test_generate_split_summary_with_issues(leaky_dataset: ProteomeDataset) -> None:
    report = validate_splits(leaky_dataset, expected_counts={})
    summary = generate_split_summary(report)
    assert "数据泄漏" in summary
    assert "问题清单" in summary


def test_generate_split_summary_no_leakage(valid_dataset: ProteomeDataset) -> None:
    report = validate_splits(valid_dataset, expected_counts={})
    summary = generate_split_summary(report)
    assert "无 train/test 数据泄漏" in summary


# ---------- 常量验证 ----------


def test_valid_splits_constant() -> None:
    assert "train" in VALID_SPLITS
    assert "test" in VALID_SPLITS
    assert "val_strain_only" in VALID_SPLITS
    assert len(VALID_SPLITS) == 6


def test_expected_split_counts_constant() -> None:
    assert EXPECTED_SPLIT_COUNTS["train"] == 5920
    assert EXPECTED_SPLIT_COUNTS["test"] == 4454
    assert sum(EXPECTED_SPLIT_COUNTS.values()) == 13412

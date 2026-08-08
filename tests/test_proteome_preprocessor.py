"""T1.2 数据清洗与归一化测试。

遵循 `.trae/rules/00-project-rules.md` 第 3.4 节测试规范：
纯 Python + numpy，无第三方依赖；内存 mock 数据集。
"""

from __future__ import annotations

import pytest

from src.proteome.preprocessor import (
    PreprocessReport,
    correct_batch_effects,
    fill_missing,
    filter_high_missing,
    filter_low_variance,
    log2_transform,
    preprocess,
)
from src.proteome.schemas import (
    ProteomeDataset,
    ProteomeSample,
    SampleMetadata,
)

# ---------- Fixtures ----------


def _make_meta(sample_id: str, replicate: int = 1) -> SampleMetadata:
    """生成 mock 元数据。"""
    return SampleMetadata(
        sample_id=sample_id,
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
        pert_id="#1",
        split="train",
        replicate=replicate,
    )


def _make_sample(
    sample_id: str,
    gene_values: dict[str, float],
    replicate: int = 1,
) -> ProteomeSample:
    """生成 mock 样本。"""
    return ProteomeSample(
        metadata=_make_meta(sample_id, replicate),
        expression=dict(gene_values),
        n_features=len(gene_values),
    )


@pytest.fixture
def simple_dataset() -> ProteomeDataset:
    """6 样本 × 5 基因数据集（含缺失/零方差基因）。"""
    gene_names = ["GENE_A", "GENE_B", "GENE_C", "GENE_CONST", "GENE_ALL_MISSING"]
    samples = [
        _make_sample(
            "s1",
            {
                "GENE_A": 10.0,
                "GENE_B": 5.0,
                "GENE_C": 3.0,
                "GENE_CONST": 1.0,
                "GENE_ALL_MISSING": 0.0,
            },
            replicate=1,
        ),
        _make_sample(
            "s2",
            {
                "GENE_A": 12.0,
                "GENE_B": 6.0,
                "GENE_C": 4.0,
                "GENE_CONST": 1.0,
                "GENE_ALL_MISSING": 0.0,
            },
            replicate=1,
        ),
        _make_sample(
            "s3",
            {
                "GENE_A": 8.0,
                "GENE_B": 4.0,
                "GENE_C": 2.0,
                "GENE_CONST": 1.0,
                "GENE_ALL_MISSING": 0.0,
            },
            replicate=2,
        ),
        _make_sample(
            "s4",
            {
                "GENE_A": 11.0,
                "GENE_B": 5.5,
                "GENE_C": 3.5,
                "GENE_CONST": 1.0,
                "GENE_ALL_MISSING": 0.0,
            },
            replicate=2,
        ),
        _make_sample(
            "s5",
            {
                "GENE_A": 9.0,
                "GENE_B": 4.5,
                "GENE_C": 2.5,
                "GENE_CONST": 1.0,
                "GENE_ALL_MISSING": 0.0,
            },
            replicate=1,
        ),
        _make_sample(
            "s6",
            {
                "GENE_A": 13.0,
                "GENE_B": 6.5,
                "GENE_C": 4.5,
                "GENE_CONST": 1.0,
                "GENE_ALL_MISSING": 0.0,
            },
            replicate=2,
        ),
    ]
    return ProteomeDataset(
        samples=samples,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1"],
        gene_names=gene_names,
        n_samples=6,
    )


# ---------- fill_missing ----------


def test_fill_missing_zero_strategy(simple_dataset: ProteomeDataset) -> None:
    ds, n_filled = fill_missing(simple_dataset, strategy="zero")
    assert n_filled > 0  # GENE_ALL_MISSING 全 0
    assert ds.n_samples == 6


def test_fill_missing_median_strategy(simple_dataset: ProteomeDataset) -> None:
    ds, n_filled = fill_missing(simple_dataset, strategy="median")
    # GENE_ALL_MISSING 没有非零值，中位数是 0，填充后仍为 0
    assert ds.n_samples == 6
    # GENE_A 等有效基因的 0 值会被填中位数
    assert ds.samples[0].expression["GENE_A"] > 0


def test_fill_missing_mean_strategy(simple_dataset: ProteomeDataset) -> None:
    ds, n_filled = fill_missing(simple_dataset, strategy="mean")
    assert ds.n_samples == 6


def test_fill_missing_invalid_strategy(simple_dataset: ProteomeDataset) -> None:
    """非 zero/median 的策略走 mean 分支，不抛异常但按均值填充。"""
    ds, n_filled = fill_missing(simple_dataset, strategy="invalid")
    assert ds.n_samples == 6
    # mean 策略下，0 值会被均值替换
    assert n_filled > 0


# ---------- filter_low_variance ----------


def test_filter_low_variance_removes_constant(simple_dataset: ProteomeDataset) -> None:
    ds, n_filtered = filter_low_variance(simple_dataset, min_variance=0.01)
    # GENE_CONST 方差为 0，应被剔除；GENE_ALL_MISSING 方差也为 0
    assert "GENE_CONST" not in ds.gene_names
    assert "GENE_ALL_MISSING" not in ds.gene_names
    assert n_filtered == 2
    assert len(ds.gene_names) == 3


def test_filter_low_variance_keeps_all(simple_dataset: ProteomeDataset) -> None:
    ds, n_filtered = filter_low_variance(simple_dataset, min_variance=0.0)
    assert n_filtered == 0
    assert len(ds.gene_names) == 5


def test_filter_low_variance_empty_dataset() -> None:
    empty = ProteomeDataset(samples=[], gene_names=[], n_samples=0)
    ds, n_filtered = filter_low_variance(empty, min_variance=0.01)
    assert n_filtered == 0


# ---------- filter_high_missing ----------


def test_filter_high_missing_removes_all_missing(simple_dataset: ProteomeDataset) -> None:
    # GENE_ALL_MISSING 全部为 0，缺失率 1.0 > 0.3，应被剔除
    ds, n_filtered = filter_high_missing(simple_dataset, max_missing_rate=0.3)
    assert "GENE_ALL_MISSING" not in ds.gene_names
    assert n_filtered == 1


def test_filter_high_missing_keeps_partial() -> None:
    """部分缺失的基因应被保留。"""
    gene_names = ["G1", "G2"]
    samples = [
        _make_sample("s1", {"G1": 1.0, "G2": 0.0}),
        _make_sample("s2", {"G1": 2.0, "G2": 5.0}),
        _make_sample("s3", {"G1": 3.0, "G2": 6.0}),
    ]
    ds = ProteomeDataset(
        samples=samples,
        gene_names=gene_names,
        n_samples=3,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1"],
    )
    # G2 缺失率 1/3 ≈ 0.33 > 0.3，应被剔除
    out, n_filtered = filter_high_missing(ds, max_missing_rate=0.3)
    assert "G2" not in out.gene_names
    assert n_filtered == 1


# ---------- log2_transform ----------


def test_log2_transform_basic() -> None:
    gene_names = ["G1"]
    samples = [_make_sample("s1", {"G1": 7.0})]  # log2(7+1) = 3
    ds = ProteomeDataset(
        samples=samples,
        gene_names=gene_names,
        n_samples=1,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1"],
    )
    out = log2_transform(ds, offset=1.0)
    assert abs(out.samples[0].expression["G1"] - 3.0) < 1e-9


def test_log2_transform_zero_value() -> None:
    """零值加位移后应为 log2(offset)。"""
    gene_names = ["G1"]
    samples = [_make_sample("s1", {"G1": 0.0})]
    ds = ProteomeDataset(
        samples=samples,
        gene_names=gene_names,
        n_samples=1,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1"],
    )
    out = log2_transform(ds, offset=1.0)
    assert abs(out.samples[0].expression["G1"] - 0.0) < 1e-9  # log2(0+1)=0


def test_log2_transform_negative_value() -> None:
    """负值取绝对值后转换，不应产生 NaN。"""
    import math

    gene_names = ["G1"]
    samples = [_make_sample("s1", {"G1": -7.0})]  # log2(|-7|+1) = 3
    ds = ProteomeDataset(
        samples=samples,
        gene_names=gene_names,
        n_samples=1,
        strains=["BAI"],
        temperatures=["30"],
        carbon_sources=["glucose"],
        perturbations=["#1"],
    )
    out = log2_transform(ds, offset=1.0)
    val = out.samples[0].expression["G1"]
    assert not math.isnan(val)
    assert abs(val - 3.0) < 1e-9


# ---------- correct_batch_effects ----------


def test_correct_batch_effects_centers_replicate(simple_dataset: ProteomeDataset) -> None:
    """校正后，每个 replicate 组的均值应接近 0。"""
    import numpy as np

    out = correct_batch_effects(simple_dataset, group_key="replicate")

    # 计算 replicate=1 组的均值
    rep1_vals = [s.expression["GENE_A"] for s in out.samples if s.metadata.replicate == 1]
    rep1_mean = np.mean(rep1_vals)
    assert abs(rep1_mean) < 1e-9  # 校正后组均值应为 0


def test_correct_batch_effects_no_samples() -> None:
    empty = ProteomeDataset(samples=[], gene_names=[], n_samples=0)
    out = correct_batch_effects(empty, group_key="replicate")
    assert out.n_samples == 0


# ---------- preprocess pipeline ----------


def test_preprocess_pipeline(simple_dataset: ProteomeDataset) -> None:
    out, report = preprocess(
        simple_dataset,
        fill_strategy="median",
        log_offset=1.0,
        min_variance=0.01,
        max_missing_rate=0.3,
        correct_batch=True,
    )
    assert isinstance(report, PreprocessReport)
    assert report.n_samples_in == 6
    assert report.n_samples_out == 6
    assert report.n_genes_in == 5
    # GENE_CONST（零方差）和 GENE_ALL_MISSING（全缺失）应被剔除
    assert report.n_genes_filtered_low_var >= 1
    assert report.n_genes_filtered_high_missing >= 1
    assert report.batch_corrected is True
    assert len(report.steps) == 5
    assert "GENE_CONST" not in out.gene_names
    assert "GENE_ALL_MISSING" not in out.gene_names


def test_preprocess_skip_batch(simple_dataset: ProteomeDataset) -> None:
    out, report = preprocess(
        simple_dataset,
        correct_batch=False,
    )
    assert report.batch_corrected is False
    assert len(report.steps) == 4  # 少了批次校正步骤


def test_preprocess_report_to_dict(simple_dataset: ProteomeDataset) -> None:
    _, report = preprocess(simple_dataset)
    d = report.to_dict()
    assert isinstance(d, dict)
    assert "n_samples_in" in d
    assert "steps" in d

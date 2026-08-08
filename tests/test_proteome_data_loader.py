"""T1.1 WAYB/WAYC 数据加载器测试。

遵循 `.trae/rules/00-project-rules.md` 第 3.4 节测试规范：
- 外部数据用 fixture/mock，不依赖真实数据文件
- 覆盖加载、过滤、聚合等核心逻辑
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.proteome.data_loader import (
    _parse_expression_row,
    _parse_metadata_row,
    _resolve_file,
    compute_strain_conditions,
    get_expression_matrix,
    get_samples_by_split,
    get_samples_by_strain,
    load_wayb_wayc,
)
from src.proteome.schemas import (
    BioCandidate,
    ProteomeDataset,
    ProteomeSample,
    SampleMetadata,
    StrainCondition,
)

# ---------- Fixtures ----------


def _make_metadata_rows(n: int = 6) -> list[dict[str, Any]]:
    """生成 mock metadata 行。"""
    strains = ["BAI", "BAH", "DHY210"]
    temps = ["30", "37"]
    carbons = ["glucose", "galactose"]
    splits = ["train", "val_strain_only"]
    rows = []
    for i in range(n):
        rows.append(
            {
                "sample_id": f"s_{i:04d}",
                "strain": strains[i % len(strains)],
                "temperature": temps[i % len(temps)],
                "carbon_source": carbons[i % len(carbons)],
                "pert_id": f"#{(i % 3) + 1}",
                "time_point": 0.0,
                "split": splits[i % len(splits)],
                "replicate": (i % 2) + 1,
                "extra_col": f"extra_{i}",
            }
        )
    return rows


def _make_proteome_rows(n: int = 6, n_genes: int = 50) -> list[dict[str, Any]]:
    """生成 mock proteome 行。"""
    gene_names = [f"GENE_{j:04d}" for j in range(n_genes)]
    rows = []
    for i in range(n):
        row: dict[str, Any] = {"sample_id": f"s_{i:04d}"}
        for g in gene_names:
            row[g] = float(i * 0.1 + hash(g) % 100 / 100.0)
        rows.append(row)
    return rows


@pytest.fixture
def mock_csv_dir(tmp_path: Path) -> Path:
    """创建临时 mock CSV 文件。"""
    meta_rows = _make_metadata_rows(6)
    prot_rows = _make_proteome_rows(6, n_genes=50)

    meta_df = pd.DataFrame(meta_rows)
    prot_df = pd.DataFrame(prot_rows)

    meta_path = tmp_path / "metadata.csv"
    prot_path = tmp_path / "proteome.csv"
    meta_df.to_csv(meta_path, index=False)
    prot_df.to_csv(prot_path, index=False)
    return tmp_path


@pytest.fixture
def simple_dataset() -> ProteomeDataset:
    """构建内存 mock 数据集（不依赖 CSV）。"""
    gene_names = [f"GENE_{j:04d}" for j in range(10)]
    samples: list[ProteomeSample] = []
    for i in range(6):
        meta = SampleMetadata(
            sample_id=f"s_{i:04d}",
            strain=["BAI", "BAH", "DHY210"][i % 3],
            temperature=["30", "37"][i % 2],
            carbon_source=["glucose", "galactose"][i % 2],
            pert_id=f"#{(i % 3) + 1}",
            time_point=0.0,
            split=["train", "val_strain_only"][i % 2],
            replicate=(i % 2) + 1,
        )
        expr = {g: float(i + j * 0.1) for j, g in enumerate(gene_names)}
        samples.append(
            ProteomeSample(
                metadata=meta,
                expression=expr,
                n_features=len(expr),
            )
        )
    return ProteomeDataset(
        samples=samples,
        strains=["BAI", "BAH", "DHY210"],
        temperatures=["30", "37"],
        carbon_sources=["glucose", "galactose"],
        perturbations=["#1", "#2", "#3"],
        gene_names=gene_names,
        n_samples=len(samples),
    )


# ---------- _resolve_file ----------


def test_resolve_file_success(mock_csv_dir: Path) -> None:
    meta_path, prot_path = _resolve_file(mock_csv_dir)
    assert meta_path.exists()
    assert prot_path.exists()
    assert meta_path.name == "metadata.csv"
    assert prot_path.name == "proteome.csv"


def test_resolve_file_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _resolve_file(tmp_path)


# ---------- _parse_metadata_row ----------


def test_parse_metadata_row_basic() -> None:
    row = {
        "sample_id": "s_0001",
        "strain": "BAI",
        "temperature": "30",
        "carbon_source": "Glucose",
        "pert_id": "#1",
        "time_point": "2.5",
        "split": "train",
        "replicate": "2",
        "extra_info": "test",
    }
    meta = _parse_metadata_row(row)
    assert meta.sample_id == "s_0001"
    assert meta.strain == "BAI"
    assert meta.temperature == "30"
    assert meta.carbon_source == "glucose"
    assert meta.pert_id == "#1"
    assert meta.time_point == 2.5
    assert meta.split == "train"
    assert meta.replicate == 2
    assert "extra_info" in meta.extra


def test_parse_metadata_row_defaults() -> None:
    row = {"sample_id": "s_0001", "strain": "BAI", "temperature": "30"}
    meta = _parse_metadata_row(row)
    assert meta.carbon_source == ""
    assert meta.pert_id == ""


# ---------- _parse_expression_row ----------


def test_parse_expression_row_basic() -> None:
    gene_names = ["GENE_A", "GENE_B", "GENE_C"]
    row = {"GENE_A": "1.5", "GENE_B": "2.3", "GENE_C": "NA"}
    expr = _parse_expression_row(row, gene_names)
    assert expr["GENE_A"] == 1.5
    assert expr["GENE_B"] == 2.3
    assert expr["GENE_C"] == 0.0


def test_parse_expression_row_missing_values() -> None:
    gene_names = ["GENE_A", "GENE_B"]
    row = {}
    expr = _parse_expression_row(row, gene_names)
    assert expr["GENE_A"] == 0.0
    assert expr["GENE_B"] == 0.0


# ---------- load_wayb_wayc ----------


def test_load_wayb_wayc_full(mock_csv_dir: Path) -> None:
    dataset = load_wayb_wayc(mock_csv_dir)
    assert dataset.n_samples == 6
    assert len(dataset.strains) > 0
    assert len(dataset.gene_names) == 50


def test_load_wayb_wayc_split_filter(mock_csv_dir: Path) -> None:
    dataset = load_wayb_wayc(mock_csv_dir, splits="train")
    for sample in dataset.samples:
        assert sample.metadata.split == "train"


def test_load_wayb_wayc_multi_split(mock_csv_dir: Path) -> None:
    dataset = load_wayb_wayc(mock_csv_dir, splits=["train", "val_strain_only"])
    assert dataset.n_samples == 6


def test_load_wayb_wayc_single_split_string(mock_csv_dir: Path) -> None:
    dataset = load_wayb_wayc(mock_csv_dir, splits="val_strain_only")
    assert dataset.n_samples > 0
    for sample in dataset.samples:
        assert sample.metadata.split == "val_strain_only"


# ---------- compute_strain_conditions ----------


def test_compute_strain_conditions(simple_dataset: ProteomeDataset) -> None:
    conditions = compute_strain_conditions(simple_dataset)
    assert len(conditions) > 0
    for cond in conditions:
        assert isinstance(cond, StrainCondition)
        assert cond.n_replicates > 0
        assert len(cond.sample_ids) == cond.n_replicates


# ---------- get_samples_by_strain / get_samples_by_split ----------


def test_get_samples_by_strain(simple_dataset: ProteomeDataset) -> None:
    bai_samples = get_samples_by_strain(simple_dataset, "BAI")
    assert len(bai_samples) > 0
    for s in bai_samples:
        assert s.metadata.strain == "BAI"


def test_get_samples_by_split(simple_dataset: ProteomeDataset) -> None:
    train_samples = get_samples_by_split(simple_dataset, "train")
    assert len(train_samples) > 0
    for s in train_samples:
        assert s.metadata.split == "train"


# ---------- get_expression_matrix ----------


def test_get_expression_matrix_full(simple_dataset: ProteomeDataset) -> None:
    sample_ids, matrix = get_expression_matrix(simple_dataset)
    assert len(sample_ids) == simple_dataset.n_samples
    assert len(matrix) == simple_dataset.n_samples
    assert all(len(row) == len(simple_dataset.gene_names) for row in matrix)


def test_get_expression_matrix_subset(simple_dataset: ProteomeDataset) -> None:
    genes = simple_dataset.gene_names[:3]
    sample_ids, matrix = get_expression_matrix(simple_dataset, gene_names=genes)
    assert all(len(row) == 3 for row in matrix)


# ---------- ProteomeDataset ----------


def test_proteome_dataset_get_strain_conditions(
    simple_dataset: ProteomeDataset,
) -> None:
    conditions = simple_dataset.get_strain_conditions()
    assert len(conditions) > 0
    for cond in conditions:
        assert cond.strain in ["BAI", "BAH", "DHY210"]


# ---------- BioCandidate ----------


def test_bio_candidate_score_avg() -> None:
    cand = BioCandidate(
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
        pert_id="#1",
        formula="BAI_30C_glucose_#1",
        scores={"scientific": 0.8, "feasibility": 0.6, "support": 0.7},
    )
    assert abs(cand.score_avg() - 0.7) < 1e-9


def test_bio_candidate_score_avg_empty() -> None:
    cand = BioCandidate(
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
        formula="BAI_30C_glucose",
    )
    assert cand.score_avg() == 0.0


def test_bio_candidate_to_dict() -> None:
    cand = BioCandidate(
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
        formula="BAI_30C_glucose",
    )
    d = cand.to_dict()
    assert isinstance(d, dict)
    assert d["strain"] == "BAI"
    assert "formula" in d


# ---------- ProteomeSample ----------


def test_proteome_sample_to_vector_ordered() -> None:
    gene_names = ["A", "B", "C"]
    expr = {"A": 1.0, "B": 2.0, "C": 3.0}
    meta = SampleMetadata(
        sample_id="test",
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
    )
    sample = ProteomeSample(metadata=meta, expression=expr, n_features=3)
    vec = sample.to_vector(gene_order=gene_names)
    assert vec == [1.0, 2.0, 3.0]


def test_proteome_sample_to_vector_unordered() -> None:
    expr = {"A": 1.0, "B": 2.0}
    meta = SampleMetadata(
        sample_id="test",
        strain="BAI",
        temperature="30",
        carbon_source="glucose",
    )
    sample = ProteomeSample(metadata=meta, expression=expr, n_features=2)
    vec = sample.to_vector()
    assert set(vec) == {1.0, 2.0}

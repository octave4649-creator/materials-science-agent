"""WAYB/WAYC 数据集划分验证器。

对齐 `.trae/rules/00-project-rules.md` 第 5.3 节样本划分规范：
- train(5920) / val_strain_only(1547) / val_chem_only(1065) /
  val_both(269) / val_time(157) / test(4454)
- 5 种菌株：BAI、BAH、DHY210、CEK、CGD
- 验证划分正确性：互斥性、覆盖率、分布一致性

验证内容：
1. 划分互斥性：每个样本只属于一个 split
2. 划分覆盖率：所有样本都被分配到合法 split
3. 菌株分布：每个 split 中的菌株分布是否符合预期（val_strain_only 含未训练菌株）
4. 化学扰动分布：val_chem_only 含未训练扰动
5. 数据泄漏检测：train 与 test 之间不应有相同的 (strain, pert_id) 组合
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.common.logging import AuditLogger
from src.proteome.schemas import ProteomeDataset

logger = AuditLogger("proteome_split_validator")

# 合法 split 名称（对齐 00-project-rules.md 第 5.3 节）
VALID_SPLITS: tuple[str, ...] = (
    "train",
    "val_strain_only",
    "val_chem_only",
    "val_both",
    "val_time",
    "test",
)

# 预期划分样本数（对齐数据集说明）
EXPECTED_SPLIT_COUNTS: dict[str, int] = {
    "train": 5920,
    "val_strain_only": 1547,
    "val_chem_only": 1065,
    "val_both": 269,
    "val_time": 157,
    "test": 4454,
}


@dataclass
class SplitReport:
    """划分验证报告。"""

    n_samples: int = 0
    n_valid_splits: int = 0
    n_invalid_splits: int = 0
    split_counts: dict[str, int] = field(default_factory=dict)
    n_missing_split: int = 0
    strain_distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    pert_distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    leakage_pairs: list[tuple[str, str]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_samples": self.n_samples,
            "n_valid_splits": self.n_valid_splits,
            "n_invalid_splits": self.n_invalid_splits,
            "split_counts": self.split_counts,
            "n_missing_split": self.n_missing_split,
            "strain_distribution": self.strain_distribution,
            "pert_distribution": self.pert_distribution,
            "leakage_pairs": self.leakage_pairs,
            "issues": self.issues,
            "is_valid": self.is_valid,
        }


def validate_splits(
    dataset: ProteomeDataset,
    expected_counts: dict[str, int] | None = None,
    check_leakage: bool = True,
) -> SplitReport:
    """验证数据集划分正确性。

    Args:
        dataset: 已加载的数据集。
        expected_counts: 预期样本数（None 用默认 EXPECTED_SPLIT_COUNTS）。
        check_leakage: 是否检测 train/test 数据泄漏。

    Returns:
        SplitReport 验证报告。
    """
    start = time.perf_counter()
    expected = expected_counts or EXPECTED_SPLIT_COUNTS
    report = SplitReport(n_samples=dataset.n_samples)

    # Step 1: 统计划分
    split_counts: dict[str, int] = {}
    invalid_splits: list[str] = []
    missing_split = 0

    for sample in dataset.samples:
        split = sample.metadata.split
        if not split:
            missing_split += 1
            continue
        if split not in VALID_SPLITS:
            invalid_splits.append(split)
            continue
        split_counts[split] = split_counts.get(split, 0) + 1

    report.split_counts = split_counts
    report.n_valid_splits = sum(split_counts.values())
    report.n_invalid_splits = len(invalid_splits)
    report.n_missing_split = missing_split

    if invalid_splits:
        report.issues.append(f"发现 {len(invalid_splits)} 个非法 split 名称: {set(invalid_splits)}")
        report.is_valid = False

    if missing_split > 0:
        report.issues.append(f"{missing_split} 个样本未分配 split")
        report.is_valid = False

    # Step 2: 与预期样本数比较（容差 20%）
    for split_name, expected_count in expected.items():
        actual = split_counts.get(split_name, 0)
        if actual == 0:
            report.issues.append(f"split '{split_name}' 缺失（预期 {expected_count}）")
            report.is_valid = False
        elif abs(actual - expected_count) / expected_count > 0.2:
            report.issues.append(
                f"split '{split_name}' 样本数 {actual} 与预期 {expected_count} 偏差 > 20%"
            )

    # Step 3: 菌株分布（每个 split 的菌株分布）
    strain_dist: dict[str, dict[str, int]] = {}
    for sample in dataset.samples:
        split = sample.metadata.split
        strain = sample.metadata.strain
        if split not in strain_dist:
            strain_dist[split] = {}
        strain_dist[split][strain] = strain_dist[split].get(strain, 0) + 1
    report.strain_distribution = strain_dist

    # Step 4: 化学扰动分布
    pert_dist: dict[str, dict[str, int]] = {}
    for sample in dataset.samples:
        split = sample.metadata.split
        pert = sample.metadata.pert_id
        if not pert:
            continue
        if split not in pert_dist:
            pert_dist[split] = {}
        pert_dist[split][pert] = pert_dist[split].get(pert, 0) + 1
    report.pert_distribution = pert_dist

    # Step 5: 数据泄漏检测（train 与 test 的 (strain, pert_id) 交集）
    if check_leakage:
        train_pairs = {
            (s.metadata.strain, s.metadata.pert_id)
            for s in dataset.samples
            if s.metadata.split == "train" and s.metadata.pert_id
        }
        test_pairs = {
            (s.metadata.strain, s.metadata.pert_id)
            for s in dataset.samples
            if s.metadata.split == "test" and s.metadata.pert_id
        }
        leakage = train_pairs & test_pairs
        report.leakage_pairs = list(leakage)[:20]  # 最多记录前 20 个
        if leakage:
            report.issues.append(
                f"检测到 {len(leakage)} 个 train/test 数据泄漏 (strain, pert_id) 对"
            )
            report.is_valid = False

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.log(
        "validate_splits_complete",
        "success" if report.is_valid else "warning",
        output_summary=report.to_dict(),
        duration_ms=elapsed_ms,
    )
    return report


def check_strain_split_consistency(
    dataset: ProteomeDataset,
) -> dict[str, Any]:
    """检查 val_strain_only 是否包含未在 train 出现的菌株。

    val_strain_only 的设计意图：验证模型对未训练菌株的泛化能力，
    因此应包含 train 中未出现的菌株。

    Args:
        dataset: 数据集。

    Returns:
        包含 train_strains、val_strain_only_strains、unique_val_strains 的字典。
    """
    train_strains: set[str] = set()
    val_strain_strains: set[str] = set()

    for sample in dataset.samples:
        if sample.metadata.split == "train":
            train_strains.add(sample.metadata.strain)
        elif sample.metadata.split == "val_strain_only":
            val_strain_strains.add(sample.metadata.strain)

    unique_val_strains = val_strain_strains - train_strains

    result = {
        "train_strains": sorted(train_strains),
        "val_strain_only_strains": sorted(val_strain_strains),
        "unique_val_strains": sorted(unique_val_strains),
        "is_consistent": len(unique_val_strains) > 0,
    }

    logger.log(
        "check_strain_split_consistency",
        "success" if result["is_consistent"] else "warning",
        output_summary=result,
    )
    return result


def check_pert_split_consistency(
    dataset: ProteomeDataset,
) -> dict[str, Any]:
    """检查 val_chem_only 是否包含未在 train 出现的化学扰动。

    val_chem_only 的设计意图：验证模型对未训练化学扰动的泛化能力。

    Args:
        dataset: 数据集。

    Returns:
        包含 train_perts、val_chem_only_perts、unique_val_perts 的字典。
    """
    train_perts: set[str] = set()
    val_chem_perts: set[str] = set()

    for sample in dataset.samples:
        if not sample.metadata.pert_id:
            continue
        if sample.metadata.split == "train":
            train_perts.add(sample.metadata.pert_id)
        elif sample.metadata.split == "val_chem_only":
            val_chem_perts.add(sample.metadata.pert_id)

    unique_val_perts = val_chem_perts - train_perts

    result = {
        "train_perts_count": len(train_perts),
        "val_chem_only_perts_count": len(val_chem_perts),
        "unique_val_perts_count": len(unique_val_perts),
        "unique_val_perts": sorted(unique_val_perts),
        "is_consistent": len(unique_val_perts) > 0,
    }

    logger.log(
        "check_pert_split_consistency",
        "success" if result["is_consistent"] else "warning",
        output_summary=result,
    )
    return result


def generate_split_summary(report: SplitReport) -> str:
    """生成人类可读的划分验证摘要。

    Args:
        report: 验证报告。

    Returns:
        Markdown 格式的摘要文本。
    """
    lines: list[str] = []
    lines.append("# 数据集划分验证报告\n")
    lines.append(f"## 总样本数：{report.n_samples}\n")

    lines.append("## 各划分样本数\n")
    lines.append("| Split | 样本数 | 预期 | 偏差 |")
    lines.append("|-------|--------|------|------|")
    for split in VALID_SPLITS:
        actual = report.split_counts.get(split, 0)
        expected = EXPECTED_SPLIT_COUNTS.get(split, 0)
        diff = actual - expected
        pct = f"{diff / expected * 100:.1f}%" if expected > 0 else "N/A"
        lines.append(f"| {split} | {actual} | {expected} | {pct} |")

    lines.append("\n## 菌株分布\n")
    all_strains = set()
    for strains in report.strain_distribution.values():
        all_strains.update(strains.keys())
    lines.append("| Split | " + " | ".join(sorted(all_strains)) + " |")
    lines.append("|-------|" + "|".join(["-----"] * len(all_strains)) + "|")
    for split in VALID_SPLITS:
        if split in report.strain_distribution:
            row = [str(report.strain_distribution[split].get(s, 0)) for s in sorted(all_strains)]
            lines.append(f"| {split} | " + " | ".join(row) + " |")

    if report.leakage_pairs:
        lines.append(f"\n## ⚠️ 数据泄漏：{len(report.leakage_pairs)} 个 train/test 重复对\n")
    else:
        lines.append("\n## ✅ 无 train/test 数据泄漏\n")

    if report.issues:
        lines.append("\n## ⚠️ 问题清单\n")
        for issue in report.issues:
            lines.append(f"- {issue}")

    lines.append(f"\n## 验证结论：{'✅ 通过' if report.is_valid else '⚠️ 有问题需关注'}\n")

    return "\n".join(lines)

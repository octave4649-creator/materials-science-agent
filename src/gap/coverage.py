"""覆盖率分析：成分×性能研究矩阵 → 空白格定位（Gap 识别方法 1）。

对齐 `.trae/rules/04-literature-agent.md` 第 4.2.1 节：
统计某材料体系的研究分布（成分×结构×性能矩阵），寻找空白格。
对研究较充分（证据数 ≥ 阈值）但仍缺核心性能的体系标记「未探索方向」。
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from src.extraction.knowledge_base import KnowledgeBase
from src.gap.schemas import GapCandidate

# 热电/半导体系核心性能维度（可扩展，按领域扩展）
KNOWN_PROPS = [
    "figure_of_merit_zT",
    "band_gap",
    "seebeck_coefficient",
    "thermal_conductivity",
    "electrical_conductivity",
    "power_factor",
]

# 性能名别名归一化（LLM 输出与规则式输出不一致时统一）
_PROP_ALIASES = {
    "zt": "figure_of_merit_zT",
    "z t": "figure_of_merit_zT",
    "figure of merit": "figure_of_merit_zT",
    "figure_of_merit": "figure_of_merit_zT",
    "thermoelectric figure of merit": "figure_of_merit_zT",
    "bandgap": "band_gap",
    "band gap": "band_gap",
    "seebeck": "seebeck_coefficient",
    "seebeck coefficient": "seebeck_coefficient",
    "thermal conductivity": "thermal_conductivity",
    "electrical conductivity": "electrical_conductivity",
    "power factor": "power_factor",
    "power_factor": "power_factor",
}


def normalize_prop_name(name: str | None) -> str:
    """性能名归一化：别名/大小写/空格统一为规范名。

    参数:
        name: 原始性能名（如 ``zT`` / ``band gap``）

    返回:
        归一化后的规范性能名（未命中别名时返回小写清洗结果）。
    """
    if not name:
        return ""
    key = re.sub(r"\s+", " ", name.strip().lower())
    return _PROP_ALIASES.get(key, key)


def coverage_matrix(kb: KnowledgeBase) -> dict[str, dict[str, int]]:
    """构建成分×性能研究矩阵。

    参数:
        kb: 知识库

    返回:
        {归一化化学式: {归一化性能名: 证据条数}}。
    """
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entry in kb.entries:
        formula = entry.normalized_formula
        for prop in entry.record.properties:
            key = normalize_prop_name(prop.name)
            if key:
                matrix[formula][key] += 1
    return dict(matrix)


def find_blank_cells(
    kb: KnowledgeBase,
    *,
    min_evidence: int = 2,
    max_gaps: int = 10,
) -> list[GapCandidate]:
    """定位空白格：研究较充分但缺核心性能的体系。

    参数:
        kb: 知识库
        min_evidence: 体系至少具备的证据数（防单篇噪声）
        max_gaps: 返回的最大 Gap 数

    返回:
        未探索方向 Gap 候选列表（置信度较低，待 LLM 验证）。
    """
    # 证据数统计：体系 → 证据 doc_id 数
    n_evidence: dict[str, int] = defaultdict(int)
    for entry in kb.entries:
        n_evidence[entry.normalized_formula] += len(entry.evidence_ids) or 1

    matrix = coverage_matrix(kb)
    gaps: list[GapCandidate] = []
    for formula, props in matrix.items():
        if n_evidence.get(formula, 0) < min_evidence:
            continue
        studied = set(props)
        missing = [p for p in KNOWN_PROPS if p not in studied]
        if not missing:
            continue
        gaps.append(
            GapCandidate(
                gap_type="未探索方向",
                statement=(
                    f"{formula} 已被研究（{n_evidence[formula]} 条证据），"
                    f"但缺乏 {'/'.join(missing)} 的系统研究"
                ),
                rationale=(
                    f"成分空间已有研究基础，性能维度 {'/'.join(missing)} "
                    "存在研究空白，可作路线 A 搜索的候选目标"
                ),
                formulas=[formula],
                evidence_ids=sorted(
                    {
                        e
                        for entry in kb.entries
                        if entry.normalized_formula == formula
                        for e in entry.evidence_ids
                    }
                ),
                novelty="部分已知",
                operability=(
                    f"以 {formula} 为种子，搜索 {'/'.join(missing)} 对应的"
                    "成分-结构-性能关联"
                ),
                confidence=0.5,
                source="coverage",
            )
        )
        if len(gaps) >= max_gaps:
            break
    return gaps


def to_dict_matrix(matrix: dict[str, dict[str, int]]) -> dict[str, Any]:
    """矩阵序列化（审计/报告用）。"""
    return {k: dict(v) for k, v in matrix.items()}

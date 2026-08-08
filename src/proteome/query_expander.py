"""生物材料文献检索关键词与查询扩展。

对齐 `.trae/rules/02-literature-data-sources.md` 第 4.5 节
生物材料/蛋白质组学检索策略，为 RetrievalAgent 提供生物材料领域的
关键词词典、查询模板和子问题生成器。

设计原则：
1. 关键词分类组织（模式生物/组学技术/数据来源/扰动/构效关系/条件控制/数据库）
2. 中英文双语关键词，支持布尔组合
3. 查询模板覆盖核心 Research Gap 方向（温度响应/碳源切换/扰动响应/菌株特异）
4. 与 RetrievalAgent._decompose 兼容，可作为子问题生成器的扩展
"""

from __future__ import annotations

from typing import Any

from src.common.logging import AuditLogger

logger = AuditLogger("proteome_query_expander")

# 生物材料关键词词典（对齐 02-literature-data-sources.md 第 4.5 节表）
KEYWORDS: dict[str, dict[str, list[str]]] = {
    "organism": {
        "en": [
            "Saccharomyces cerevisiae",
            "yeast",
            "S. cerevisiae",
            "budding yeast",
        ],
        "zh": ["酿酒酵母", "酵母", "芽殖酵母"],
    },
    "omics": {
        "en": [
            "proteomics",
            "mass spectrometry",
            "TMT labeling",
            "quantitative proteomics",
            "protein expression",
            "gene expression",
        ],
        "zh": ["蛋白质组学", "质谱", "TMT标记", "定量蛋白质组学", "蛋白表达", "基因表达"],
    },
    "data_source": {
        "en": [
            "WAYB",
            "WAYC",
            "Yeast Proteome Atlas",
            "yeast proteome dataset",
        ],
        "zh": ["WAYB", "WAYC", "酵母蛋白质组图谱", "酵母蛋白质组数据集"],
    },
    "perturbation": {
        "en": [
            "chemical perturbation",
            "drug response",
            "stress response",
            "perturbation",
            "chemical stress",
        ],
        "zh": ["化学扰动", "药物响应", "应激反应", "扰动反应", "化学应激"],
    },
    "structure_property": {
        "en": [
            "gene expression-phenotype",
            "protein-function relationship",
            "strain performance",
            "gene-phenotype association",
            "fitness landscape",
        ],
        "zh": ["基因表达-表型", "蛋白功能关系", "菌株性能", "基因-表型关联", "适应性景观"],
    },
    "condition": {
        "en": [
            "temperature response",
            "heat shock",
            "carbon source",
            "galactose",
            "glucose",
            "metabolic switch",
        ],
        "zh": ["温度响应", "热休克", "碳源", "半乳糖", "葡萄糖", "代谢切换"],
    },
    "database": {
        "en": [
            "Proteome Atlas",
            "UniProt",
            "YeastMine",
            "SGD",
            "Saccharomyces Genome Database",
        ],
        "zh": ["蛋白质组图谱", "UniProt", "YeastMine", "SGD", "酵母基因组数据库"],
    },
}

# 核心 Research Gap 方向（对齐 05-route-a-SPR.md 第 6.4 节）
# 长 Boolean 查询字符串不可拆分，整行加 noqa: E501
GAP_DIRECTIONS: dict[str, dict[str, str]] = {
    "temperature_response": {
        "en": (  # noqa: E501
            '("Saccharomyces cerevisiae" OR yeast) AND (proteomics OR "gene expression")'
            ' AND ("temperature response" OR "heat shock")'
        ),
        "zh": "酵母 蛋白质组学 温度响应 热休克",
        "description": "菌株在 30°C vs 37°C 下的蛋白表达差异模式",
    },
    "carbon_source_switch": {
        "en": (  # noqa: E501
            '("Saccharomyces cerevisiae" OR yeast) AND (proteomics OR "gene expression")'
            ' AND ("carbon source" OR "glucose" OR "galactose")'
            ' AND ("metabolic switch" OR "GAL")'
        ),
        "zh": "酵母 蛋白质组学 碳源 葡萄糖 半乳糖 代谢切换 GAL",
        "description": "葡萄糖→半乳糖切换时的蛋白表达重编程",
    },
    "perturbation_specific": {
        "en": (  # noqa: E501
            '("Saccharomyces cerevisiae" OR yeast) AND'
            ' (proteomics OR "chemical perturbation") AND'
            ' ("drug response" OR "stress response")'
        ),
        "zh": "酵母 蛋白质组学 化学扰动 药物响应 应激反应",
        "description": "同一扰动在不同菌株中的响应差异",
    },
    "strain_specific": {
        "en": (  # noqa: E501
            '("Saccharomyces cerevisiae" OR yeast) AND'
            ' (proteomics OR "strain-specific") AND'
            ' ("genetic background" OR "phenotype")'
        ),
        "zh": "酵母 蛋白质组学 菌株特异 遗传背景 表型",
        "description": "5 种菌株（BAI/BAH/DHY210/CEK/CGD）的遗传背景差异",
    },
    "multi_condition_interaction": {
        "en": (  # noqa: E501
            '("Saccharomyces cerevisiae" OR yeast) AND proteomics AND'
            ' ("temperature" AND "carbon source" AND "chemical perturbation")'
        ),
        "zh": "酵母 蛋白质组学 温度 碳源 化学扰动 多条件交互",
        "description": "温度-碳源-扰动的三方交互效应",
    },
    "protein_family_clustering": {
        "en": (  # noqa: E501
            '("Saccharomyces cerevisiae" OR yeast) AND proteomics AND'
            ' ("heat shock protein" OR "HSP" OR "oxidative stress" OR "DNA repair")'
        ),
        "zh": "酵母 蛋白质组学 热休克蛋白 HSP 氧化应激 DNA修复 蛋白家族",
        "description": "特定功能蛋白家族的协同表达模式",
    },
}


def expand_query(
    base_query: str,
    extra_categories: list[str] | None = None,
    lang: str = "en",
) -> list[str]:
    """扩展基础查询：附加关键词构造布尔组合查询。

    Args:
        base_query: 基础研究问题。
        extra_categories: 额外关键词类别（organism/omics/...）。
        lang: 关键词语言（en/zh）。

    Returns:
        扩展后的查询列表（每个元素是一个布尔组合查询）。
    """
    start_time = __import__("time").perf_counter()

    default_categories = ["organism", "omics"]
    categories = extra_categories or default_categories

    queries: list[str] = []
    for cat in categories:
        if cat not in KEYWORDS:
            continue
        keywords = KEYWORDS[cat].get(lang, [])
        if not keywords:
            continue
        # 用 OR 组合同类关键词，再 AND 基础查询
        kw_block = " OR ".join(f'"{kw}"' for kw in keywords[:3])  # 取前 3 个避免查询过长
        if lang == "en":
            expanded = f"({base_query}) AND ({kw_block})"
        else:
            expanded = f"{base_query} {kw_block}"
        queries.append(expanded)

    elapsed_ms = (__import__("time").perf_counter() - start_time) * 1000
    logger.log(
        "expand_query",
        "success",
        output_summary={
            "base_query": base_query,
            "n_expanded": len(queries),
            "categories": categories,
            "lang": lang,
        },
        duration_ms=elapsed_ms,
    )
    return queries


def generate_gap_queries(
    directions: list[str] | None = None,
    lang: str = "en",
) -> list[dict[str, str]]:
    """生成 Research Gap 方向的检索查询列表。

    Args:
        directions: Gap 方向列表（temperature_response/carbon_source_switch/...），
                    None 时生成全部。
        lang: 查询语言（en/zh）。

    Returns:
        字典列表，每个含 direction/query/description。
    """
    target_directions = directions or list(GAP_DIRECTIONS.keys())

    queries: list[dict[str, str]] = []
    for direction in target_directions:
        if direction not in GAP_DIRECTIONS:
            continue
        info = GAP_DIRECTIONS[direction]
        queries.append(
            {
                "direction": direction,
                "query": info[lang],
                "description": info["description"],
            }
        )

    logger.log(
        "generate_gap_queries",
        "success",
        output_summary={
            "n_queries": len(queries),
            "directions": target_directions,
            "lang": lang,
        },
    )
    return queries


def build_research_question(
    strain: str | None = None,
    temperature: str | None = None,
    carbon_source: str | None = None,
    perturbation: str | None = None,
) -> str:
    """从菌株-条件参数构建自然语言研究问题。

    Args:
        strain: 菌株名（如 BAI），None 时不限定。
        temperature: 温度（如 30/37）。
        carbon_source: 碳源（glucose/galactose）。
        perturbation: 扰动 ID（如 #5）。

    Returns:
        自然语言研究问题字符串。
    """
    parts: list[str] = ["Saccharomyces cerevisiae proteomics"]
    if strain:
        parts.append(f"strain {strain}")
    if temperature:
        parts.append(f"temperature {temperature}°C")
    if carbon_source:
        parts.append(f"carbon source {carbon_source}")
    if perturbation:
        parts.append(f"chemical perturbation {perturbation}")

    return " AND ".join(parts)


def get_keyword_summary() -> dict[str, Any]:
    """返回关键词词典摘要（供 UI/报告展示）。"""
    summary: dict[str, Any] = {}
    for category, langs in KEYWORDS.items():
        summary[category] = {
            "en_count": len(langs.get("en", [])),
            "zh_count": len(langs.get("zh", [])),
            "sample_en": langs.get("en", [])[:3],
            "sample_zh": langs.get("zh", [])[:3],
        }
    summary["_gap_directions"] = list(GAP_DIRECTIONS.keys())
    return summary

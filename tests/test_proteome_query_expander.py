"""T2.x 生物材料查询扩展器测试。"""

from __future__ import annotations

from src.proteome.query_expander import (
    GAP_DIRECTIONS,
    KEYWORDS,
    build_research_question,
    expand_query,
    generate_gap_queries,
    get_keyword_summary,
)

# ---------- KEYWORDS ----------


def test_keywords_has_all_categories() -> None:
    expected_categories = {
        "organism",
        "omics",
        "data_source",
        "perturbation",
        "structure_property",
        "condition",
        "database",
    }
    assert set(KEYWORDS.keys()) == expected_categories


def test_keywords_bilingual() -> None:
    for cat, langs in KEYWORDS.items():
        assert "en" in langs, f"{cat} 缺少英文关键词"
        assert "zh" in langs, f"{cat} 缺少中文关键词"
        assert len(langs["en"]) > 0
        assert len(langs["zh"]) > 0


def test_keywords_yeast_present() -> None:
    assert "Saccharomyces cerevisiae" in KEYWORDS["organism"]["en"]
    assert "酵母" in KEYWORDS["organism"]["zh"]


# ---------- GAP_DIRECTIONS ----------


def test_gap_directions_has_core_directions() -> None:
    core_directions = {
        "temperature_response",
        "carbon_source_switch",
        "perturbation_specific",
        "strain_specific",
    }
    assert core_directions.issubset(set(GAP_DIRECTIONS.keys()))


def test_gap_directions_bilingual() -> None:
    for direction, info in GAP_DIRECTIONS.items():
        assert "en" in info
        assert "zh" in info
        assert "description" in info
        assert len(info["en"]) > 0
        assert len(info["zh"]) > 0


# ---------- expand_query ----------


def test_expand_query_default_categories() -> None:
    queries = expand_query("yeast proteomics")
    # 默认使用 organism + omics
    assert len(queries) == 2
    assert all("yeast proteomics" in q for q in queries)


def test_expand_query_custom_categories() -> None:
    queries = expand_query(
        "temperature response",
        extra_categories=["organism", "condition"],
        lang="en",
    )
    assert len(queries) == 2
    assert any("Saccharomyces cerevisiae" in q for q in queries)
    assert any("temperature" in q.lower() for q in queries)


def test_expand_query_chinese() -> None:
    queries = expand_query("酵母蛋白质组学", extra_categories=["organism"], lang="zh")
    assert len(queries) >= 1
    assert any("酵母" in q for q in queries)


def test_expand_query_invalid_category_skipped() -> None:
    queries = expand_query("test", extra_categories=["invalid_category"])
    assert queries == []


# ---------- generate_gap_queries ----------


def test_generate_gap_queries_all() -> None:
    queries = generate_gap_queries()
    assert len(queries) == len(GAP_DIRECTIONS)
    for q in queries:
        assert "direction" in q
        assert "query" in q
        assert "description" in q


def test_generate_gap_queries_specific_directions() -> None:
    queries = generate_gap_queries(
        directions=["temperature_response", "carbon_source_switch"],
        lang="en",
    )
    assert len(queries) == 2
    directions = {q["direction"] for q in queries}
    assert directions == {"temperature_response", "carbon_source_switch"}


def test_generate_gap_queries_invalid_direction_skipped() -> None:
    queries = generate_gap_queries(directions=["invalid_direction"])
    assert queries == []


def test_generate_gap_queries_chinese() -> None:
    queries = generate_gap_queries(directions=["temperature_response"], lang="zh")
    assert len(queries) == 1
    assert "酵母" in queries[0]["query"]


# ---------- build_research_question ----------


def test_build_research_question_full() -> None:
    q = build_research_question(
        strain="BAI",
        temperature="37",
        carbon_source="galactose",
        perturbation="#5",
    )
    assert "Saccharomyces cerevisiae" in q
    assert "BAI" in q
    assert "37" in q
    assert "galactose" in q
    assert "#5" in q


def test_build_research_question_partial() -> None:
    q = build_research_question(strain="BAI")
    assert "BAI" in q
    assert "temperature" not in q
    assert "carbon source" not in q


def test_build_research_question_empty() -> None:
    q = build_research_question()
    assert "Saccharomyces cerevisiae proteomics" in q


# ---------- get_keyword_summary ----------


def test_get_keyword_summary() -> None:
    summary = get_keyword_summary()
    assert "organism" in summary
    assert "en_count" in summary["organism"]
    assert "zh_count" in summary["organism"]
    assert "sample_en" in summary["organism"]
    assert "_gap_directions" in summary
    assert "temperature_response" in summary["_gap_directions"]

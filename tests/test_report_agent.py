"""报告 Agent 测试：引用去重/证据回映射/自检/渲染/落盘/LLM 降级。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.report_agent import ReportAgent
from src.common.llm import LLMError
from src.extraction.schemas import (
    ExtractionRecord,
    KnowledgeEntry,
    Material,
    PropertyEntry,
)
from src.gap.schemas import GapCandidate, GapReport
from src.report import assembly as asm
from src.report.render import render_html, render_markdown
from src.report.schemas import SECTION_ORDER


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认清空 LLM key（测试规则式摘要降级路径）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


# ---------- 测试数据构造 ----------


def _paper(
    doc_id: str | None,
    *,
    title: str | None = None,
    unique_id: str | None = None,
    authors: list[str] | None = None,
    year: int | None = 2020,
    journal: str = "journal",
    doi: str | None = None,
) -> dict:
    """构造单篇论文 dict（对齐检索输出字段）。"""
    return {
        "doc_id": doc_id,
        "unique_id": unique_id,
        "title": title or f"title-{doc_id or unique_id}",
        "authors": authors or [f"author {doc_id or unique_id}"],
        "year": year,
        "journal": journal,
        "doi": doi,
        "source": "semantic",
    }


def _retrieval(tmp_path: Path, papers: list[dict]) -> Path:
    """构造检索输出 JSON。"""
    path = tmp_path / "retrieval.json"
    path.write_text(
        json.dumps(
            {
                "query": "thermoelectric doping zT",
                "sub_queries": ["thermoelectric doping zT"],
                "total_found": len(papers),
                "papers": papers,
                "generated_at": "2026-08-04T00:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _kb(tmp_path: Path, formulas: list[str]) -> Path:
    """构造含证据条目的知识库文件。"""
    kb = asm.KnowledgeBase(path=tmp_path / "kb.json")
    for i, formula in enumerate(formulas):
        rec = ExtractionRecord(
            material=Material(formula=formula),
            properties=[PropertyEntry(name="zT", value=1.0, unit=None)],
        )
        kb.entries.append(
            KnowledgeEntry(
                record=rec,
                evidence_ids=[f"doc{i}"],
                normalized_formula=formula,
            )
        )
    kb.save()
    return kb.path


def _gaps(tmp_path: Path, *, domain: str = "thermoelectric") -> Path:
    """构造 Gap 报告 JSON（1 条带证据 Gap）。"""
    report = GapReport(
        domain=domain,
        n_entries=1,
        gaps=[
            GapCandidate(
                gap_type="未探索方向",
                statement="PbTe 带隙与掺杂浓度的关联未被系统研究",
                rationale="覆盖率分析发现性能维度空白",
                formulas=["PbTe"],
                evidence_ids=["doc0"],
                novelty="新知",
                operability="以 PbTe 为种子搜索带隙-掺杂关联",
                confidence=0.8,
            )
        ],
    )
    path = tmp_path / "gaps.json"
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    return path


def _build_doc(tmp_path: Path) -> asm.ReportDocument:
    """组装一份完整报告（1 篇文献 + 1 条知识 + 1 条 Gap）。"""
    papers = [_paper("doc0", title="PbTe doping", doi="10.1/x")]
    kb = asm.KnowledgeBase(path=_kb(tmp_path, ["PbTe"]))
    gaps = asm.load_gaps(_gaps(tmp_path))
    return asm.build_document(
        papers=papers,
        kb=kb,
        gaps_report=gaps,
        question="thermoelectric doping zT",
        sub_queries=["thermoelectric doping zT"],
        generated_at="2026-08-04T00:00:00+00:00",
        total_found=1,
        input_hashes={"retrieval": "abc", "kb": "def", "gaps": "ghi"},
    )


# ---------- 引用去重与清洗 ----------


def test_build_references_dedupe() -> None:
    """三级去重键：doc_id > unique_id > 归一化标题。"""
    papers = [
        _paper("d1", title="PbTe doping", unique_id="uid:1"),
        _paper("d1", title="PbTe doping dup", unique_id="uid:1"),  # 同 doc_id 去重
        _paper(None, unique_id="uid:2", title="Bi2Te3"),  # 无 doc_id，unique_id 键
        _paper(None, unique_id=None, title="SnTe"),  # 纯标题键
        _paper(None, unique_id=None, title="SnTe"),  # 标题去重
    ]
    refs, doc_to_ref = asm.build_references(papers)
    assert len(refs) == 3
    assert doc_to_ref == {"d1": 1}
    assert [r.index for r in refs] == [1, 2, 3]


def test_clean_authors_dedupe_keep_order() -> None:
    """作者清洗：去重保序，超限补 et al.。"""
    authors = ["j. shuai", "x. tan", "j. shuai", "q. guo", "x. tan"]
    assert asm.clean_authors(authors, max_show=2) == "j. shuai, x. tan, et al."
    assert asm.clean_authors(None) == "N/A"
    assert asm.clean_authors("single") == "single"


def test_paper_ref_fmt() -> None:
    """参考文献 GB/T 风格格式化。"""
    ref = asm.PaperRef(
        index=1,
        title="PbTe doping",
        authors="j. shuai",
        year=2019,
        journal="materials today physics",
        doi="10.1/x",
        doc_id="d1",
        source="semantic",
    )
    out = ref.fmt()
    assert out.startswith("j. shuai. (2019). PbTe doping")
    assert "DOI: 10.1/x" in out


# ---------- Gap 证据回映射 ----------


def test_section_gaps_evidence_mapping() -> None:
    """Gap 证据 doc_id → 引用编号 [n] 回映射。"""
    papers = [
        _paper("doc0", title="PbTe A"),
        _paper("doc1", title="PbTe B"),
    ]
    _, doc_to_ref = asm.build_references(papers)
    assert doc_to_ref == {"doc0": 1, "doc1": 2}
    report = GapReport(
        gaps=[
            GapCandidate(
                gap_type="未探索方向",
                statement="PbTe 带隙研究不足",
                evidence_ids=["doc0", "doc1"],
                novelty="新知",
            )
        ]
    )
    content, refs_used = asm.section_gaps(report, doc_to_ref)
    assert "[1]" in content and "[2]" in content
    assert "2 条" in content
    assert refs_used == [1, 2]


def test_section_gaps_evidence_unresolved() -> None:
    """证据 doc_id 未在参考文献中 → 只显示条数，不产生引用编号。"""
    report = GapReport(
        gaps=[
            GapCandidate(
                gap_type="未探索方向",
                statement="x",
                evidence_ids=["missing_doc"],
                novelty="已知",
            )
        ]
    )
    content, refs_used = asm.section_gaps(report, {})
    assert "1 条证据" in content
    assert refs_used == []


# ---------- 自检清单 ----------


def test_self_check_all_pass(tmp_path: Path) -> None:
    """完整数据下自检 6 项全部通过。"""
    doc = _build_doc(tmp_path)
    checks = doc.meta.self_check
    for key in (
        "sections_complete",
        "abstract_nonempty",
        "extraction_has_rows",
        "refs_resolved",
        "gaps_evidence_linked",
        "references_complete",
    ):
        assert checks[key], f"自检项 {key} 应通过: {checks}"


def test_self_check_empty_kb(tmp_path: Path) -> None:
    """知识库为空 → extraction_has_rows 失败（如实反映数据缺失）。"""
    papers = [_paper("doc0")]
    kb = asm.KnowledgeBase(path=tmp_path / "empty_kb.json")
    gaps = asm.load_gaps(_gaps(tmp_path))
    doc = asm.build_document(
        papers=papers,
        kb=kb,
        gaps_report=gaps,
        question="q",
        sub_queries=["q"],
        generated_at="t",
        total_found=1,
        input_hashes={},
    )
    assert doc.meta.self_check["sections_complete"] is True
    assert doc.meta.self_check["extraction_has_rows"] is False


# ---------- 渲染 ----------


def test_render_markdown_structure(tmp_path: Path) -> None:
    """Markdown：标题 + 全部章节按 SECTION_ORDER 顺序出现。"""
    doc = _build_doc(tmp_path)
    md = render_markdown(doc)
    assert md.startswith(f"# {doc.title}")
    order = [s.title for s in doc.sections]
    pos = [md.index(f"## {t}") for t in order]
    assert pos == sorted(pos)  # 顺序递增


def test_render_html_structure(tmp_path: Path) -> None:
    """HTML：DOCTYPE + h1/h2 标题 + 表格渲染。"""
    doc = _build_doc(tmp_path)
    html = render_html(doc)
    assert html.startswith("<!DOCTYPE html>")
    assert f"<h1>{doc.title}</h1>" in html
    assert f"<h2>{doc.sections[1].title}</h2>" in html
    assert "<table>" in html and "<th>化学式</th>" in html


# ---------- ReportAgent 端到端 ----------


def test_report_agent_run_no_llm(tmp_path: Path) -> None:
    """无 LLM：规则摘要降级，md/html/meta 落盘，版本快照存在。"""
    out = tmp_path / "out"
    agent = ReportAgent(
        retrieval_path=_retrieval(tmp_path, [_paper("doc0", title="PbTe A", doi="10.1/x")]),
        kb_path=_kb(tmp_path, ["PbTe"]),
        gaps_path=_gaps(tmp_path),
        output_dir=out,
    )
    result = agent.run(use_llm=False)
    assert result.llm_abstract is False
    assert result.md_path and result.md_path.is_file()
    assert result.html_path and result.html_path.is_file()
    assert result.meta_path and result.meta_path.is_file()
    doc = result.document
    assert [s.key for s in doc.sections] == SECTION_ORDER
    assert doc.meta.self_check["sections_complete"]
    assert doc.meta.input_hashes  # 版本快照非空
    assert doc.meta.n_papers == 1 and doc.meta.n_gaps == 1


def test_llm_abstract_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 摘要成功：写入 abstract 章节，标记 llm_abstract。"""
    monkeypatch.setattr("src.agent.report_agent.llm_available", lambda: True)
    monkeypatch.setattr(
        "src.agent.report_agent.llm_chat_json",
        lambda system, user, **kw: {
            "abstract": (
                "本报告围绕热电材料领域开展文献调研，检索 1 篇文献，抽取 1 个材料体系，"
                "识别 1 条 Research Gap，所有结论均附证据链。"
            )
        },
    )
    agent = ReportAgent(
        retrieval_path=_retrieval(tmp_path, [_paper("doc0", title="PbTe A")]),
        kb_path=_kb(tmp_path, ["PbTe"]),
        gaps_path=_gaps(tmp_path),
        output_dir=tmp_path / "out",
    )
    result = agent.run(use_llm=True)
    assert result.llm_abstract is True
    smap = result.document.section_map()
    assert smap["abstract"].content.startswith("本报告围绕热电材料领域")


def test_llm_abstract_degraded_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM 抛错：降级到规则摘要，不阻塞流水线（可回退）。"""
    monkeypatch.setattr("src.agent.report_agent.llm_available", lambda: True)

    def boom(system: str, user: str, **kw: object) -> dict:
        raise LLMError("mock llm down")

    monkeypatch.setattr("src.agent.report_agent.llm_chat_json", boom)
    agent = ReportAgent(
        retrieval_path=_retrieval(tmp_path, [_paper("doc0", title="PbTe A")]),
        kb_path=_kb(tmp_path, ["PbTe"]),
        gaps_path=_gaps(tmp_path),
        output_dir=tmp_path / "out",
    )
    result = agent.run(use_llm=True)
    assert result.llm_abstract is False
    smap = result.document.section_map()
    assert "本报告围绕" in smap["abstract"].content  # 规则摘要兜底


# ---------- 验证章节（模块 6 对接） ----------


def _validation_file(dir_path: Path, name: str, rows: list[dict]) -> Path:
    """构造单个验证 JSON（对齐 validation_agent 输出字段）。"""
    p = dir_path / name
    p.write_text(
        json.dumps({"source_finding": "finding_x.json", "results": rows}),
        encoding="utf-8",
    )
    return p


def test_section_validation_placeholder(tmp_path: Path) -> None:
    """无验证目录 → 占位说明（不阻塞报告）。"""
    assert "尚未执行数据库交叉验证" in asm.section_validation(None)
    assert "尚未执行数据库交叉验证" in asm.section_validation(tmp_path / "missing")


def test_section_validation_no_files(tmp_path: Path) -> None:
    """目录存在但无验证文件 → 明确提示。"""
    (tmp_path / "v").mkdir()
    assert "未找到验证结果" in asm.section_validation(tmp_path / "v")


def test_section_validation_with_data(tmp_path: Path) -> None:
    """有验证 JSON → 判定分布 + 候选表格（确定性组装）。"""
    vdir = tmp_path / "v"
    vdir.mkdir()
    _validation_file(
        vdir,
        "validation_1.json",
        [
            {
                "candidate_formula": "Ge0.95Ti0.05Te",
                "host": "GeTe",
                "verdict": "已知",
                "reason": "母体 GeTe 在 oqmd 中已收录且热力学稳定",
            },
            {
                "candidate_formula": "Pb0.9Na0.1Te",
                "host": "PbTe",
                "verdict": "新知",
                "reason": "母体 PbTe 不在库（库外假设）",
            },
        ],
    )
    _validation_file(
        vdir,
        "validation_2.json",
        [
            {
                "candidate_formula": "Sn0.95In0.05Te",
                "host": "SnTe",
                "verdict": "验证失败",
                "reason": "分数成分无法直查",
            }
        ],
    )
    out = asm.section_validation(vdir)
    assert "**2** 个构效关系发现" in out
    assert "**3** 个候选" in out
    assert "已知 1 个；新知 1 个；验证失败 1 个" in out
    assert "| Ge0.95Ti0.05Te | GeTe | 已知 |" in out
    assert "所有判定可回溯至 OQMD/MP 记录" in out


def test_report_agent_validation_section(tmp_path: Path) -> None:
    """端到端：ReportAgent 传 validation_dir → 验证章节含判定分布。"""
    vdir = tmp_path / "v"
    vdir.mkdir()
    _validation_file(
        vdir,
        "validation_1.json",
        [
            {
                "candidate_formula": "Ge0.95Ti0.05Te",
                "host": "GeTe",
                "verdict": "已知",
                "reason": "母体 GeTe 在 oqmd 中已收录且热力学稳定",
            }
        ],
    )
    agent = ReportAgent(
        retrieval_path=_retrieval(tmp_path, [_paper("doc0", title="PbTe A")]),
        kb_path=_kb(tmp_path, ["PbTe"]),
        gaps_path=_gaps(tmp_path),
        output_dir=tmp_path / "out",
        validation_dir=vdir,
    )
    result = agent.run(use_llm=False)
    smap = result.document.section_map()
    assert smap["validation"].title == "6. 数据库交叉验证"
    assert "已知 1 个" in smap["validation"].content
    assert result.document.meta.self_check["sections_complete"] is True

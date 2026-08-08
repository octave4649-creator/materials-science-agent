"""证据链审计报告模块单测（tmp fixture，无网络）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.audit.evidence_report import (
    audit_degradation,
    audit_logs,
    audit_verdicts,
    build_audit_report,
    check_evidence_coverage,
    load_findings,
    load_gaps,
    load_logs,
    load_retrieval_doc_ids,
    load_validations,
    render_html,
    render_markdown,
)

DOC_A = "a" * 64
DOC_B = "b" * 64


@pytest.fixture()
def env(tmp_path: Path) -> Path:
    """构造审计环境：logs + retrieval + gaps + findings + validation。"""
    root = tmp_path / "proj"
    results = root / "results"
    logs = results / "logs"
    data = root / "data"
    (results / "findings").mkdir(parents=True)
    (results / "validation").mkdir(parents=True)
    (results / "logs").mkdir(parents=True)
    data.mkdir()

    # 日志：success / error / skipped / degraded
    (logs / "extraction_agent_20260808.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"ts": "t1", "agent": "extraction_agent", "action": "extract_all",
                            "status": "success", "duration_ms": 120.0, "input_summary": {"n": 2}}),
                json.dumps({"ts": "t2", "agent": "extraction_agent", "action": "extract_one",
                            "status": "error", "error": "ValueError: bad", "duration_ms": 5.0}),
                "not-json\n",  # 坏行应跳过
                json.dumps({"ts": "t3", "agent": "gap_agent", "action": "gap_loop",
                            "status": "skipped", "output_summary": "degraded no llm"}),
            ]
        ),
        encoding="utf-8",
    )
    # 检索产物：两条 doc_id
    (results / "retrieval_20260808T000000.json").write_text(
        json.dumps(
            {
                "query": "test",
                "papers": [
                    {"doc_id": DOC_A, "chunk": "aaa", "doi": "10.1/a"},
                    {"doc_id": DOC_B, "chunk": "bbb", "doi": "10.1/b"},
                ],
            }
        ),
        encoding="utf-8",
    )
    # gaps：1 条有证据（可追溯）、1 条无证据
    (data / "gaps.json").write_text(
        json.dumps(
            {
                "gaps": [
                    {"statement": "gap traceable", "evidence_ids": [DOC_A]},
                    {"statement": "gap no evidence", "evidence_ids": []},
                    {"statement": "gap untraceable", "evidence_ids": ["x" * 64]},
                ]
            }
        ),
        encoding="utf-8",
    )
    # findings：1 条有证据、1 条无证据
    (results / "findings" / "finding_20260808T000000_1.json").write_text(
        json.dumps({"relation": "f traceable", "evidence_ids": [DOC_B]}),
        encoding="utf-8",
    )
    (results / "findings" / "finding_20260808T000000_2.json").write_text(
        json.dumps({"relation": "f no evidence", "evidence_ids": []}),
        encoding="utf-8",
    )
    # validation：判定分布（已知/新知/反例/验证失败）
    (results / "validation" / "validation_20260808T000000_1.json").write_text(
        json.dumps(
            {
                "source_finding": "f1",
                "evidence_ids": [DOC_A],
                "results": [
                    {"candidate_formula": "GeTe", "verdict": "已知"},
                    {"candidate_formula": "Ge0.9Ti0.1Te", "verdict": "新知"},
                    {"candidate_formula": "X", "verdict": "反例"},
                    {"candidate_formula": "Y", "verdict": "验证失败"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


class TestLoaders:
    def test_load_logs_parse_and_skip_bad_lines(self, env: Path) -> None:
        logs = load_logs(env / "results" / "logs")
        assert len(logs) == 3  # 坏行被跳过
        assert logs[0]["action"] == "extract_all"

    def test_load_retrieval_doc_ids(self, env: Path) -> None:
        ids = load_retrieval_doc_ids(env / "results")
        assert ids == {DOC_A, DOC_B}

    def test_load_gaps(self, env: Path) -> None:
        gaps = load_gaps(env / "data" / "gaps.json")
        assert len(gaps) == 3

    def test_load_findings_validations(self, env: Path) -> None:
        assert len(load_findings(env / "results")) == 2
        assert len(load_validations(env / "results")) == 1


class TestAuditItems:
    def test_audit_logs_health(self, env: Path) -> None:
        logs = load_logs(env / "results" / "logs")
        health = audit_logs(logs)
        assert health["total_logs"] == 3
        agents = {a["agent"]: a for a in health["agents"]}
        assert agents["extraction_agent"]["n_logs"] == 2
        assert agents["extraction_agent"]["success_rate"] == 0.5
        assert agents["extraction_agent"]["n_errors"] == 1

    def test_evidence_coverage_three_states(self, env: Path) -> None:
        ids = load_retrieval_doc_ids(env / "results")
        gaps = load_gaps(env / "data" / "gaps.json")
        findings = load_findings(env / "results")
        validations = load_validations(env / "results")
        cov = check_evidence_coverage(gaps, findings, validations, ids)
        assert cov["gaps"]["n_total"] == 3
        assert cov["gaps"]["n_traceable"] == 1
        assert cov["gaps"]["n_no_evidence"] == 1
        assert cov["gaps"]["n_untraceable"] == 1
        assert cov["findings"]["n_no_evidence"] == 1
        assert cov["validations"]["n_traceable"] == 1

    def test_audit_degradation(self, env: Path) -> None:
        logs = load_logs(env / "results" / "logs")
        deg = audit_degradation(logs)
        # error 1 条 + skipped 1 条（含 degraded 字样）
        assert deg["n_degraded"] == 2

    def test_audit_verdicts(self, env: Path) -> None:
        validations = load_validations(env / "results")
        v = audit_verdicts(validations)
        assert v["n_candidates"] == 4
        assert v["verdict_dist"] == {"已知": 1, "新知": 1, "反例": 1, "验证失败": 1}


class TestBuildAndRender:
    def test_build_audit_report(self, env: Path) -> None:
        report = build_audit_report(
            log_dir=env / "results" / "logs",
            results_dir=env / "results",
            gaps_path=env / "data" / "gaps.json",
        )
        assert report["data_overview"]["retrieval_doc_ids"] == 2
        assert report["data_overview"]["n_gaps"] == 3
        assert "log_health" in report and "verdicts" in report

    def test_render_markdown_sections(self, env: Path) -> None:
        report = build_audit_report(
            log_dir=env / "results" / "logs",
            results_dir=env / "results",
            gaps_path=env / "data" / "gaps.json",
        )
        md = render_markdown(report)
        for section in ("# 证据链审计报告", "日志健康度", "证据链覆盖", "验证判定分布"):
            assert section in md
        assert "gap no evidence" in md  # 无证据明细列出

    def test_render_html_structure(self, env: Path) -> None:
        report = build_audit_report(
            log_dir=env / "results" / "logs",
            results_dir=env / "results",
            gaps_path=env / "data" / "gaps.json",
        )
        h = render_html(report)
        assert "<!DOCTYPE html>" in h
        assert "证据链审计报告" in h
        assert "chip" in h  # 判定色块
        assert "#2e7d32" in h  # 已知色

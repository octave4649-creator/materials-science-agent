"""证据链审计报告：统一日志 + 全链路证据链 → 结构化审计报告。

对齐 `.trae/rules/00-project-rules.md`：
- 4.1 可观测性：每个 Agent 暴露结构化日志（输入、输出、耗时、工具调用序列）
- 4.2 证据链强制：任何结论输出必须附带 EvidenceChain（来源、DOI、页码、调用记录）
- 4.3 统一 JSON 日志：{ts, agent, action, input_summary, output_summary, duration_ms, status}

数据源（全部本地文件，无网络）：
- results/logs/*.jsonl        ：AuditLogger 统一 JSON 日志（agent 维度，追加式）
- results/retrieval_*.json    ：检索产物（papers[].doc_id 证据链起点）
- data/gaps.json              ：Gap 清单（evidence_ids 回链检索 doc_id）
- results/findings/*.json     ：搜索 finding（evidence_ids + top_candidates）
- results/validation/*.json   ：数据库验证（evidence_ids + verdict 判定）
- data/knowledge_base.json    ：知识库条目（record.source.doc_id）

审计项：
1. 日志健康度：各 agent 日志条数 / action 分布 / 成功率 / 平均耗时 / 异常 top
2. 证据链覆盖：Gap / finding / validation 的 evidence_ids 是否命中检索 doc_id
   （无来源结论 = evidence_ids 为空 或 全部无法回溯 → 审计告警）
3. 降级留痕：status=error/skipped 与 degraded 标记（降级不中断，但需留痕）
4. 验证判定分布：validation verdict 统计（已知 / 新知 / 反例 / 验证失败）
5. 结论-证据矩阵：每条结论（Gap / finding）的证据链长度与可追溯性

输出：结构化 dict + Markdown + HTML（纯 Python 渲染，无第三方依赖）。
"""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# 验证判定色（HTML 状态色块）
_VERDICT_COLOR = {
    "已知": "#2e7d32",
    "新知": "#1565c0",
    "反例": "#c62828",
    "验证失败": "#e65100",
    "unknown": "#757575",
}
# 日志状态色
_STATUS_COLOR = {"success": "#2e7d32", "error": "#c62828", "skipped": "#757575"}


def load_logs(log_dir: Path) -> list[dict[str, Any]]:
    """读全部 agent 审计日志（results/logs/*.jsonl），坏行跳过。

    返回按 ts 升序的日志记录列表（每条含 agent/action/status/ts 等）。
    """
    records: list[dict[str, Any]] = []
    if not log_dir.exists():
        return records
    for path in sorted(log_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec.setdefault("_file", path.name)
                records.append(rec)
    records.sort(key=lambda r: str(r.get("ts", "")))
    return records


def _load_json(path: Path) -> Any:
    """读 JSON 文件；缺失/损坏返回 None。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_retrieval_doc_ids(results_dir: Path = RESULTS_DIR) -> set[str]:
    """收集全部检索产物的 doc_id（证据链可回溯集合）。"""
    doc_ids: set[str] = set()
    for path in results_dir.glob("retrieval_*.json"):
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        for paper in data.get("papers", []) or []:
            if paper.get("doc_id"):
                doc_ids.add(paper["doc_id"])
    return doc_ids


def load_gaps(gaps_path: Path | None = None) -> list[dict[str, Any]]:
    """读 data/gaps.json 的 gaps 列表。"""
    path = gaps_path or (DATA_DIR / "gaps.json")
    data = _load_json(path)
    if not isinstance(data, dict):
        return []
    return data.get("gaps", []) or []


def load_findings(results_dir: Path = RESULTS_DIR) -> list[dict[str, Any]]:
    """读 results/findings/*.json（跳过 validation 批量产物同名冲突）。"""
    findings: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("findings/finding_*.json")):
        data = _load_json(path)
        if isinstance(data, dict):
            data.setdefault("_file", path.name)
            findings.append(data)
    return findings


def load_validations(results_dir: Path = RESULTS_DIR) -> list[dict[str, Any]]:
    """读 results/validation/validation_*.json（不含 rerun 汇总与 mp_phase_check）。"""
    validations: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("validation/validation_*.json")):
        data = _load_json(path)
        if isinstance(data, dict):
            data.setdefault("_file", path.name)
            validations.append(data)
    return validations


def load_knowledge_base(kb_path: Path | None = None) -> list[dict[str, Any]]:
    """读知识库条目列表。"""
    path = kb_path or (DATA_DIR / "knowledge_base.json")
    data = _load_json(path)
    if isinstance(data, list):
        return data
    return []


# ---------- 审计项 ----------


def audit_logs(logs: list[dict[str, Any]]) -> dict[str, Any]:
    """审计项 1：日志健康度（按 agent 聚合）。"""
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in logs:
        by_agent[rec.get("agent") or "unknown"].append(rec)
    agents: list[dict[str, Any]] = []
    for agent in sorted(by_agent):
        recs = by_agent[agent]
        statuses = Counter(r.get("status") for r in recs)
        actions = Counter(r.get("action") for r in recs)
        durations = [r["duration_ms"] for r in recs if r.get("duration_ms") is not None]
        errors = [
            {"action": r.get("action"), "error": str(r.get("error"))[:160]}
            for r in recs
            if r.get("status") == "error"
        ]
        agents.append(
            {
                "agent": agent,
                "n_logs": len(recs),
                "status": dict(statuses),
                "success_rate": round(
                    statuses.get("success", 0) / len(recs), 4
                ) if recs else 0.0,
                "avg_duration_ms": round(sum(durations) / len(durations), 1)
                if durations else None,
                "top_actions": [a for a, _ in actions.most_common(5)],
                "n_errors": len(errors),
                "errors": errors[:10],
            }
        )
    return {"agents": agents, "total_logs": len(logs)}


def check_evidence_coverage(
    gaps: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    retrieval_doc_ids: set[str],
) -> dict[str, Any]:
    """审计项 2：证据链覆盖——每条结论的 evidence_ids 是否命中检索 doc_id。

    无来源结论 = evidence_ids 为空，或全部 id 无法回溯到检索产物。
    """
    def _check(name: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        checked: list[dict[str, Any]] = []
        n_no_evidence = 0
        n_untraceable = 0
        for it in items:
            ids = list(dict.fromkeys(it.get("evidence_ids") or []))
            hit = [i for i in ids if i in retrieval_doc_ids]
            if not ids:
                n_no_evidence += 1
            elif not hit:
                n_untraceable += 1
            checked.append(
                {
                    "name": it.get("_file") or it.get("statement") or it.get("relation")
                    or it.get("gap_statement") or f"{name}#{len(checked)}",
                    "n_evidence": len(ids),
                    "n_traceable": len(hit),
                    "traceable": bool(hit),
                    "evidence_ids": ids[:3],
                }
            )
        n_total = len(checked)
        return {
            "items": checked,
            "n_total": n_total,
            "n_no_evidence": n_no_evidence,
            "n_untraceable": n_untraceable,
            "n_traceable": n_total - n_no_evidence - n_untraceable,
        }

    return {
        "gaps": _check("gap", gaps),
        "findings": _check("finding", findings),
        "validations": _check("validation", validations),
        "retrieval_doc_count": len(retrieval_doc_ids),
    }


def audit_degradation(logs: list[dict[str, Any]]) -> dict[str, Any]:
    """审计项 3：降级留痕——error/skipped 状态与 degraded 标记日志。"""
    degraded = [
        {
            "ts": r.get("ts"),
            "agent": r.get("agent"),
            "action": r.get("action"),
            "status": r.get("status"),
            "detail": str(r.get("error") or r.get("output_summary"))[:160],
        }
        for r in logs
        if r.get("status") in ("error", "skipped")
        or "degraded" in json.dumps(r, ensure_ascii=False)
    ]
    return {"n_degraded": len(degraded), "items": degraded[:50]}


def audit_verdicts(validations: list[dict[str, Any]]) -> dict[str, Any]:
    """审计项 4：验证判定分布（跨全部 validation 产物的 results[].verdict）。"""
    verdicts: Counter[str] = Counter()
    by_formula: dict[str, Counter[str]] = defaultdict(Counter)
    n_candidates = 0
    for v in validations:
        for res in v.get("results", []) or []:
            verdicts[res.get("verdict") or "unknown"] += 1
            n_candidates += 1
            formula = res.get("candidate_formula") or res.get("host") or "?"
            by_formula[formula][res.get("verdict") or "unknown"] += 1
    top_formulas = sorted(
        ({"formula": f, "verdicts": dict(c)} for f, c in by_formula.items()),
        key=lambda x: sum(x["verdicts"].values()),
        reverse=True,
    )[:20]
    return {
        "n_candidates": n_candidates,
        "verdict_dist": dict(verdicts),
        "n_validations": len(validations),
        "top_formulas": top_formulas,
    }


def build_audit_report(
    log_dir: Path | None = None,
    results_dir: Path = RESULTS_DIR,
    gaps_path: Path | None = None,
    kb_path: Path | None = None,
) -> dict[str, Any]:
    """汇总全部审计项 → 结构化审计报告 dict。

    参数:
        log_dir: 审计日志目录（默认 results/logs）
        results_dir: 结果目录（retrieval/findings/validation 产物）
        gaps_path: gaps.json 路径（默认 data/gaps.json）
        kb_path: 知识库路径（默认 data/knowledge_base.json）
    """
    log_dir = log_dir or (results_dir / "logs")
    logs = load_logs(log_dir)
    retrieval_doc_ids = load_retrieval_doc_ids(results_dir)
    gaps = load_gaps(gaps_path)
    findings = load_findings(results_dir)
    validations = load_validations(results_dir)
    kb = load_knowledge_base(kb_path)
    return {
        "log_health": audit_logs(logs),
        "evidence_coverage": check_evidence_coverage(
            gaps, findings, validations, retrieval_doc_ids
        ),
        "degradation": audit_degradation(logs),
        "verdicts": audit_verdicts(validations),
        "data_overview": {
            "retrieval_doc_ids": len(retrieval_doc_ids),
            "n_gaps": len(gaps),
            "n_findings": len(findings),
            "n_validations": len(validations),
            "n_kb_entries": len(kb),
        },
    }


# ---------- 渲染 ----------


def render_markdown(report: dict[str, Any]) -> str:
    """渲染 Markdown 审计报告。"""
    lines: list[str] = [
        "# 证据链审计报告",
        "",
        "## 1. 数据概览",
        "",
        "| 数据源 | 数量 |",
        "| --- | --- |",
        f"| 检索文献 doc_id | {report['data_overview']['retrieval_doc_ids']} |",
        f"| Gap 结论 | {report['data_overview']['n_gaps']} |",
        f"| 搜索 finding | {report['data_overview']['n_findings']} |",
        f"| 验证产物 | {report['data_overview']['n_validations']} |",
        f"| 知识库条目 | {report['data_overview']['n_kb_entries']} |",
        "",
        "## 2. 日志健康度",
        "",
        "| Agent | 日志数 | 成功率 | 平均耗时(ms) | error | top actions |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for a in report["log_health"]["agents"]:
        lines.append(
            f"| {a['agent']} | {a['n_logs']} | {a['success_rate']:.3f} | "
            f"{a['avg_duration_ms'] if a['avg_duration_ms'] is not None else '-'} | "
            f"{a['n_errors']} | {', '.join(a['top_actions'])} |"
        )
    cov = report["evidence_coverage"]
    lines += [
        "",
        "## 3. 证据链覆盖（无来源结论检查）",
        "",
        "| 结论类型 | 总数 | 可追溯 | 无证据 | 不可追溯 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for key, label in (("gaps", "Gap"), ("findings", "Finding"), ("validations", "验证")):
        c = cov[key]
        lines.append(
            f"| {label} | {c['n_total']} | {c['n_traceable']} | "
            f"{c['n_no_evidence']} | {c['n_untraceable']} |"
        )
    lines += [
        "",
        "### 无证据结论明细（evidence_ids 为空）",
        "",
    ]
    any_no_evidence = False
    for key, label in (("gaps", "Gap"), ("findings", "Finding"), ("validations", "验证")):
        no_ev = [i for i in cov[key]["items"] if i["n_evidence"] == 0]
        if no_ev:
            any_no_evidence = True
            lines.append(f"- **{label}**（{len(no_ev)} 条）：")
            for i in no_ev[:10]:
                lines.append(f"  - {i['name']}")
    if not any_no_evidence:
        lines.append("- 无（全部结论均携带证据链）")
    deg = report["degradation"]
    lines += [
        "",
        f"## 4. 降级留痕（{deg['n_degraded']} 条 error/skipped/degraded）",
        "",
    ]
    if deg["items"]:
        for d in deg["items"][:20]:
            lines.append(
                f"- [{d['ts']}] {d['agent']}.{d['action']} "
                f"status={d['status']}：{d['detail']}"
            )
    else:
        lines.append("- 无降级记录")
    v = report["verdicts"]
    lines += [
        "",
        "## 5. 验证判定分布",
        "",
        f"- 候选总数：{v['n_candidates']}（验证产物 {v['n_validations']} 份）",
        "- 判定分布："
        + "、".join(f"{k} {n}" for k, n in v["verdict_dist"].items()),
        "",
        "| 母体/候选 | 判定分布 |",
        "| --- | --- |",
    ]
    for f in v["top_formulas"]:
        dist = ", ".join(f"{k}:{n}" for k, n in f["verdicts"].items())
        lines.append(f"| {f['formula']} | {dist} |")
    return "\n".join(lines) + "\n"


def render_html(report: dict[str, Any]) -> str:
    """渲染 HTML 审计报告（内联 CSS，无第三方依赖，可浏览器直接打开）。"""
    rows_agents = "".join(
        f"<tr><td>{html.escape(a['agent'])}</td><td>{a['n_logs']}</td>"
        f"<td>{a['success_rate']:.3f}</td>"
        f"<td>{a['avg_duration_ms'] if a['avg_duration_ms'] is not None else '-'}</td>"
        f"<td class='err'>{a['n_errors']}</td>"
        f"<td>{html.escape(', '.join(a['top_actions']))}</td></tr>"
        for a in report["log_health"]["agents"]
    )
    cov = report["evidence_coverage"]
    rows_cov = "".join(
        f"<tr><td>{label}</td><td>{cov[key]['n_total']}</td>"
        f"<td class='ok'>{cov[key]['n_traceable']}</td>"
        f"<td class='warn'>{cov[key]['n_no_evidence']}</td>"
        f"<td class='err'>{cov[key]['n_untraceable']}</td></tr>"
        for key, label in (("gaps", "Gap"), ("findings", "Finding"), ("validations", "验证"))
    )
    deg_items = report["degradation"]["items"]
    rows_deg = "".join(
        f"<li>[{html.escape(d['ts'] or '')}] {html.escape(d['agent'])}."
        f"{html.escape(d['action'])} status={d['status']}："
        f"{html.escape(d['detail'])}</li>"
        for d in deg_items[:20]
    ) or "<li>无降级记录</li>"
    v = report["verdicts"]
    chips = "".join(
        f"<span class='chip' style='background:{_VERDICT_COLOR.get(k, '#757575')}'>"
        f"{html.escape(k)} {n}</span> "
        for k, n in v["verdict_dist"].items()
    )
    def _verdict_cell(f: dict[str, Any]) -> str:
        """母体/候选的判定分布单元格（HTML 转义）。"""
        dist = ", ".join(f"{k}:{n}" for k, n in f["verdicts"].items())
        return html.escape(dist)

    rows_verdict = "".join(
        f"<tr><td>{html.escape(f['formula'])}</td><td>{_verdict_cell(f)}</td></tr>"
        for f in v["top_formulas"]
    )
    ov = report["data_overview"]
    cards_html = "".join(
        f'<div class="card"><div class="num">{num}</div>'
        f'<div class="lbl">{lbl}</div></div>'
        for num, lbl in (
            (ov["retrieval_doc_ids"], "检索文献 doc_id"),
            (ov["n_gaps"], "Gap 结论"),
            (ov["n_findings"], "搜索 finding"),
            (ov["n_validations"], "验证产物"),
            (ov["n_kb_entries"], "知识库条目"),
        )
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>证据链审计报告</title>
<style>
  body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
         background:#f7f9fc; color:#1f2d3d; margin:0; padding:24px; }}
  .wrap {{ max-width:960px; margin:0 auto; }}
  h1 {{ color:#1a5f9e; font-size:22px; border-bottom:2px solid #1a5f9e;
        padding-bottom:8px; }}
  h2 {{ color:#1a5f9e; font-size:17px; margin-top:28px; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; margin:12px 0;
          box-shadow:0 4px 20px rgba(26,95,158,0.08); border-radius:12px; overflow:hidden; }}
  th, td {{ padding:8px 12px; text-align:left; border-bottom:1px solid #eef2f7;
           font-size:13px; }}
  th {{ background:#eef5fb; color:#1a5f9e; }}
  .ok {{ color:#2e7d32; font-weight:600; }}
  .err {{ color:#c62828; font-weight:600; }}
  .warn {{ color:#e65100; font-weight:600; }}
  .chip {{ display:inline-block; color:#fff; border-radius:12px; padding:2px 10px;
          margin:2px; font-size:12px; }}
  li {{ font-size:13px; margin:4px 0; }}
  .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:12px 0; }}
  .card {{ background:#fff; border-radius:12px; padding:14px 18px;
          box-shadow:0 4px 20px rgba(26,95,158,0.08); flex:1; min-width:140px; }}
  .card .num {{ font-size:26px; color:#1a5f9e; font-weight:700; }}
  .card .lbl {{ font-size:12px; color:#8c9aa8; }}
</style></head><body><div class="wrap">
<h1>证据链审计报告</h1>
<div class="cards">
{cards_html}
</div>
<h2>1. 日志健康度</h2>
<table><tr><th>Agent</th><th>日志数</th><th>成功率</th><th>平均耗时(ms)</th>
<th>error</th><th>top actions</th></tr>{rows_agents}</table>
<h2>2. 证据链覆盖（无来源结论检查）</h2>
<table><tr><th>结论类型</th><th>总数</th><th>可追溯</th><th>无证据</th>
<th>不可追溯</th></tr>{rows_cov}</table>
<h2>3. 降级留痕（{report['degradation']['n_degraded']} 条）</h2>
<ul>{rows_deg}</ul>
<h2>4. 验证判定分布（{v['n_candidates']} 候选）</h2>
<p>{chips}</p>
<table><tr><th>母体/候选</th><th>判定分布</th></tr>{rows_verdict}</table>
</div></body></html>
"""

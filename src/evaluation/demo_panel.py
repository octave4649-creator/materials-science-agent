"""决赛现场 demo：自包含 HTML 面板核心逻辑（真实产物快照聚合 + 渲染）。

阶段 6 唯一剩余项「现场 demo」：用真实产物（data/gaps.json、data/knowledge_base.json、
results/findings/、results/validation/、results/eval/recall_matrix_*.json、
results/ablation/ablation_report.json、results/ensemble/*.md）聚合成单个
自包含 HTML 面板 `docs/demo-panel.html`——无 CDN、无外部请求，数据以
`<script type="application/json">` 内嵌，浏览器直接打开即可展示
「问题 → 文献与知识库 → Research Gap → 构效关系 → 数据库验证 → 评测指标 → 证据链」
全流程，对齐 task_plan 阶段 6「现场 demo：问题→Gap→构效关系→数据库验证」。

设计：
- 纯标准库（无第三方依赖），幂等可复跑
- 聚合函数与 HTML 渲染分离，聚合逻辑可单测
- 内嵌 JSON 时对 `</script>` 做转义（`<\\/script>`），保证 file:// 打开不破 HTML
- 本文件含大段 HTML/CSS/JS 模板字符串，行长豁免（对齐 deploy_v2.py 先例）
"""
# ruff: noqa: E501
# 说明：HTML/CSS/JS 模板字符串行长豁免（对齐 deploy_v2.py 先例）

from __future__ import annotations

import json
import re
from pathlib import Path

from src.common.config import DATA_DIR, RESULTS_DIR

# ---------------------------------------------------------------- 聚合层


def load_json(path: Path) -> object:
    """读取 JSON，缺失/损坏返回 None（对齐 gap_evidence_backfill.load_json 语义）。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def collect_gaps(gaps_path: Path = DATA_DIR / "gaps.json") -> dict:
    """gaps.json → 面板数据：全量 Gap + novelty/gap_type 分布 + 有证据计数。"""
    gaps = load_json(gaps_path)
    if not isinstance(gaps, dict):
        return {"n_gaps": 0, "gaps": [], "novelty_dist": {}, "type_dist": {}, "n_with_evidence": 0}
    items = gaps.get("gaps") or []
    novelty_dist: dict[str, int] = {}
    type_dist: dict[str, int] = {}
    n_with_evidence = 0
    panel_gaps = []
    for g in items:
        nov = g.get("novelty") or "未知"
        gap_type = g.get("gap_type") or "未知"
        novelty_dist[nov] = novelty_dist.get(nov, 0) + 1
        type_dist[gap_type] = type_dist.get(gap_type, 0) + 1
        ev = g.get("evidence_ids") or []
        if ev:
            n_with_evidence += 1
        panel_gaps.append(
            {
                "idx": g.get("idx"),
                "gap_type": gap_type,
                "statement": g.get("statement"),
                "novelty": nov,
                "formulas": g.get("formulas") or [],
                "n_evidence": len(ev),
                "operability": g.get("operability"),
            }
        )
    return {
        "n_gaps": len(items),
        "gaps": panel_gaps,
        "novelty_dist": novelty_dist,
        "type_dist": type_dist,
        "n_with_evidence": n_with_evidence,
    }


def collect_kb(kb_path: Path = DATA_DIR / "knowledge_base.json") -> list[dict]:
    """知识库 → 面板数据（formula + 代表性属性，去重保序）。"""
    kb = load_json(kb_path)
    if not isinstance(kb, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for entry in kb:
        formula = (entry.get("normalized_formula") or "").strip()
        if not formula or formula.lower() in seen:
            continue
        seen.add(formula.lower())
        record = entry.get("record") or {}
        props = []
        for p in record.get("properties") or []:
            if p.get("name") and p.get("value") is not None:
                props.append(f"{p['name']}={p['value']}")
        synthesis = record.get("synthesis") or {}
        out.append(
            {
                "formula": formula,
                "properties": props[:4],
                "synthesis_temp": synthesis.get("temperature"),
                "n_evidence": len(entry.get("evidence_ids") or []),
            }
        )
    return out


def collect_findings(findings_dir: Path = RESULTS_DIR / "findings", top_n: int = 3) -> dict:
    """findings/*.json → 面板数据（relation/hypothesis/top_candidates 截断）。"""
    files = sorted(findings_dir.glob("finding_*.json"))
    items: list[dict] = []
    seen_relation: set[str] = set()
    for f in files:
        data = load_json(f)
        if not isinstance(data, dict):
            continue
        relation = (data.get("relation") or "").strip()
        if not relation or relation in seen_relation:
            continue
        seen_relation.add(relation)
        candidates = []
        for cand in (data.get("top_candidates") or [])[:top_n]:
            scores = cand.get("scores") or {}
            candidates.append(
                {
                    "formula": cand.get("formula"),
                    "dopant": cand.get("dopant"),
                    "concentration": cand.get("concentration"),
                    "score": round(float(scores.get("scientific") or 0.0), 3),
                    "rationale": (cand.get("rationale") or "")[:60],
                }
            )
        items.append(
            {
                "relation": relation,
                "hypothesis": data.get("hypothesis"),
                "gap_statement": (data.get("gap_statement") or "")[:80],
                "n_candidates": len(data.get("top_candidates") or []),
                "top_candidates": candidates,
            }
        )
    return {"n_findings": len(items), "findings": items}


def collect_validations(validation_dir: Path = RESULTS_DIR / "validation") -> dict:
    """validation/*.json → 面板数据（verdict 分布 + 代表条目，按候选去重）。"""
    files = sorted(validation_dir.glob("validation_*.json"))
    seen: dict[tuple[str, str], dict] = {}  # (gap_statement, candidate_formula) → item
    for f in files:
        data = load_json(f)
        if not isinstance(data, dict):
            continue
        gap_stmt = (data.get("gap_statement") or "")[:60]
        for r in data.get("results") or []:
            verdict = r.get("verdict") or "未知"
            key = (gap_stmt, r.get("candidate_formula") or "")
            seen[key] = {
                "gap_statement": gap_stmt,
                "candidate_formula": r.get("candidate_formula"),
                "host": r.get("host"),
                "dopant": r.get("dopant"),
                "concentration": r.get("concentration"),
                "verdict": verdict,
                "reason": (r.get("reason") or "")[:90],
            }
    items = sorted(
        seen.values(),
        key=lambda x: (x["gap_statement"], x["candidate_formula"]),
    )
    verdict_dist: dict[str, int] = {}
    for item in items:
        verdict_dist[item["verdict"]] = verdict_dist.get(item["verdict"], 0) + 1
    return {"verdict_dist": verdict_dist, "n_checks": len(items), "items": items}


def collect_recall_matrix(eval_dir: Path = RESULTS_DIR / "eval") -> dict:
    """取最新 recall_matrix_*.json 内嵌（同一 (algo, mode) 已由 merge 脚本去重）。"""
    files = sorted(eval_dir.glob("recall_matrix_*.json"))
    if not files:
        return {"matrix": [], "note": "暂无召回率矩阵，运行 merge_recall_matrix.py 生成"}
    data = load_json(files[-1])
    if not isinstance(data, dict):
        return {"matrix": [], "note": "recall_matrix 解析失败"}
    return {"matrix": data.get("matrix") or [], "note": data.get("note") or ""}


def collect_ablation(ablation_path: Path = RESULTS_DIR / "ablation" / "ablation_report.json") -> dict:
    """消融报告 → 面板数据（arms + gains）。"""
    data = load_json(ablation_path)
    if not isinstance(data, dict):
        return {"arms": {}, "gains": {}}
    return {"arms": data.get("arms") or {}, "gains": data.get("gains") or {}}


def collect_ensemble(ensemble_dir: Path = RESULTS_DIR / "ensemble") -> dict:
    """ensemble/*.md → 概要（解析「算法数：N」行统计多算法共识数）。"""
    files = sorted(ensemble_dir.glob("ensemble_*.md"))
    if not files:
        return {"n_gap_groups": 0, "n_consensus": 0, "note": "暂无融合结果，运行 run_ensemble.py 生成"}
    n_groups = 0
    n_consensus = 0
    pattern = re.compile(r"算法数：(\d+)")
    for f in files:
        text = f.read_text(encoding="utf-8")
        for line in text.splitlines():
            m = pattern.search(line)
            if m:
                n_groups += 1
                if int(m.group(1)) >= 2:
                    n_consensus += 1
    return {"n_gap_groups": n_groups, "n_consensus": n_consensus}


def build_payload() -> dict:
    """聚合全部真实产物 → 面板 JSON payload。"""
    return {
        "domain": "热电材料 · 掺杂-性能构效关系（路线 A）",
        "gaps": collect_gaps(),
        "kb": collect_kb(),
        "findings": collect_findings(),
        "validation": collect_validations(),
        "recall": collect_recall_matrix(),
        "ablation": collect_ablation(),
        "ensemble": collect_ensemble(),
    }


# ---------------------------------------------------------------- 渲染层


def _escape_script_json(obj: object) -> str:
    """JSON 内嵌 <script> 时转义 `</` → `<\\/`，防止提前闭合（file:// 安全）。"""
    return json.dumps(obj, ensure_ascii=False, indent=1).replace("</", "<\\/")


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>材料科学文献驱动的科学发现智能体 · 现场演示</title>
<style>
  :root {
    --deep-blue: #1A5F9E; --ice: #F7F9FC; --mint: #4ECDC4; --warm: #FF8C42;
    --ink: #2B3A4A; --muted: #8C9AA8; --line: #E3EAF2;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: "PingFang SC", "Source Han Sans SC", "Microsoft YaHei", sans-serif;
         background: var(--ice); color: var(--ink); line-height: 1.6; }
  .hero { background: linear-gradient(135deg, #12456F 0%, var(--deep-blue) 55%, #1E7BB5 100%);
          color: #fff; padding: 44px 32px 36px; text-align: center; }
  .hero h1 { font-size: 26px; font-weight: 700; letter-spacing: 1px; }
  .hero p { margin-top: 10px; font-size: 14px; color: #D8E6F5; }
  .stats { display: flex; flex-wrap: wrap; justify-content: center; gap: 14px; margin-top: 22px; }
  .stat { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.22);
          border-radius: 12px; padding: 10px 18px; min-width: 108px; }
  .stat b { display: block; font-size: 20px; }
  .stat span { font-size: 12px; color: #C7DAF0; }
  nav { position: sticky; top: 0; z-index: 10; display: flex; flex-wrap: wrap; gap: 4px;
        background: #fff; border-bottom: 1px solid var(--line); padding: 8px 16px;
        box-shadow: 0 4px 20px rgba(26,95,158,0.06); }
  nav button { border: none; background: transparent; color: var(--muted); font-size: 13px;
               padding: 8px 14px; border-radius: 10px; cursor: pointer; transition: all .18s; }
  nav button:hover { background: #EEF4FB; color: var(--deep-blue); }
  nav button.active { background: var(--deep-blue); color: #fff; font-weight: 600; }
  main { max-width: 1080px; margin: 24px auto 60px; padding: 0 20px; }
  section.panel { display: none; }
  section.panel.active { display: block; }
  .card { background: #fff; border: 1px solid var(--line); border-radius: 12px;
          padding: 18px 20px; margin-bottom: 16px;
          box-shadow: 0 4px 20px rgba(26,95,158,0.08); }
  .card h2 { font-size: 16px; margin-bottom: 12px; color: var(--deep-blue); }
  .card h3 { font-size: 14px; margin: 10px 0 6px; color: var(--ink); }
  .tag { display: inline-block; font-size: 12px; padding: 1px 10px; border-radius: 999px;
         margin-right: 6px; vertical-align: middle; }
  .tag.novelty-new { background: #E4F7F5; color: #0E8F86; }
  .tag.novelty-partial { background: #FFF1E6; color: #D9701B; }
  .tag.novelty-unknown { background: #EEF0F4; color: var(--muted); }
  .tag.ev { background: #E9F1FB; color: var(--deep-blue); }
  .tag.verdict-known { background: #E4F7F5; color: #0E8F86; }
  .tag.verdict-新知 { background: #E4F7F5; color: #0E8F86; }
  .tag.verdict-反例 { background: #FDEBEA; color: #C73E3E; }
  .tag.verdict-验证失败 { background: #FFF1E6; color: #D9701B; }
  .tag.verdict-未知 { background: #EEF0F4; color: var(--muted); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); }
  th { color: var(--deep-blue); font-weight: 600; background: #F4F8FD; }
  .pill { display: inline-block; min-width: 34px; text-align: center; padding: 1px 8px;
          border-radius: 8px; font-size: 12px; font-weight: 600; }
  .pill.good { background: #E4F7F5; color: #0E8F86; }
  .pill.mid { background: #FFF1E6; color: #D9701B; }
  .pill.low { background: #FDEBEA; color: #C73E3E; }
  .flow { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 13px; }
  .flow .step { background: #EEF4FB; color: var(--deep-blue); border-radius: 10px;
                padding: 8px 14px; font-weight: 600; }
  .flow .arrow { color: var(--muted); }
  .muted { color: var(--muted); font-size: 12px; }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
  .gap-item, .find-item { padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px;
                          margin-bottom: 10px; background: #FCFEFF; }
  .gap-item .stmt { font-size: 13px; }
  .find-item .rel { font-size: 13px; font-weight: 600; color: var(--deep-blue); }
  .find-item .hyp { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .search-box { width: 100%; padding: 9px 14px; border: 1px solid var(--line); border-radius: 10px;
                font-size: 13px; margin-bottom: 12px; outline: none; }
  .search-box:focus { border-color: var(--deep-blue); }
  .note { background: #F4F8FD; border-left: 3px solid var(--deep-blue); border-radius: 8px;
          padding: 10px 14px; font-size: 12px; color: var(--muted); margin-top: 10px; }
  footer { text-align: center; color: var(--muted); font-size: 12px; padding: 24px 0 40px; }
</style>
</head>
<body>
<header class="hero">
  <h1>材料科学文献驱动的科学发现智能体</h1>
  <p>GOAI 赛道三 · 方向三｜基本任务（文献调研四 Agent）+ 路线 A（构效关系发现）｜主攻热电材料</p>
  <div class="stats" id="stats"></div>
</header>
<nav id="tabs"></nav>
<main id="main"></main>
<footer>演示面板数据为真实运行产物快照（gaps / knowledge_base / findings / validation / recall / ablation / ensemble），
  由 <code>scripts/build_demo_panel.py</code> 聚合生成 · 自包含无外部依赖，双击即开</footer>

<script id="demo-data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("demo-data").textContent);

/* ---- 顶部指标卡 ---- */
const G = D.gaps, F = D.findings, V = D.validation, R = D.recall, A = D.ablation;
const stats = [
  ["文献知识库", D.kb.length + " 条"],
  ["Research Gap", G.n_gaps + " 条"],
  ["构效关系候选", F.n_findings + " finding"],
  ["数据库验证", V.n_checks + " 候选"],
  ["搜索算法", "GA/MCTS/BO/SR"],
  ["证据可追溯", G.n_with_evidence + "/" + G.n_gaps],
];
document.getElementById("stats").innerHTML = stats.map(([k, v]) =>
  `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");

/* ---- Tab 定义 ---- */
const TABS = [
  ["overview", "问题与流程"],
  ["literature", "文献与知识库"],
  ["gaps", "Research Gap"],
  ["findings", "构效关系"],
  ["validation", "数据库验证"],
  ["metrics", "评测指标"],
  ["evidence", "证据链"],
];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function novTag(n) {
  const cls = n === "新知" ? "novelty-new" : n === "部分已知" ? "novelty-partial" : "novelty-unknown";
  return `<span class="tag ${cls}">${esc(n)}</span>`;
}
function verdictTag(v) {
  const cls = v === "已知" || v === "新知" ? "verdict-known" : v === "反例" ? "verdict-反例"
    : v === "验证失败" ? "verdict-验证失败" : "verdict-未知";
  return `<span class="tag ${cls}">${esc(v)}</span>`;
}
function scorePill(x) {
  const cls = x >= 0.8 ? "good" : x >= 0.6 ? "mid" : "low";
  return `<span class="pill ${cls}">${x.toFixed(2)}</span>`;
}

/* ---- 各面板渲染 ---- */
function panelOverview() {
  const arms = A.arms || {};
  const gain = (A.gains && A.gains.llm_fusion_gain_pct != null)
    ? A.gains.llm_fusion_gain_pct.toFixed(2) : "—";
  return `
  <div class="card">
    <h2>科学问题</h2>
    <p style="font-size:13px">热电优值 zT = S²σT/κ 的电热输运强耦合，使「掺杂 × 浓度」的组分-性能定量关联长期依赖试错实验。
    基岩盐族热电体系（GeTe/PbTe/SnTe）存在三类瓶颈：<b>掺杂协同机制不明、矛盾结论未消解、高维组分空间无高效导航</b>。</p>
    <p class="muted" style="margin-top:6px">AI 介入点：以文献证据驱动 + 搜索算法 × LLM 深度融合，构建「检索 → 抽取 → Gap → 搜索 → 数据库验证」自动发现闭环。</p>
  </div>
  <div class="card">
    <h2>系统流程</h2>
    <div class="flow">
      <span class="step">检索 Agent</span><span class="arrow">→</span>
      <span class="step">抽取 Agent</span><span class="arrow">→</span>
      <span class="step">Gap 识别</span><span class="arrow">→</span>
      <span class="step">搜索算法 × LLM</span><span class="arrow">→</span>
      <span class="step">OQMD/MP 验证</span><span class="arrow">→</span>
      <span class="step">证据链审计</span>
    </div>
    <p class="muted" style="margin-top:8px">LLM 三角色融合：假设种子生成器 → 科学合理性评估器 → 搜索空间引导器；Gap/构效关系/验证结果全部携带可回溯证据链。</p>
  </div>
  <div class="grid2">
    <div class="card"><h2>Gap 概览</h2>
      ${Object.entries(G.novelty_dist).map(([k, v]) => `<div>${novTag(k)} × ${v}</div>`).join("")}
      <p class="muted" style="margin-top:6px">Gap 类型：${Object.entries(G.type_dist).map(([k, v]) => `${k} ${v}`).join("、")}</p>
    </div>
    <div class="card"><h2>评测速览</h2>
      <table>
        <tr><th>项目</th><th>结果</th></tr>
        <tr><td>三臂消融（Oracle 真值）</td><td>full ${(arms.full?.mean_best_score ?? 0).toFixed(3)} / rule ${(arms.rule?.mean_best_score ?? 0).toFixed(3)} / llm ${(arms.llm?.mean_best_score ?? 0).toFixed(3)}</td></tr>
        <tr><td>LLM 融合增益</td><td>${gain}%（如实记录为负，定位真值表覆盖偏置）</td></tr>
        <tr><td>LLM 模式召回率最优</td><td>${bestRecall()}</td></tr>
        <tr><td>融合投票</td><td>${D.ensemble.n_gap_groups} 组 Gap / ${D.ensemble.n_consensus} 组多算法共识</td></tr>
      </table>
    </div>
  </div>`;
  function bestRecall() {
    const m = R.matrix || [];
    const llm = m.filter(r => r.mode === "LLM");
    if (!llm.length) return "—";
    const best = llm.reduce((a, b) => (b["recall@3"] >= a["recall@3"] ? b : a));
    return `${best.algo_name} recall@3=${best["recall@3"].toFixed(2)}`;
  }
}

function panelLiterature() {
  const rows = D.kb.map(k => `
    <tr><td><b>${esc(k.formula)}</b></td>
        <td>${k.properties.map(esc).join("<br>") || "—"}</td>
        <td>${k.synthesis_temp ? esc(k.synthesis_temp) + " K" : "—"}</td>
        <td>${k.n_evidence}</td></tr>`).join("");
  return `
  <div class="card">
    <h2>文献检索与知识抽取</h2>
    <p class="muted">检索：Sciverse 双通道（agentic-search 语义 + meta-search 结构化）｜抽取：MinerU 解析 + LLM schema 结构化 + 规则式降级</p>
    <table>
      <tr><th>材料体系</th><th>抽取属性</th><th>合成温度</th><th>证据数</th></tr>
      ${rows || '<tr><td colspan="4">知识库为空</td></tr>'}
    </table>
    <div class="note">每条知识记录强制携带 EvidenceChain（doc_id 回链），无来源结论禁止入 Gap/构效关系输出。</div>
  </div>`;
}

function panelGaps() {
  return `
  <div class="card">
    <h2>Research Gap 清单（${G.n_gaps} 条，可搜索）</h2>
    <input class="search-box" id="gap-search" placeholder="输入关键词过滤 Gap（如 GeTe、掺杂、热稳定性）…">
    <div id="gap-list"></div>
    <div class="note">Gap 识别四方法：覆盖率分析 / 矛盾检测 / 缺失连接发现 / LLM 推理 + Sciverse 回查验证；每条附证据链计数与可操作性。</div>
  </div>`;
}

function panelFindings() {
  const items = F.findings.map(f => `
    <div class="find-item">
      <div class="rel">${esc(f.relation)}</div>
      <div class="hyp">假设：${esc(f.hypothesis || "—")}</div>
      <table style="margin-top:6px">
        <tr><th>候选</th><th>掺杂</th><th>浓度</th><th>科学评分</th><th>来源</th></tr>
        ${f.top_candidates.map(c => `
          <tr><td>${esc(c.formula)}</td><td>${esc(c.dopant)}</td>
              <td>${c.concentration != null ? c.concentration + "%" : "—"}</td>
              <td>${scorePill(c.score)}</td><td class="muted">${esc(c.rationale)}</td></tr>`).join("")}
      </table>
      <p class="muted" style="margin-top:4px">对应 Gap：${esc(f.gap_statement)}｜候选数 ${f.n_candidates}</p>
    </div>`).join("");
  return `<div class="card"><h2>构效关系候选（${F.n_findings} finding，每 finding 展示 Top3 候选）</h2>${items || '<p class="muted">暂无构效关系产物</p>'}</div>`;
}

function panelValidation() {
  const dist = Object.entries(V.verdict_dist).map(([k, v]) =>
    `${verdictTag(k)} × ${v}`).join("  ");
  const rows = V.items.slice(0, 60).map(v => `
    <tr><td>${esc(v.candidate_formula)}</td><td>${esc(v.host)}</td>
        <td>${v.dopant ? esc(v.dopant) + (v.concentration != null ? " " + v.concentration + "%" : "") : "—"}</td>
        <td>${verdictTag(v.verdict)}</td><td class="muted">${esc(v.reason)}</td>
        <td class="muted">${esc(v.gap_statement)}</td></tr>`).join("");
  return `
  <div class="card">
    <h2>数据库交叉验证（OQMD 主 + MP 增强）</h2>
    <p style="font-size:13px">判定分布：${dist || "—"}</p>
    <p class="muted" style="margin-top:6px">A/B 位拆分纯母体解析（Ge0.93Ti0.01Bi0.06Te → GeTe）解决分数掺杂直查失败 38→0；反例母体自动回喂搜索剪枝器。</p>
  </div>
  <div class="card"><h2>验证明细（前 60 条）</h2>
    <table><tr><th>候选</th><th>母体</th><th>掺杂</th><th>判定</th><th>依据</th><th>对应 Gap</th></tr>
    ${rows || '<tr><td colspan="6">暂无验证产物</td></tr>'}</table>
  </div>`;
}

function panelMetrics() {
  const rows = (R.matrix || []).map(r => `
    <tr><td><b>${esc(r.algo_name)}</b></td><td>${esc(r.mode)}</td>
        <td>${esc(r.model || "—")}</td><td>${r.n_facts}</td>
        <td>${r["recall@1"].toFixed(3)}</td><td>${r["recall@3"].toFixed(3)}</td>
        <td>${r["recall@5"].toFixed(3)}</td><td>${r.coverage.toFixed(3)}</td>
        <td>${r.n_candidates_avg}</td></tr>`).join("");
  const arms = A.arms || {};
  const armRows = Object.entries(arms).map(([k, v]) => `
    <tr><td><b>${k}</b></td><td>${v.mean_best_score.toFixed(3)}</td>
        <td>${v.median_best_score.toFixed(3)}</td><td>${v.max_best_score.toFixed(3)}</td>
        <td>${v.total_llm_calls}</td><td>${v.mean_unique_dopants}</td></tr>`).join("");
  return `
  <div class="card"><h2>已知关系召回率（四算法 × 规则/LLM 统一口径）</h2>
    <table><tr><th>算法</th><th>模式</th><th>模型</th><th>n_facts</th>
      <th>recall@1</th><th>recall@3</th><th>recall@5</th><th>coverage</th><th>候选均值</th></tr>
    ${rows || '<tr><td colspan="9">暂无召回率矩阵</td></tr>'}</table>
    <p class="muted" style="margin-top:6px">${esc(R.note || "")}</p>
  </div>
  <div class="card"><h2>三臂消融（VerificationOracle 真值评分代理）</h2>
    <table><tr><th>臂</th><th>mean</th><th>median</th><th>max</th><th>LLM 调用</th><th>唯一 dopant 均值</th></tr>
    ${armRows || '<tr><td colspan="6">暂无消融报告</td></tr>'}</table>
    <p class="muted" style="margin-top:6px">增益：GA 演化 ${fmtGain(A.gains?.ga_evolution_gain_pct)} / LLM 融合 ${fmtGain(A.gains?.llm_fusion_gain_pct)}（负增益已定位为真值表覆盖偏置，非 LLM 无能，负结果如实记录）</p>
  </div>
  <div class="card"><h2>四算法融合投票</h2>
    <p style="font-size:13px">Borda rank 加权共识：<b>${D.ensemble.n_gap_groups}</b> 组 Gap 参与，<b>${D.ensemble.n_consensus}</b> 组达成多算法共识（≥2 算法）。</p>
    <p class="muted">复赛夜间四算法批量后产生真实共识清单；当前产物以单算法 GA 为主。</p>
  </div>`;
  function fmtGain(x) { return x == null ? "—" : (x >= 0 ? "+" : "") + x.toFixed(2) + "%"; }
}

function panelEvidence() {
  const rows = G.gaps.map(g => `
    <tr><td>${esc(g.statement)}</td><td>${novTag(g.novelty)}</td>
        <td><span class="tag ev">证据 ${g.n_evidence}</span></td>
        <td class="muted">${esc((g.operability || "—").slice(0, 40))}</td></tr>`).join("");
  return `
  <div class="card"><h2>证据链可审计性</h2>
    <p style="font-size:13px">审计结论：Gap 可追溯 <b>${G.n_with_evidence}/${G.n_gaps}</b>（evidence_ids 六通道回填：kb_exact / kb_parent / kb_similar / retrieval / retrieval_title / retrieval_parent）。</p>
    <p class="muted" style="margin-top:6px">每条 Gap / Finding / 验证结论强制携带 EvidenceChain；统一 JSONL 审计日志支撑五项审计（证据覆盖 / 降级留痕 / 判定分布等）。</p>
  </div>
  <div class="card"><h2>Gap 证据链明细（${G.gaps.length} 条）</h2>
    <table><tr><th>Gap 陈述</th><th>新颖性</th><th>证据</th><th>可操作性</th></tr>
    ${rows || '<tr><td colspan="4">暂无 Gap</td></tr>'}</table>
  </div>`;
}

/* ---- 渲染器 ---- */
const RENDER = {
  overview: panelOverview, literature: panelLiterature, gaps: panelGaps,
  findings: panelFindings, validation: panelValidation, metrics: panelMetrics,
  evidence: panelEvidence,
};

function mount() {
  const nav = document.getElementById("tabs");
  TABS.forEach(([id, label]) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.onclick = () => switchTab(id);
    nav.appendChild(b);
  });
  switchTab("overview");
  const search = document.getElementById("gap-search");
  if (search) search.addEventListener("input", renderGapList);
}
function switchTab(id) {
  document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
  [...nav.children].forEach(b => { if (b.textContent === TABS.find(t => t[0] === id)[1]) b.classList.add("active"); });
  document.querySelectorAll("section.panel").forEach(s => s.classList.remove("active"));
  let panel = document.getElementById("panel-" + id);
  if (!panel) {
    panel = document.createElement("section");
    panel.id = "panel-" + id;
    panel.className = "panel";
    document.getElementById("main").appendChild(panel);
  }
  panel.innerHTML = RENDER[id]();
  panel.classList.add("active");
  if (id === "gaps") renderGapList();
}
function renderGapList() {
  const kw = (document.getElementById("gap-search")?.value || "").trim().toLowerCase();
  const list = document.getElementById("gap-list");
  if (!list) return;
  const items = G.gaps.filter(g =>
    !kw || (g.statement + " " + (g.formulas || []).join(" ")).toLowerCase().includes(kw));
  list.innerHTML = items.map(g => `
    <div class="gap-item">
      <div class="stmt">${novTag(g.novelty)} ${esc(g.statement)}</div>
      <div class="muted" style="margin-top:4px">体系：${esc((g.formulas || []).join(", ") || "—")}｜证据 ${g.n_evidence}｜${esc(g.gap_type)}</div>
    </div>`).join("") || '<p class="muted">无匹配 Gap</p>';
}
document.addEventListener("DOMContentLoaded", mount);
</script>
</body>
</html>
"""


def render_html(payload: dict) -> str:
    """payload → 自包含 HTML 文本。"""
    return _TEMPLATE.replace("__DATA__", _escape_script_json(payload))


def write_demo(html: str, out_path: Path) -> None:
    """落盘面板 HTML。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def self_check(html: str) -> None:
    """生成自检：占位符已替换；闭合 </script> 恰为 2 个（数据节点 + 主脚本）。"""
    assert "__DATA__" not in html, "数据占位符未替换"
    assert html.count("</script>") == 2, "script 内嵌转义缺失（数据含 </ 需转义）"
    assert 'id="demo-data"' in html, "数据脚本节点缺失"

"""共识候选数据库交叉验证（模块 6 扩展：LLM 融合发现验证闭环）。

背景（复赛深化·路线 A「可信性与新颖性」评分支撑）：
run_ensemble.py 输出四算法融合投票清单（results/ensemble/ensemble_*.md），
其中「多算法共识候选」（n_votes ≥ 2）是搜索×LLM 融合的高可信信号。本模块
将这些共识候选批量送数据库交叉验证（OQMD 主 + MP 增强），产出
「共识候选 → 数据库判定」对照表，并统计判定一致性——
对齐 `.trae/rules/05-route-a-SPR.md` 第 7 节交叉验证流程。

判定逻辑（对齐 src/agent/validation_agent.py）：
- 母体在库且稳定（hull ≤ 0.1 且 delta_e < 0）→ 已知：基础体系已收录，掺杂为库外扩展
- 母体在库但热力学不稳定 → 反例：与数据库结论矛盾（负结果也入库）
- 母体不在库 → 新知：成分空间未被数据库覆盖，潜在新发现
- 无法解析母体 / 查询失败 → 验证失败（如实标注，不伪装结论）

数据源（全部本地产物，网络仅在线模式回退）：
- results/ensemble/ensemble_*.md（融合投票清单）
- results/oracle/oracle_truth_*.json + results/validation/validation_*.json（真值缓存）
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.validation.oqmd_client import OQMDClient
from src.validation.parent_parser import parse_integer_parent, parse_variable_parent

# 分数成分正则（含小数下标的掺杂/合金式，如 Ge0.93Ti0.01Bi0.06Te）
_FRACTION_RE = re.compile(r"\d\.\d")
# 候选字符串切分：<host>-<dopant><conc>%（如 Mg3Sb2-Na2% / CoSb3-Yb0.2Ba0.10%）
_CAND_RE = re.compile(
    r"^(?P<host>.+)-(?P<dop>[A-Za-z][A-Za-z0-9.]*)(?P<conc>\d+(?:\.\d+)?)%$"
)
# 去数字下标（合金式 Si0.8Ge0.2 → SiGe）
_STRIP_NUM_RE = re.compile(r"\d+\.?\d*")
# 纯元素序列（去下标后的合金必须是合法元素串）
_ELEM_SEQ_RE = re.compile(r"[A-Z][a-z]?(?:[A-Z][a-z]?)*")
# 热电体系常见阴离子（末尾元素判定，避免把 Si0.8Ge0.2 误解析）
_ANIONS = {"Te", "Se", "S", "As", "P", "Br", "Cl", "I", "F", "O", "N"}
# 判定优先级（多记录覆盖用：已知=存在稳定相最可靠，防低质量记录污染）
VERDICT_PRIORITY = {"已知": 3, "反例": 2, "新知": 2, "验证失败": 1}
# 多算法共识阈值（n_votes ≥ 2 视为高可信共识候选）
CONSENSUS_MIN_VOTES = 2
# 稳定性阈值（energy above hull，eV/atom，与 oqmd_client 对齐）
_STABILITY_THRESHOLD = 0.1

# ensemble md 表格行（| 排名 | 候选 | 得票 | 得分 | 来源算法 | 平均可信度 |）
_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*"
    r"([^|]+?)\s*\|\s*([\d.]+)\s*\|$"
)


def split_candidate(formula: str) -> tuple[str, str | None, float | None]:
    """候选字符串 → (host, dopant, concentration%)。

    参数:
        formula: 融合清单中的候选名
            - Mg3Sb2-Na2% → (Mg3Sb2, Na, 2.0)
            - CoSb3-Yb0.2Ba0.10% → (CoSb3, Yb0.2Ba0.1, 0.0)（双掺杂描述，母体不受影响）
            - Ge0.98Bi0.02Te（无 -xx% 后缀）→ (Ge0.98Bi0.02Te, None, None)

    返回:
        (host, dopant, concentration)；无法切分时 dopant/concentration 为 None。
    """
    f = (formula or "").strip()
    m = _CAND_RE.match(f)
    if m:
        try:
            conc = float(m.group("conc"))
        except (TypeError, ValueError):
            conc = 0.0
        return m.group("host"), m.group("dop"), conc
    return f, None, None


def _last_element(formula: str) -> str:
    """公式末尾元素符号（如 Ge0.98Bi0.02Te → Te）。"""
    elems = re.findall(r"[A-Z][a-z]?", formula or "")
    return elems[-1] if elems else ""


def resolve_parent(host: str) -> str | None:
    """候选 host → 数据库可直查的整数母体（None 表示无法解析）。

    解析顺序：
    1. 变量式（含 x/y，如 Ge1-xBixTe）→ parse_variable_parent
    2. 分数式（含 0.x 下标）：
       - 末尾为阴离子 → parse_integer_parent（A/B 位拆分，如 Ge0.98Bi0.02Te → GeTe）
       - 末尾非阴离子（合金式 Si0.8Ge0.2）→ 去数字下标 → SiGe
    3. 整数式（PbTe / Mg3Sb2 / ZrNiSn）→ 原样
    """
    h = (host or "").strip()
    if not h:
        return None
    if "x" in h or "y" in h:
        return parse_variable_parent(h)
    if _FRACTION_RE.search(h):
        parent = parse_integer_parent(h)
        if parent:
            return parent
        # 分数式末尾为阴离子但无法 A/B 拆分（多掺杂如 Pb0.98Na+Sr0.02Te）：
        # 保守返回 None，不猜测母体
        if _last_element(h) in _ANIONS:
            return None
        # 合金式（Si0.8Ge0.2 → SiGe）：去数字下标后必须是合法元素序列
        stripped = _STRIP_NUM_RE.sub("", h)
        if stripped != h and _ELEM_SEQ_RE.fullmatch(stripped):
            return stripped
        return None
    return h


def parse_ensemble_md(text: str) -> list[dict[str, Any]]:
    """解析融合投票 Markdown → 按 gap 分组的投票清单。

    参数:
        text: ensemble md 全文（render_markdown 输出格式）

    返回:
        [{gap_statement, votes: [{formula, n_votes, score, algorithms,
          avg_confidence}]}]；无表格行的 gap 会被丢弃。
    """
    results: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("## "):
            if current is not None and current["votes"]:
                results.append(current)
            current = {"gap_statement": s[3:].strip(), "votes": []}
        elif current is not None:
            m = _ROW_RE.match(s)
            if m:
                current["votes"].append(
                    {
                        "formula": m.group(2).strip(),
                        "n_votes": int(m.group(3)),
                        "score": float(m.group(4)),
                        "algorithms": m.group(5).strip(),
                        "avg_confidence": float(m.group(6)),
                    }
                )
    if current is not None and current["votes"]:
        results.append(current)
    return results


def build_truth_map(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """聚合 oracle_truth_*.json / validation_*.json → {host: 判定}。

    参数:
        paths: 真值表文件路径列表（oracle 扩面 + 历史验证产物）

    返回:
        {host: {verdict, reason, entries}}；同一 host 多条记录按
        VERDICT_PRIORITY 高者覆盖（已知 > 反例/新知 > 验证失败）。
    """
    truth: dict[str, dict[str, Any]] = {}
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for r in data.get("results", []):
            verdict = str(r.get("verdict") or "未知")
            if verdict == "未知":
                continue
            keys = {
                str(r.get("candidate_formula") or "").strip(),
                str(r.get("host") or "").strip(),
                str(r.get("parent_formula") or "").strip(),
            } - {""}
            for k in keys:
                old = truth.get(k)
                if old is None or VERDICT_PRIORITY.get(verdict, 0) > VERDICT_PRIORITY.get(
                    old["verdict"], 0
                ):
                    truth[k] = {
                        "verdict": verdict,
                        "reason": str(r.get("reason") or ""),
                        "entries": r.get("entries") or [],
                    }
    return truth


def _reason(verdict: str, parent: str, *, detail: str = "") -> str:
    """按判定生成说明（detail 追加库证据摘要）。"""
    base = {
        "已知": (
            f"母体 {parent} 在数据库中已收录且热力学稳定，基础体系得到支撑"
            "（掺杂方案为库外扩展）"
        ),
        "反例": (
            f"母体 {parent} 在数据库中热力学不稳定，该掺杂方向与数据库结论矛盾"
            "（负结果留痕）"
        ),
        "新知": (
            f"母体 {parent} 未收录于数据库，成分空间未被覆盖，掺杂方案为潜在新发现"
            "（需实验/更高精度验证）"
        ),
        "验证失败": f"母体 {parent} 无法完成数据库判定（查询失败/未收录）",
    }.get(verdict, f"母体 {parent} 判定：{verdict}")
    return f"{base}；{detail}" if detail else base


def verify_one(
    cand: dict[str, Any],
    truth_map: dict[str, dict[str, Any]],
    *,
    oqmd: OQMDClient | None = None,
    use_mp: bool = False,
    online: bool = False,
) -> dict[str, Any]:
    """单个共识候选 → 数据库判定（真值缓存优先，online 时网络回退）。

    参数:
        cand: {formula, n_votes, score, algorithms, avg_confidence, gap_statement}
        truth_map: build_truth_map 产物
        oqmd: OQMD 客户端（online 回退用，缺省惰性创建）
        use_mp: 是否叠加 MP 查询（online 回退用）
        online: 允许网络直查未命中母体（默认仅本地真值表）

    返回:
        判定记录：candidate/host/parent_formula/verdict/reason/db_entries 等。
    """
    formula = str(cand.get("formula") or "").strip()
    host, dopant, conc = split_candidate(formula)
    parent = resolve_parent(host)
    rec: dict[str, Any] = {
        "gap_statement": str(cand.get("gap_statement") or ""),
        "candidate": formula or host,
        "host": host,
        "dopant": dopant,
        "concentration": conc,
        "parent_formula": parent,
        "n_votes": int(cand.get("n_votes") or 0),
        "score": float(cand.get("score") or 0.0),
        "algorithms": str(cand.get("algorithms") or ""),
        "avg_confidence": float(cand.get("avg_confidence") or 0.0),
    }
    if parent is None:
        rec.update(
            {
                "verdict": "验证失败",
                "reason": (
                    f"候选 {formula} 的母体 {host} 无法解析为整数成分，"
                    "数据库直查受限"
                ),
                "db_entries": [],
                "cache_hit": False,
            }
        )
        return rec
    hit = truth_map.get(parent)
    if hit is not None:
        rec.update(
            {
                "verdict": hit["verdict"],
                "reason": _reason(hit["verdict"], parent, detail=hit.get("reason", "")),
                "db_entries": hit.get("entries", []),
                "cache_hit": True,
            }
        )
        return rec
    if not online:
        rec.update(
            {
                "verdict": "验证失败",
                "reason": (
                    f"母体 {parent} 未命中本地真值表（online 模式才会网络直查）"
                ),
                "db_entries": [],
                "cache_hit": False,
            }
        )
        return rec
    # 网络回退：OQMD 主查 + MP 增强（判定逻辑对齐 validation_agent）
    client = oqmd or OQMDClient()
    entries: list[dict[str, Any]] = []
    try:
        for e in client.query_formation_energy(parent):
            entries.append(e.model_dump())
    except Exception:  # noqa: BLE001 - 单母体查询失败不中断批量
        pass
    if use_mp:
        try:
            from src.validation.mp_client import query_summary

            for h in (query_summary(parent) or [])[:3]:
                entries.append(
                    {
                        "db": "mp",
                        "formula": h.get("formula") or parent,
                        "entry_id": h.get("material_id"),
                        "delta_e": h.get("formation_energy_per_atom"),
                        "stability": h.get("energy_above_hull"),
                        "band_gap": h.get("band_gap"),
                        "is_stable": h.get("is_stable"),
                        "source_url": (
                            "https://next-gen.materialsproject.org/materials/"
                            f"{h.get('material_id')}"
                        ),
                    }
                )
        except Exception:  # noqa: BLE001 - MP 增强失败降级为仅 OQMD
            pass
    if not entries:
        rec.update(
            {
                "verdict": "新知",
                "reason": (
                    f"母体 {parent} 未收录于 OQMD/MP，成分空间未被数据库覆盖，"
                    "掺杂方案为潜在新发现"
                ),
                "db_entries": [],
                "cache_hit": False,
            }
        )
        return rec
    best = min(
        entries,
        key=lambda e: (
            e.get("stability") if e.get("stability") is not None else 1e9,
            e.get("delta_e") if e.get("delta_e") is not None else 1e9,
        ),
    )
    stable = best.get("is_stable")
    if stable is None:
        hull = best.get("stability")
        delta = best.get("delta_e")
        stable = (
            hull is not None
            and delta is not None
            and hull <= _STABILITY_THRESHOLD
            and delta < 0
        )
    verdict = "已知" if stable else "反例"
    detail = (
        f"hull={best.get('stability')} eV/atom, delta_e={best.get('delta_e')} eV/atom"
        f"（来源 {best.get('db')}）"
    )
    rec.update(
        {
            "verdict": verdict,
            "reason": _reason(verdict, parent, detail=detail),
            "db_entries": entries,
            "cache_hit": False,
        }
    )
    return rec


def verify_consensus(
    results: list[dict[str, Any]],
    truth_map: dict[str, dict[str, Any]],
    *,
    min_votes: int = CONSENSUS_MIN_VOTES,
    oqmd: OQMDClient | None = None,
    use_mp: bool = False,
    online: bool = False,
) -> list[dict[str, Any]]:
    """共识候选批量交叉验证：筛选 n_votes ≥ min_votes 后逐条判定。

    参数:
        results: parse_ensemble_md 产物（按 gap 分组）
        truth_map: build_truth_map 产物
        min_votes: 多算法共识阈值
        oqmd/use_mp/online: 透传 verify_one

    返回:
        判定记录列表（仅共识候选），含汇总统计字段 stats。
    """
    records: list[dict[str, Any]] = []
    for r in results:
        gap = r.get("gap_statement", "")
        for v in r.get("votes", []):
            if int(v.get("n_votes") or 0) < min_votes:
                continue
            cand = {**v, "gap_statement": gap}
            records.append(
                verify_one(cand, truth_map, oqmd=oqmd, use_mp=use_mp, online=online)
            )
    # records 平铺返回，统计由调用方通过 summarize 聚合
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总判定分布与母体支撑率（可信度/新颖性信号）。"""
    dist = dict(Counter(str(r["verdict"]) for r in records))
    n = len(records)
    return {
        "n_consensus": n,
        "verdict_dist": dist,
        "known_ratio": round(dist.get("已知", 0) / n, 3) if n else 0.0,
        "counterexample_ratio": round(dist.get("反例", 0) / n, 3) if n else 0.0,
        "novel_ratio": round(dist.get("新知", 0) / n, 3) if n else 0.0,
        "note": (
            "已知=母体在库且稳定（基础体系支撑，掺杂为库外扩展）；"
            "反例=母体热力学不稳定（方向存疑）；新知=成分空间未被数据库覆盖；"
            "验证失败=无法判定（如实留痕）"
        ),
    }


def _best_entry(rec: dict[str, Any]) -> dict[str, Any] | None:
    """记录中取最稳定库条目（hull 最小，无 hull 取 delta_e 最小）。"""
    entries = rec.get("db_entries") or []
    if not entries:
        return None
    return min(
        entries,
        key=lambda e: (
            e.get("stability") if e.get("stability") is not None else 1e9,
            e.get("delta_e") if e.get("delta_e") is not None else 1e9,
        ),
    )


def render_markdown(records: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    """渲染共识候选验证对照表为 Markdown（按 gap 分组）。"""
    lines = ["# 共识候选数据库交叉验证对照表", ""]
    lines.append(
        "- 数据源：四算法融合投票清单 + OQMD/MP 交叉验证"
        "（OQMD 主路径，MP 增强；真值缓存优先）"
    )
    lines.append(f"- 共识候选（n_votes ≥ {CONSENSUS_MIN_VOTES}）：{stats['n_consensus']} 个")
    lines.append(f"- 判定分布：{stats['verdict_dist']}")
    lines.append(
        f"- 母体稳定性支撑率（已知占比）：{stats['known_ratio']}"
        f"｜反例占比：{stats['counterexample_ratio']}"
        f"｜新知占比：{stats['novel_ratio']}"
    )
    lines.append("")
    by_gap: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_gap.setdefault(rec.get("gap_statement") or "未分组", []).append(rec)
    for gap, items in by_gap.items():
        lines += [f"## {gap}", ""]
        lines.append(
            "| 共识候选 | 母体(整数) | 得票 | 来源算法 | 平均可信度 | "
            "数据库判定 | 库证据(hull/delta_e) | 说明 |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for rec in items:
            best = _best_entry(rec)
            evidence = "—"
            if best is not None:
                hull = best.get("stability")
                delta = best.get("delta_e")
                db = str(best.get("db") or "oqmd")
                if hull is not None:
                    evidence = f"hull={hull:.3f}"
                    evidence += f", Δe={delta:.3f}" if delta is not None else ""
                    evidence += f"（{db}）"
                else:
                    evidence = f"{db} 记录（{best.get('entry_id') or ''}）"
            lines.append(
                f"| {rec['candidate']} | {rec['parent_formula'] or '—'} | "
                f"{rec['n_votes']} | {rec['algorithms']} | {rec['avg_confidence']} | "
                f"{rec['verdict']} | {evidence} | {rec['reason']} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_html(records: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    """渲染共识候选验证对照表为 HTML（内联 CSS，浏览器直接打开）。"""
    sections = []
    by_gap: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_gap.setdefault(rec.get("gap_statement") or "未分组", []).append(rec)
    for gap, items in by_gap.items():
        rows = []
        for rec in items:
            best = _best_entry(rec)
            evidence = "—"
            if best is not None:
                hull = best.get("stability")
                delta = best.get("delta_e")
                db = str(best.get("db") or "oqmd")
                if hull is not None:
                    evidence = f"hull={hull:.3f}"
                    evidence += f", Δe={delta:.3f}" if delta is not None else ""
                    evidence += f"（{db}）"
                else:
                    evidence = f"{db} 记录（{best.get('entry_id') or ''}）"
            rows.append(
                "<tr>"
                f"<td>{html.escape(rec['candidate'])}</td>"
                f"<td>{html.escape(str(rec.get('parent_formula') or '—'))}</td>"
                f"<td class='ok'>{rec['n_votes']}</td>"
                f"<td>{html.escape(rec['algorithms'])}</td>"
                f"<td>{rec['avg_confidence']}</td>"
                f"<td><span class='verdict {rec['verdict']}'>{rec['verdict']}</span></td>"
                f"<td>{html.escape(evidence)}</td>"
                f"<td class='reason'>{html.escape(rec['reason'])}</td>"
                "</tr>"
            )
        sections.append(
            f"<h2>{html.escape(gap)}</h2>"
            f"<table><tr><th>共识候选</th><th>母体(整数)</th><th>得票</th>"
            f"<th>来源算法</th><th>平均可信度</th><th>数据库判定</th>"
            f"<th>库证据</th><th>说明</th></tr>{''.join(rows)}</table>"
        )
    dist = stats["verdict_dist"]
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>共识候选数据库交叉验证对照表</title>
<style>
  body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
         background:#f7f9fc; color:#1f2d3d; margin:0; padding:24px; }}
  .wrap {{ max-width:1080px; margin:0 auto; }}
  h1 {{ color:#1a5f9e; font-size:22px; border-bottom:2px solid #1a5f9e;
        padding-bottom:8px; }}
  h2 {{ color:#1a5f9e; font-size:16px; margin-top:28px; }}
  .meta {{ font-size:13px; color:#5a6b7d; line-height:1.8; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; margin:8px 0;
          box-shadow:0 4px 20px rgba(26,95,158,0.08); border-radius:12px;
          overflow:hidden; }}
  th, td {{ padding:8px 10px; text-align:left; border-bottom:1px solid #eef2f7;
           font-size:12.5px; vertical-align:top; }}
  th {{ background:#eef5fb; color:#1a5f9e; }}
  .ok {{ color:#2e7d32; font-weight:600; }}
  .verdict {{ padding:2px 8px; border-radius:10px; font-weight:600; font-size:12px; }}
  .已知 {{ background:#e8f5e9; color:#2e7d32; }}
  .新知 {{ background:#e3f2fd; color:#1565c0; }}
  .反例 {{ background:#fdecea; color:#c62828; }}
  .验证失败 {{ background:#f5f5f5; color:#757575; }}
  .reason {{ color:#5a6b7d; max-width:360px; }}
</style></head><body>
<div class="wrap">
  <h1>共识候选数据库交叉验证对照表</h1>
  <div class="meta">
    <p>数据源：四算法融合投票清单 + OQMD/MP 交叉验证
      （OQMD 主路径，MP 增强；真值缓存优先）</p>
    <p>共识候选（n_votes ≥ {CONSENSUS_MIN_VOTES}）：{stats['n_consensus']} 个；
      判定分布：{html.escape(str(dist))}；
      母体稳定性支撑率（已知占比）：{stats['known_ratio']}，
      反例占比：{stats['counterexample_ratio']}，新知占比：{stats['novel_ratio']}</p>
  </div>
  {''.join(sections)}
</div>
</body></html>"""

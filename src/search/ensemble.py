"""四算法输出融合投票：GA / MCTS / BO / SR 候选 → 共识清单。

对齐 `.trae/rules/05-route-a-SPR.md`：四算法独立探索组合空间，各自
输出 top_candidates；融合投票将「多算法共识」作为候选可信度信号——
同一候选被越多算法推荐、排名越靠前，越值得进入最终构效关系清单。

投票计分（跨算法可比，不受候选数影响）：
- 每个算法对其 top_candidates 排名：第 rank 名贡献权重 1/rank
- 同一算法内同一候选只计最高排名（去重防刷票）
- 候选总得分 = Σ(1/rank)；得票数 n_votes = 推荐该候选的算法数
- 排序：得票数降序 → 总得分降序 → 取 top_k

数据源（全部本地产物，无网络）：
- results/findings/finding_*.json（payload 含 algo / gap_statement /
  top_candidates / evidence_ids，`algo` 缺省 unknown 向后兼容）

输出：按 gap 分组的融合投票清单（含候选、得票、来源算法、证据链并集）。
"""
from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.extraction.extractor import normalize_formula

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
TOP_K = 10

# 候选 key 的浓度取整精度（0.5 步长，吸收 GA 交叉均值/BO 采集的浓度抖动）
_CONC_STEP = 2.0


def candidate_key(candidate: dict[str, Any]) -> tuple[str, str, float]:
    """候选归一化键：host 归一化 + dopant 大写 + 浓度 0.5 步长取整。

    同一 (母体, 掺杂, 浓度≈) 的候选视为同一投票对象。
    """
    host = normalize_formula(str(candidate.get("host") or "")).upper()
    dopant = str(candidate.get("dopant") or "").upper()
    try:
        conc = float(candidate.get("concentration") or 0)
    except (TypeError, ValueError):
        conc = 0.0
    conc = round(conc * _CONC_STEP) / _CONC_STEP  # 4.1→4.0、4.4→4.5
    return (host, dopant, conc)


def _candidate_confidence(candidate: dict[str, Any]) -> float:
    """候选科学合理性分（scores.scientific，缺失记 0）。"""
    scores = candidate.get("scores") or {}
    if not isinstance(scores, dict):
        return 0.0
    try:
        return float(scores.get("scientific") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def ensemble_vote(
    candidates_by_algo: dict[str, list[dict[str, Any]]],
    top_k: int = TOP_K,
) -> dict[str, Any]:
    """对四算法候选做融合投票。

    参数:
        candidates_by_algo: {算法名: 候选列表}（候选须含 host/dopant/
            concentration/formula，scores.scientific 可选）
        top_k: 输出候选数上限

    返回:
        融合投票结果：n_algorithms / algorithms / votes（得票降序 top_k）/
        n_votes_total。
    """
    votes: dict[tuple[str, str, float], dict[str, Any]] = {}
    for algo, cands in candidates_by_algo.items():
        seen: set[tuple[str, str, float]] = set()
        for rank, c in enumerate(cands or [], 1):
            key = candidate_key(c)
            if key in seen:  # 同算法重复候选只计最高排名
                continue
            seen.add(key)
            entry = votes.setdefault(
                key,
                {
                    "host": str(c.get("host") or ""),
                    "dopant": str(c.get("dopant") or ""),
                    "concentration": float(c.get("concentration") or 0.0),
                    "formula": str(c.get("formula") or ""),
                    "n_votes": 0,
                    "score": 0.0,
                    "algorithms": [],
                    "rank_by_algo": {},
                    "confidences": [],
                },
            )
            entry["n_votes"] += 1
            entry["score"] += 1.0 / rank
            entry["algorithms"].append(algo)
            entry["rank_by_algo"][algo] = rank
            entry["confidences"].append(_candidate_confidence(c))
    ordered = []
    for key, e in votes.items():
        e["score"] = round(e["score"], 4)
        e["avg_confidence"] = round(
            sum(e["confidences"]) / len(e["confidences"]), 3
        ) if e["confidences"] else 0.0
        e.pop("confidences", None)
        ordered.append(e)
    ordered.sort(key=lambda e: (-e["n_votes"], -e["score"], e["host"]))
    return {
        "n_algorithms": len(candidates_by_algo),
        "algorithms": list(candidates_by_algo),
        "votes": ordered[:top_k],
        "n_votes_total": len(ordered),
    }


def load_findings(results_dir: Path = RESULTS_DIR) -> list[dict[str, Any]]:
    """读 results/findings/*.json，坏文件跳过，缺省 algo=unknown。"""
    findings: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("findings/finding_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        data.setdefault("algo", "unknown")
        data.setdefault("_file", path.name)
        findings.append(data)
    return findings


def ensemble_findings(
    findings: list[dict[str, Any]],
    top_k: int = TOP_K,
) -> list[dict[str, Any]]:
    """按 gap 分组融合投票：同 gap 的多算法 finding 投票 → 共识清单。

    参数:
        findings: load_findings 产物（含 algo / gap_statement / top_candidates）
        top_k: 每 gap 输出候选数上限

    返回:
        每 gap 一个融合结果（含 gap_statement / evidence_ids 并集 / 投票）。
    """
    by_gap: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    gap_meta: dict[str, dict[str, Any]] = {}
    for f in findings:
        gap = f.get("gap_statement") or ""
        if not gap:
            continue
        algo = f.get("algo") or "unknown"
        by_gap[gap].setdefault(algo, []).extend(f.get("top_candidates") or [])
        ids = list(dict.fromkeys(f.get("evidence_ids") or []))
        meta = gap_meta.setdefault(
            gap, {"gap_statement": gap, "evidence_ids": [], "n_findings": 0}
        )
        meta["evidence_ids"] = list(dict.fromkeys(meta["evidence_ids"] + ids))
        meta["n_findings"] += 1
    results: list[dict[str, Any]] = []
    for gap in by_gap:
        result = ensemble_vote(by_gap[gap], top_k=top_k)
        result.update(gap_meta[gap])
        results.append(result)
    results.sort(key=lambda r: (-r["n_votes_total"], r["gap_statement"]))
    return results


def run_ensemble(
    results_dir: Path = RESULTS_DIR, top_k: int = TOP_K
) -> list[dict[str, Any]]:
    """端到端：加载 findings → 按 gap 融合投票。"""
    return ensemble_findings(load_findings(results_dir), top_k=top_k)


# ---------- 渲染 ----------


def render_markdown(results: list[dict[str, Any]]) -> str:
    """渲染融合投票清单为 Markdown。"""
    lines = ["# 四算法融合投票（GA / MCTS / BO / SR）", ""]
    for r in results:
        lines += [
            f"## {r['gap_statement']}",
            "",
            f"- 算法数：{r['n_algorithms']}（{', '.join(r['algorithms'])}）"
            f"｜候选总数：{r['n_votes_total']}"
            f"｜finding：{r['n_findings']} 份",
            f"- 证据链 doc_id：{len(r['evidence_ids'])} 条",
            "",
            "| 排名 | 候选 | 得票 | 得分 | 来源算法 | 平均可信度 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for i, v in enumerate(r["votes"], 1):
            lines.append(
                f"| {i} | {v['formula'] or v['host']} | {v['n_votes']} | "
                f"{v['score']} | {', '.join(v['algorithms'])} | "
                f"{v['avg_confidence']} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_html(results: list[dict[str, Any]]) -> str:
    """渲染融合投票清单为 HTML（内联 CSS，浏览器直接打开）。"""
    sections = []
    for r in results:
        rows = "".join(
            f"<tr><td>{i}</td><td>{html.escape(v['formula'] or v['host'])}</td>"
            f"<td class='ok'>{v['n_votes']}</td><td>{v['score']}</td>"
            f"<td>{html.escape(', '.join(v['algorithms']))}</td>"
            f"<td>{v['avg_confidence']}</td></tr>"
            for i, v in enumerate(r["votes"], 1)
        )
        sections.append(
            f"<h2>{html.escape(r['gap_statement'])}</h2>"
            f"<p>算法 {r['n_algorithms']}（{html.escape(', '.join(r['algorithms']))}）"
            f"｜候选 {r['n_votes_total']}｜finding {r['n_findings']} 份"
            f"｜证据链 {len(r['evidence_ids'])} 条</p>"
            f"<table><tr><th>排名</th><th>候选</th><th>得票</th><th>得分</th>"
            f"<th>来源算法</th><th>平均可信度</th></tr>{rows}</table>"
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>四算法融合投票</title>
<style>
  body {{ font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
         background:#f7f9fc; color:#1f2d3d; margin:0; padding:24px; }}
  .wrap {{ max-width:960px; margin:0 auto; }}
  h1 {{ color:#1a5f9e; font-size:22px; border-bottom:2px solid #1a5f9e;
        padding-bottom:8px; }}
  h2 {{ color:#1a5f9e; font-size:16px; margin-top:28px; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; margin:8px 0;
          box-shadow:0 4px 20px rgba(26,95,158,0.08); border-radius:12px; overflow:hidden; }}
  th, td {{ padding:8px 12px; text-align:left; border-bottom:1px solid #eef2f7;
           font-size:13px; }}
  th {{ background:#eef5fb; color:#1a5f9e; }}
  .ok {{ color:#2e7d32; font-weight:600; }}
  p {{ font-size:13px; color:#5a6b7d; }}
</style></head><body><div class="wrap">
<h1>四算法融合投票（GA / MCTS / BO / SR）</h1>
{''.join(sections)}
</div></body></html>
"""

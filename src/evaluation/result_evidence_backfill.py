"""finding/验证产物 evidence_ids 回填核心逻辑（复用 Gap 六通道匹配）。

背景：Gap evidence_ids 经 `scripts/backfill_gap_evidence.py` 六通道回填后
29/29 全可追溯，但审计（`src/audit/evidence_report.py`）显示 finding 与
验证产物的 evidence_ids 覆盖仍偏低（finding 7/36、验证 15/47）——早期
findings/validation 产物生成时 Gap 尚无证据，未继承。本模块把同一套
六通道匹配能力扩展到下游结论，补齐「每个结论可回溯」的审计覆盖
（对齐 00-project-rules.md 4.1 证据链红线）。

回填语义（与 Gap 回填一致）：
- finding：evidence_ids 为空时，从 gap.formulas 与 top_candidates[].formula/host
  六通道匹配回填；已有证据（继承自 Gap）则保留并仅在可补强时新增。
- validation：顶层 evidence_ids 为空时，从 gap_statement + results[] 的
  candidate_formula / host / parent_formula 六通道匹配回填。
- 每条新增证据标注来源（source_map），写进 `evidence_backfill` 字段留痕；
  未匹配任何证据的条目保持空，审计如实列出（不编造）。

六通道定义见 `src/evaluation/gap_evidence_backfill.py` 模块 docstring。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.evaluation.gap_evidence_backfill import (
    load_json,
    load_kb_index,
    load_retrieval_papers,
    match_evidence_for_formula,
)


def _kb(kb_index: dict[str, dict] | None) -> dict[str, dict]:
    """None → 空索引（测试/无知识库场景容错）。"""
    return kb_index or {}


def _merge_ids(
    existing: list[str], evs: list[str], sources: dict[str, str],
) -> tuple[list[str], list[str], dict[str, str]]:
    """合并证据：已有在前、新增在后、去重保序。返回 (new_ids, added, added_sources)。"""
    seen = set(existing)
    added: list[str] = []
    added_sources: dict[str, str] = {}
    for ev in evs:
        if ev not in seen:
            added.append(ev)
            added_sources[ev] = sources[ev]
            seen.add(ev)
    return existing + added, added, added_sources


def backfill_finding(
    finding: dict,
    kb_index: dict[str, dict],
    papers: list[dict],
) -> tuple[dict, dict]:
    """单条 finding 回填：evidence_ids 为空时六通道匹配，返回 (finding, stats)。"""
    kb_index = _kb(kb_index)
    existing = list(finding.get("evidence_ids") or [])
    formulas: list[str] = []
    gap = finding.get("gap") or {}
    formulas.extend(str(f) for f in gap.get("formulas") or [])
    for cand in finding.get("top_candidates") or []:
        for key in ("host", "formula"):
            val = str(cand.get(key) or "").strip()
            if val and val not in formulas:
                formulas.append(val)

    added: list[str] = []
    added_sources: dict[str, str] = {}
    if not existing:  # 仅对无证据条目回填（已有继承 Gap 证据则保留）
        for formula in formulas:
            evs, src_map = match_evidence_for_formula(formula, kb_index, papers)
            if evs:
                new_ids, a, a_s = _merge_ids(existing, evs, src_map)
                added.extend(a)
                added_sources.update(a_s)
                existing = new_ids
                if added:
                    break  # 命中即停（与 Gap 回填一致的强度降序语义）

    if added:
        finding["evidence_ids"] = existing
        finding["evidence_backfill"] = {
            "filled_at": datetime.now(timezone.utc).isoformat(),
            "n_existing": len(existing) - len(added),
            "n_added": len(added),
            "sources": added_sources,
        }
    return finding, {
        "n_existing": len(existing) - len(added),
        "n_added": len(added),
        "filled": bool(added),
    }


def backfill_validation_file(
    data: dict,
    kb_index: dict[str, dict],
    papers: list[dict],
) -> tuple[dict, dict]:
    """单份 validation 产物回填：顶层 evidence_ids 为空时从 results 匹配。

    候选公式为分数掺杂式（如 Ge0.96Ti0.04Te），六通道中的
    kb_parent / retrieval_parent 会自动解析名义母体（GeTe）命中证据。
    返回 (data, stats)。
    """
    kb_index = _kb(kb_index)
    existing = list(data.get("evidence_ids") or [])
    stats = {"n_existing": len(existing), "n_added": 0, "filled": False}

    if existing:  # 已有证据（继承 Gap/finding）则保留
        return data, stats

    formulas: list[str] = []
    for r in data.get("results") or []:
        for key in ("candidate_formula", "host", "parent_formula"):
            val = str(r.get(key) or "").strip()
            if val and val not in formulas:
                formulas.append(val)

    added: list[str] = []
    added_sources: dict[str, str] = {}
    for formula in formulas:
        evs, src_map = match_evidence_for_formula(formula, kb_index, papers)
        if evs:
            new_ids, a, a_s = _merge_ids(existing, evs, src_map)
            added.extend(a)
            added_sources.update(a_s)
            existing = new_ids
            if added:
                break

    if added:
        data["evidence_ids"] = existing
        data["evidence_backfill"] = {
            "filled_at": datetime.now(timezone.utc).isoformat(),
            "n_existing": len(existing) - len(added),
            "n_added": len(added),
            "sources": added_sources,
        }
        stats.update({"n_added": len(added), "filled": True})
    return data, stats


def backfill_results_dir(
    target: str,
    kb_path: Path,
    results_dir: Path,
) -> tuple[dict, list[dict]]:
    """批量回填 results/{target}/*.json，返回 (stats, per_item)。

    results_dir 需同时包含 retrieval_*.json（证据来源）与 {target}/ 子目录。
    """
    kb_index = load_kb_index(kb_path)
    papers = load_retrieval_papers(results_dir)
    stats = {"n_items": 0, "n_filled": 0, "n_skipped": 0, "source_dist": {}}
    per_item: list[dict] = []

    for path in sorted(results_dir.glob(f"{target}/*.json")):
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        stats["n_items"] += 1
        if target == "validation":
            _, item_stats = backfill_validation_file(data, kb_index, papers)
        else:
            _, item_stats = backfill_finding(data, kb_index, papers)
        for src in (data.get("evidence_backfill") or {}).get("sources", {}).values():
            stats["source_dist"][src] = stats["source_dist"].get(src, 0) + 1
        if item_stats["filled"]:
            stats["n_filled"] += 1
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            stats["n_skipped"] += 1
        per_item.append(
            {
                "file": path.name,
                "n_existing": item_stats["n_existing"],
                "n_added": item_stats["n_added"],
                "filled": item_stats["filled"],
            }
        )
    return stats, per_item


def render_report(stats: dict, per_item: list[dict]) -> str:
    """回填报告文本（控制台 + 落盘共用）。"""
    lines = [
        f"产物总数：{stats['n_items']}",
        f"回填增强：{stats['n_filled']} 份（新增证据累计见明细）",
        f"跳过（已有证据或未命中）：{stats['n_skipped']} 份",
        f"证据来源分布：{stats['source_dist']}",
        "",
        "逐份明细（file | 已有 | +新增 | 回填）：",
    ]
    for item in per_item:
        mark = "✓" if item["filled"] else "—"
        lines.append(
            f"  {item['file']:<42} | {item['n_existing']:>2} | {item['n_added']:+d} | {mark}"
        )
    return "\n".join(lines)

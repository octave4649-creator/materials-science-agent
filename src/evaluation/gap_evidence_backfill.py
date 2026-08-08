"""Gap 证据链回填核心逻辑：从知识库与检索产物反向匹配证据 doc_id。

背景：审计（`src/audit/evidence_report.py`）暴露 data/gaps.json 的 29 条 Gap
仅 1 条可追溯（evidence_ids 为空）——Gap 识别时依赖知识库 kb_entry_ids 回映射，
但扩充（source=curated/llm）的 Gap 未携带证据。本模块从下游产物反查证据回填，
提升「每个结论可回溯」的审计覆盖（对齐 00-project-rules.md 4.1 证据链红线）。

六个匹配通道（按强度降序，可叠加）：
1. kb_exact（强）：Gap.formulas 归一化后 == 知识库 normalized_formula → 取该条目 evidence_ids
2. kb_parent（中）：知识库条目为分数掺杂公式（如 Ge0.93Ti0.01Bi0.06Te），
   其整数母体（parse_integer_parent → GeTe）== Gap.formulas 中的母体公式
   （含变量式名义母体，parse_variable_parent：Ge1-xBixTe → GeTe）→ 取该条目 evidence_ids
3. kb_similar（中弱）：去掉末尾下标数字后与知识库条目一致（如 Gap Bi0.5Sb1.5Te3 vs
   知识库 Bi0.5Sb1.5Te——同材料家族但下标表述不一致）→ 取该条目 evidence_ids
4. retrieval（弱）：检索产物 papers[].chunk 归一化后包含 Gap 公式子串 → 取该 paper doc_id
5. retrieval_title（弱）：chunk 未命中时，论文标题含 Gap 公式（标题点名该材料体系）
   → 取该 paper doc_id
6. retrieval_parent（最弱）：Gap 公式为分数/掺杂/变量式时解析其名义母体
   （parse_integer_parent：Bi0.5Sb1.5Te3 → Sb2Te3；parse_variable_parent：Ge1-xBixTe → GeTe），
   检索产物 chunk 含该母体子串 → 取该 paper doc_id

回填规则：
- 保留已有 evidence_ids（并集、去重、保序：已有在前，新增在后）
- 每条新增证据标注来源（source_map），写进 `evidence_backfill` 字段留痕
- 未匹配任何证据的 Gap 保持空，并在报告中如实列出（不编造）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.extraction.extractor import normalize_formula
from src.validation.parent_parser import parse_integer_parent, parse_variable_parent


def load_json(path: Path) -> object:
    """读取 JSON，文件缺失或损坏返回 None。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_kb_index(kb_path: Path) -> dict[str, dict]:
    """知识库 → {normalized_formula: entry} 索引（同公式取 evidence_ids 最全者）。"""
    kb = load_json(kb_path) or []
    index: dict[str, dict] = {}
    for entry in kb:
        formula = (entry.get("normalized_formula") or "").strip()
        if not formula:
            continue
        evs = entry.get("evidence_ids") or []
        if formula in index and len(index[formula].get("evidence_ids") or []) >= len(evs):
            continue
        index[formula] = entry
    return index


def load_retrieval_papers(retrieval_dir: Path) -> list[dict]:
    """扫描 results/retrieval_*.json 聚合全部论文（doc_id 去重，chunk 保留）。"""
    papers: dict[str, dict] = {}
    for path in sorted(retrieval_dir.glob("retrieval_*.json")):
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        for paper in data.get("papers", []):
            doc_id = paper.get("doc_id")
            if not doc_id:
                continue
            papers.setdefault(doc_id, paper)
    return list(papers.values())


def match_evidence_for_formula(
    formula: str,
    kb_index: dict[str, dict],
    papers: list[dict],
) -> tuple[list[str], dict[str, str]]:
    """单个 Gap 公式 → 匹配到的 (evidence_ids, source_map)。"""
    nf = normalize_formula(formula)
    if not nf:
        return [], {}
    found: list[str] = []
    sources: dict[str, str] = {}

    # 1. kb_exact：公式完全一致
    entry = kb_index.get(nf)
    if entry:
        for ev in entry.get("evidence_ids") or []:
            if ev not in sources:
                found.append(ev)
                sources[ev] = "kb_exact"

    # 2. kb_parent：KB 分数公式的整数母体 == 本公式（或变量式名义母体，如 Ge1-xBixTe → GeTe）
    nf_var_parent = parse_variable_parent(nf)
    for kb_formula, kb_entry in kb_index.items():
        parent = parse_integer_parent(kb_formula)
        if parent and (parent == nf or (nf_var_parent and parent == nf_var_parent)):
            for ev in kb_entry.get("evidence_ids") or []:
                if ev not in sources:
                    found.append(ev)
                    sources[ev] = "kb_parent"

    # 3. kb_similar：去掉末尾下标数字后与 KB 条目一致（同材料家族，下标表述差异）
    nf_stem = nf.rstrip("0123456789.")
    if nf_stem:
        for kb_formula, kb_entry in kb_index.items():
            if kb_formula == nf:
                continue
            if kb_formula.rstrip("0123456789.") != nf_stem:
                continue
            for ev in kb_entry.get("evidence_ids") or []:
                if ev not in sources:
                    found.append(ev)
                    sources[ev] = "kb_similar"

    # 4. retrieval：chunk 归一化后含本公式子串
    for paper in papers:
        chunk = normalize_formula(paper.get("chunk") or "")
        if nf in chunk:
            doc_id = paper.get("doc_id")
            if doc_id and doc_id not in sources:
                found.append(doc_id)
                sources[doc_id] = "retrieval"

    # 5. retrieval_title：chunk 未命中时，论文标题含本公式（标题点名该材料体系）
    if not found:
        for paper in papers:
            title = normalize_formula(paper.get("title") or "")
            if nf in title:
                doc_id = paper.get("doc_id")
                if doc_id and doc_id not in sources:
                    found.append(doc_id)
                    sources[doc_id] = "retrieval_title"

    # 6. retrieval_parent：本公式（分数/掺杂式/变量式）的名义母体出现在 chunk 中
    own_parent = parse_integer_parent(nf) or parse_variable_parent(nf)
    if own_parent and own_parent != nf:
        for paper in papers:
            chunk = normalize_formula(paper.get("chunk") or "")
            if own_parent in chunk:
                doc_id = paper.get("doc_id")
                if doc_id and doc_id not in sources:
                    found.append(doc_id)
                    sources[doc_id] = "retrieval_parent"
    return found, sources


def backfill_gaps(
    gaps: dict,
    kb_index: dict[str, dict],
    papers: list[dict],
) -> tuple[dict, dict, list[dict]]:
    """回填 gaps.json 的 evidence_ids，返回 (gaps, stats, per_gap)。"""
    stats = {
        "n_gaps": 0,
        "n_filled": 0,
        "n_unchanged": 0,
        "n_empty_after": 0,
        "n_new_evidence": 0,
        "source_dist": {},
    }
    per_gap: list[dict] = []
    filled_at = datetime.now(timezone.utc).isoformat()
    source_dist: dict[str, int] = {}

    for g in gaps.get("gaps", []):
        stats["n_gaps"] += 1
        existing = list(g.get("evidence_ids") or [])
        formulas = g.get("formulas") or []
        added: list[str] = []
        sources: dict[str, str] = {}

        for formula in formulas:
            evs, src_map = match_evidence_for_formula(formula, kb_index, papers)
            for ev in evs:
                if ev not in existing and ev not in added:
                    added.append(ev)
                    sources[ev] = src_map[ev]
                    source_dist[src_map[ev]] = source_dist.get(src_map[ev], 0) + 1

        new_ids = existing + added
        g["evidence_ids"] = new_ids
        g["evidence_backfill"] = {
            "filled_at": filled_at,
            "n_existing": len(existing),
            "n_added": len(added),
            "sources": sources,
        }

        if added:
            stats["n_filled"] += 1
            stats["n_new_evidence"] += len(added)
        elif existing:
            stats["n_unchanged"] += 1
        else:
            stats["n_empty_after"] += 1

        per_gap.append(
            {
                "idx": len(per_gap),
                "statement": (g.get("statement") or "")[:80],
                "formulas": formulas,
                "n_existing": len(existing),
                "n_added": len(added),
                "sources": sorted(set(sources.values())),
                "filled": bool(added),
            }
        )

    stats["source_dist"] = source_dist
    return gaps, stats, per_gap


def render_report(gaps: dict, stats: dict, per_gap: list[dict]) -> str:
    """回填报告文本（控制台 + 落盘共用）。"""
    lines = [
        f"Gap 总数：{stats['n_gaps']}",
        f"回填增强：{stats['n_filled']} 条（新增证据 {stats['n_new_evidence']} 条）",
        f"已有证据未变：{stats['n_unchanged']} 条",
        f"回填后仍无证据：{stats['n_empty_after']} 条",
        f"证据来源分布：{stats['source_dist']}",
        "",
        "逐条明细（idx | +新增 | 来源 | 语句）：",
    ]
    for item in per_gap:
        mark = "✓" if item["filled"] else "—"
        lines.append(
            f"  {item['idx']:>2} | {item['n_added']:+d} | "
            f"{','.join(item['sources']) or '空'} | {mark} {item['statement']}"
        )
    return "\n".join(lines)

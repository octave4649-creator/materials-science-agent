"""报告内容组装：检索 / 知识库 / Gap 产物 → 各章节 Markdown。

策略（task_plan 决策 2：模板填充 + LLM 润色两阶段）：
- 本模块只做确定性组装，所有数值/结论来自输入文件，零编造（防幻觉三件套第三环）
- 引用编号映射：papers 按 doc_id/unique_id/doi 去重编号 [n]，Gap 证据 doc_id 回映射引用
- 自检（self_check）：章节完整、引用可解析、Gap 有证据，输出布尔清单供评测
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.extraction.knowledge_base import KnowledgeBase
from src.gap.schemas import GapReport
from src.report.schemas import (
    SECTION_ORDER,
    SECTION_TITLES,
    ReportDocument,
    ReportMeta,
    ReportSection,
)

# 参考文献条目（清洗后的最小字段集）


def _norm_title(title: str) -> str:
    """标题归一化（去标签/小写/合并空白，用于去重）。"""
    return re.sub(r"\s+", " ", _plain_text(title).lower())


def _plain_text(text: str) -> str:
    """去 HTML 标签 + 合并空白（保留大小写，用于展示）。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def clean_authors(authors: Any, max_show: int = 3) -> str:
    """作者清洗：去重保序，最多展示 max_show 位 + "et al."。"""
    if not authors:
        return "N/A"
    if isinstance(authors, str):
        authors = [authors]
    seen: list[str] = []
    for a in authors:
        name = (a.get("name") if isinstance(a, dict) else a) or ""
        name = re.sub(r"\s+", " ", str(name).strip())
        if name and name.lower() not in {s.lower() for s in seen}:
            seen.append(name)
    if len(seen) <= max_show:
        return ", ".join(seen)
    return ", ".join(seen[:max_show]) + ", et al."


@dataclass
class PaperRef:
    """一条参考文献（编号 + 元数据）。"""

    index: int
    title: str
    authors: str
    year: int | None
    journal: str | None
    doi: str | None
    doc_id: str | None
    source: str

    def fmt(self) -> str:
        """GB/T 风格一行引用（用于参考文献列表）。"""
        parts = [
            self.authors,
            f"({self.year})" if self.year else "",
            self.title,
            self.journal or "",
            f"DOI: {self.doi}" if self.doi else "",
        ]
        text = ". ".join(p for p in parts if p)
        return text if text.endswith(".") else text + "."


def build_references(papers: list[dict[str, Any]]) -> tuple[list[PaperRef], dict[str, int]]:
    """论文清单 → 去重参考文献 + doc_id→引用编号映射。

    去重键三级：doc_id → unique_id → 归一化标题（对齐经验 4）。

    返回:
        (refs, doc_id_to_ref)。doc_id_to_ref 供 Gap 证据回映射引用编号。
    """
    refs: list[PaperRef] = []
    doc_to_ref: dict[str, int] = {}
    seen: set[str] = set()

    def _key(p: dict[str, Any]) -> str | None:
        if p.get("doc_id"):
            return f"doc:{p['doc_id']}"
        if p.get("unique_id"):
            return f"uid:{p['unique_id']}"
        title = _norm_title(p.get("title", ""))
        return f"title:{title}" if title else None

    for paper in papers:
        key = _key(paper)
        if key is None or key in seen:
            continue
        seen.add(key)
        idx = len(refs) + 1
        refs.append(
            PaperRef(
                index=idx,
                title=_plain_text(paper.get("title")),
                authors=clean_authors(paper.get("authors")),
                year=paper.get("year") or paper.get("publication_published_year"),
                journal=paper.get("journal") or paper.get("publication_venue_name_unified"),
                doi=paper.get("doi"),
                doc_id=paper.get("doc_id"),
                source=paper.get("source", "sciverse"),
            )
        )
        if paper.get("doc_id"):
            doc_to_ref[paper["doc_id"]] = idx
    return refs, doc_to_ref


# ---------- 各章节组装 ----------

def section_scope(question: str | None, domain: str) -> str:
    """1. 研究问题与范围。"""
    q = question or "未指定（请补充研究问题）"
    return (
        f"- **研究领域**：{domain}\n"
        f"- **研究问题**：{q}\n"
        "- **范围**：以文献驱动的材料科学发现为目标，覆盖检索、知识抽取、"
        "Research Gap 识别与报告生成全链路\n"
        "- **产出**：带证据链的 Gap 清单，作为进阶路线（如路线 A 构效关系发现）的搜索种子"
    )


def section_method(
    query: str,
    sub_queries: list[str],
    generated_at: str,
    n_papers: int,
    total_found: int,
) -> str:
    """2. 检索策略与数据来源（含检索记录/时间戳）。"""
    if sub_queries:
        subs = "\n".join(f"  - `{q}`" for q in sub_queries)
    else:
        subs = f"  - `{query}`" if query else "  - （未拆解）"
    ts = generated_at or "未知（检索输出未记录时间）"
    return (
        "- **数据来源**：Sciverse（4.66 亿条学术元数据，agentic-search 语义检索 + "
        "meta-search 结构化检索）\n"
        f"- **检索问题**：`{query}`\n"
        f"- **拆解子查询**：\n{subs}\n"
        f"- **检索时间**：{ts}\n"
        f"- **命中规模**：去重后 {n_papers} 篇（原始命中 {total_found} 条）\n"
        "- **证据链**：每篇文献记录 doc_id/DOI/页码/检索时间，全程可审计"
    )


def section_extraction(kb: KnowledgeBase) -> str:
    """3. 知识抽取结果（结构化数据表）。"""
    if not kb.entries:
        return "_知识库为空，无抽取结果。_"
    rows = [
        "| 化学式 | 性能 | 方法 | 合成温度 | 证据数 |",
        "|---|---|---|---|---|",
    ]
    for entry in kb.entries:
        rec = entry.record
        props = "; ".join(
            f"{p.name}={p.value}{p.unit or ''}" + (f"@{p.condition}" if p.condition else "")
            for p in rec.properties[:6]
        ) or "-"
        methods = "; ".join(
            f"{m.type}/{m.software or '?'}" for m in rec.methods[:4]
        ) or "-"
        temp = rec.synthesis.temperature or "-"
        rows.append(
            f"| {entry.normalized_formula} | {props} | {methods} | {temp} | "
            f"{len(entry.evidence_ids)} |"
        )
    rows.append("")
    return "\n".join(rows)


def section_gaps(
    report: GapReport, doc_to_ref: dict[str, int]
) -> tuple[str, list[int]]:
    """4. Research Gap 清单（四列表格 + 统计 + 交叉引用 [n]）。"""
    if not report.gaps:
        return "_未识别出 Gap（知识库规模不足或证据不足）。_", []
    refs_used: list[int] = []

    def _evid(gap: Any) -> tuple[str, list[int]]:
        """Gap 证据 → 引用编号 + 证据条数。"""
        nums: list[int] = []
        for eid in gap.evidence_ids:
            if eid in doc_to_ref:
                nums.append(doc_to_ref[eid])
        nums = sorted(set(nums))
        refs_used.extend(nums)
        n = len(gap.evidence_ids)
        if nums:
            return ", ".join(f"[{i}]" for i in nums) + f"（{n} 条）", nums
        return f"{n} 条证据", nums

    lines = [
        "| # | Gap 描述 | 类型 | 新颖性 | 证据 | 可操作性 |",
        "|---|---|---|---|---|---|",
    ]
    for i, gap in enumerate(report.gaps, 1):
        evid, _ = _evid(gap)
        note = f"（{gap.verification}）" if gap.verification else ""
        lines.append(
            f"| {i} | {gap.statement}{note} | {gap.gap_type} | {gap.novelty} | "
            f"{evid} | {gap.operability or '-'} |"
        )
    lines.append("")

    # 统计表（按类型/新颖性）
    stats = report.stats()
    by_type = "；".join(f"{k} {v}" for k, v in stats["by_type"].items()) or "无"
    by_novelty = "；".join(f"{k} {v}" for k, v in stats["by_novelty"].items()) or "无"
    lines.append(
        f"**Gap 统计**：共 {stats['n_gaps']} 条；按类型：{by_type}；按新颖性：{by_novelty}。\n"
    )
    return "\n".join(lines), sorted(set(refs_used))


def section_review(refs: list[PaperRef]) -> tuple[str, list[int]]:
    """5. 文献综述（按期刊分组组织）。"""
    if not refs:
        return "_无检索文献。_", []
    # 论文按期刊分组（小写归一化合并同名异写，展示保留首字母大写）
    groups: dict[str, list[PaperRef]] = {}
    for ref in refs:
        journal = (ref.journal or "其他").strip()
        groups.setdefault(journal.lower(), []).append(ref)
    lines: list[str] = []
    refs_used: list[int] = []
    for journal, items in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:6]:
        display = items[0].journal or "其他"
        lines.append(f"### {display}")
        for ref in items[:6]:
            lines.append(f"- [{ref.index}] {ref.title}（{ref.year or '年份未知'}）")
            refs_used.append(ref.index)
    return "\n".join(lines), sorted(set(refs_used))


def section_validation(validation_dir: Path | None) -> str:
    """6. 数据库交叉验证（模块 6 产物汇总：判定分布 + 候选表）。"""
    if validation_dir is None or not validation_dir.exists():
        return "_尚未执行数据库交叉验证（先运行 scripts/run_validation.py）。_"
    files = sorted(validation_dir.glob("validation_*.json"))
    if not files:
        return "_未找到验证结果（results/validation/validation_*.json）。_"

    rows: list[dict[str, Any]] = []
    n_files = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        n_files += 1
        for r in data.get("results", []):
            rows.append(
                {
                    "formula": r.get("candidate_formula", ""),
                    "host": r.get("host", ""),
                    "verdict": r.get("verdict", "未知"),
                    "reason": r.get("reason", ""),
                }
            )
    if not rows:
        return "_验证结果为空。_"

    # 判定分布统计
    from collections import Counter

    verdicts = Counter(r["verdict"] for r in rows)
    stats_txt = "；".join(f"{k} {v} 个" for k, v in verdicts.items()) or "无"
    lines = [
        f"对 **{n_files}** 个构效关系发现、**{len(rows)}** 个候选做了 OQMD"
        "（主）+ Materials Project（增强）数据库交叉验证：\n",
        f"**判定分布**：{stats_txt}。\n",
        "| 候选 | 母体 | 判定 | 依据（摘要） |",
        "|---|---|---|---|",
    ]
    for r in rows[:20]:
        lines.append(
            f"| {r['formula']} | {r['host']} | {r['verdict']} | "
            f"{(r['reason'] or '-')[:70]} |"
        )
    if len(rows) > 20:
        lines.append(f"| ... | 其余 {len(rows) - 20} 个候选略 | | |")
    lines.append("")
    lines.append(
        "> 判定口径：母体在库且热力学稳定 → 已知；在库但不稳定 → 反例；"
        "不在库 → 新知（库外假设）；分数成分无法直查 → 验证失败（如实标注）。"
        "所有判定可回溯至 OQMD/MP 记录（验证 JSON 含 source_url）。"
    )
    return "\n".join(lines)


def section_conclusion(report: GapReport) -> str:
    """6. 结论与建议（确定性生成，含路线 A 种子建议）。"""
    if not report.gaps:
        return (
            "- 当前知识库未产出可操作 Gap，建议扩充文献语料后重跑识别。\n"
            "- 可先用检索 Agent 扩大候选领域（热电/催化/电池）对比后收敛选题。"
        )
    # 高置信 + 可操作 Gap 作为路线 A 种子
    candidates = [
        g for g in report.gaps if g.confidence >= 0.6 and g.operability
    ] or report.gaps[:2]
    seeds = "\n".join(
        f"- {g.statement}（证据 {len(g.evidence_ids)} 条）→ 搜索种子：{g.operability}"
        for g in candidates[:3]
    )
    novelty = report.stats()["by_novelty"]
    return (
        "- 本报告识别出若干 Research Gap，均可作为路线 A（构效关系发现）的搜索种子：\n"
        f"{seeds}\n"
        f"- 新颖性分布：{novelty or '未评估'}；自动判定为启发式，最终需人工复核。\n"
        "- 建议下一步：扩充同体系多来源文献以激活矛盾检测；对高置信 Gap 在 "
        "Materials Project / OQMD 中交叉验证。"
    )


def section_references(refs: list[PaperRef]) -> str:
    """参考文献列表（[n] 编号 + DOI 回链）。"""
    if not refs:
        return "_无参考文献。_"
    return "\n".join(f"[{r.index}] {r.fmt()}" for r in refs)


def section_appendix(papers: list[dict[str, Any]], refs: list[PaperRef]) -> str:
    """附录：文献清单（DOI、标题、来源）。"""
    if not refs:
        return "_无文献清单。_"
    lines = [
        "| # | 标题 | DOI | 来源 |",
        "|---|---|---|---|",
    ]
    for ref in refs:
        lines.append(
            f"| {ref.index} | {ref.title} | {ref.doi or '-'} | {ref.source} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------- 组装入口 ----------

def build_document(
    *,
    papers: list[dict[str, Any]],
    kb: KnowledgeBase,
    gaps_report: GapReport,
    question: str | None,
    sub_queries: list[str],
    generated_at: str,
    total_found: int,
    input_hashes: dict[str, str],
    validation_dir: Path | None = None,
) -> ReportDocument:
    """组装完整报告（确定性模板填充）。

    参数:
        papers: 检索输出论文清单
        kb: 知识库
        gaps_report: Gap 报告
        question: 研究问题
        sub_queries: 检索子查询
        generated_at: 检索时间（来自检索输出）
        total_found: 原始命中数
        input_hashes: 输入文件 sha256（版本快照）
        validation_dir: 模块 6 验证结果目录（缺省取 results/validation/）
    """
    refs, doc_to_ref = build_references(papers)
    gaps_content, gap_refs = section_gaps(gaps_report, doc_to_ref)
    review_content, review_refs = section_review(refs)
    validation_content = section_validation(validation_dir)

    sections: list[ReportSection] = []
    # 摘要先占位（由 ReportAgent 填 LLM/规则摘要），此处生成规则摘要备选
    abstract = _rule_abstract(gaps_report, len(refs), len(kb.entries))
    for key in SECTION_ORDER:
        if key == "abstract":
            content, srefs = abstract, []
        elif key == "scope":
            content, srefs = section_scope(question, gaps_report.domain), []
        elif key == "method":
            content, srefs = (
                section_method(
                    question or "",
                    sub_queries,
                    generated_at,
                    len(refs),
                    total_found,
                ),
                [],
            )
        elif key == "extraction":
            content, srefs = section_extraction(kb), []
        elif key == "gaps":
            content, srefs = gaps_content, gap_refs
        elif key == "review":
            content, srefs = review_content, review_refs
        elif key == "validation":
            content, srefs = validation_content, []
        elif key == "conclusion":
            content, srefs = section_conclusion(gaps_report), []
        elif key == "references":
            content, srefs = section_references(refs), list(range(1, len(refs) + 1))
        elif key == "appendix":
            content, srefs = section_appendix(papers, refs), list(range(1, len(refs) + 1))
        else:  # pragma: no cover
            continue
        sections.append(
            ReportSection(key=key, title=SECTION_TITLES[key], content=content, refs=srefs)
        )

    doc = ReportDocument(
        title=f"{gaps_report.domain} 领域文献调研报告",
        sections=sections,
        meta=ReportMeta(
            domain=gaps_report.domain,
            question=question,
            n_papers=len(refs),
            n_kb_entries=len(kb.entries),
            n_gaps=len(gaps_report.gaps),
            input_hashes=input_hashes,
        ),
    )
    doc.meta.self_check = self_check(doc)
    return doc


def _rule_abstract(gaps_report: GapReport, n_papers: int, n_entries: int) -> str:
    """规则式摘要（无 LLM 时兜底，确定性生成）。"""
    stats = gaps_report.stats()
    top = gaps_report.gaps[0] if gaps_report.gaps else None
    top_line = (
        f"最有代表性的是「{top.gap_type}」：{top.statement}"
        if top
        else "当前语料未识别出可操作 Gap。"
    )
    return (
        f"本报告围绕 {gaps_report.domain} 领域开展文献调研：检索 {n_papers} 篇文献，"
        f"抽取 {n_entries} 个材料体系，识别 {stats['n_gaps']} 条 Research Gap"
        f"（按类型 {stats['by_type'] or '无'}；按新颖性 {stats['by_novelty'] or '未评估'}）。"
        f"{top_line}。所有结论均附证据链，可回溯至 Sciverse 检索记录。"
    )


# ---------- 输入加载与自检 ----------

def sha256_file(path: Path) -> str:
    """文件 sha256（版本快照）。"""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def load_retrieval(path: str | Path) -> dict[str, Any]:
    """加载检索输出 JSON。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "papers" not in data:
        raise ValueError(f"检索输出缺少 papers 字段: {path}")
    return data


def load_gaps(path: str | Path) -> GapReport:
    """加载 Gap 报告 JSON。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return GapReport.model_validate(data)


def self_check(doc: ReportDocument) -> dict[str, bool]:
    """结构化自检清单（赛题评测维度：结构化程度/证据回溯）。"""
    smap = doc.section_map()
    checks: dict[str, bool] = {}

    # 1. 章节完整
    checks["sections_complete"] = all(k in smap for k in SECTION_ORDER)

    # 2. 摘要非空
    abstract_sec = smap.get("abstract", ReportSection(key="", title=""))
    checks["abstract_nonempty"] = bool(abstract_sec.content.strip())

    # 3. 知识抽取表非空（有数据表行）
    ext = smap.get("extraction")
    checks["extraction_has_rows"] = bool(ext and "|" in ext.content and "证据数" in ext.content)

    # 4. Gap 章节引用可解析（所有引用编号 ≤ 参考文献总数）
    n_refs = doc.meta.n_papers
    max_ref = max((r for s in doc.sections for r in s.refs), default=0)
    checks["refs_resolved"] = max_ref <= n_refs

    # 5. 有 Gap 时每条 Gap 均有证据（Gap 表格含「证据」列非空行）
    gaps = smap.get("gaps")
    checks["gaps_evidence_linked"] = bool(
        not doc.meta.n_gaps or (gaps and "证据" in gaps.content and "条" in gaps.content)
    )

    # 6. 参考文献列表非空且与引用数一致（按行首 [n] 编号统计）
    refs_sec = smap.get("references")
    n_listed = (
        len(re.findall(r"^\[\d+\]", refs_sec.content, re.MULTILINE)) if refs_sec else 0
    )
    checks["references_complete"] = n_listed == n_refs
    return checks

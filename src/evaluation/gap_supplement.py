"""无证据 Gap 补检查询生成：缺失母体清单 + Sciverse 检索查询。

背景（对齐九次深度开发「Gap evidence_ids 回填」）：backfill 后 29 条 Gap 仍
11 条无证据（SnTe/Mg3Sb2/ZrNiSn/Cu2Se/CoSb3/SiGe/Bi0.5Sb1.5Te3 等非知识库母体
——知识库仅含 GeTe/PbTe/Bi2Te3/Sr5In2Sb6/Bi0.5Sb1.5Te3 五条热电条目，三通道
回填无源可匹配）。本模块为这些 Gap 生成「缺失母体清单 + 补检查询」，供夜间
联网批量跑 Sciverse 检索补齐证据后重跑回填。

设计：
- `find_evidence_missing_gaps()`：gaps.json 中 evidence_ids 为空的 Gap
- `extract_missing_hosts()`：去重提取缺失母体公式（清单）
- `build_query_for_gap()`：母体 + 热电主题词 → 英文检索查询（Sciverse 语义检索友好）
- `KEYWORD_MAP`：中文主题词 → 英文关键词（热电领域常用检索词）

用法：
    python scripts/gen_gap_supplement_queries.py
输出：results/eval/gap_supplement_queries_<ts>.json（缺失母体清单 + 逐条查询 + 批量命令）
"""
from __future__ import annotations

import json
from pathlib import Path

from src.extraction.extractor import normalize_formula


def find_evidence_missing_gaps(gaps: dict) -> list[dict]:
    """返回 evidence_ids 为空的 Gap 列表（保序）。"""
    out = []
    for gap in gaps.get("gaps", []):
        if not gap.get("evidence_ids"):
            out.append(gap)
    return out


def extract_missing_hosts(missing_gaps: list[dict]) -> list[str]:
    """从无证据 Gap 提取去重的缺失母体公式（保序，公式归一化）。"""
    hosts: list[str] = []
    seen: set[str] = set()
    for gap in missing_gaps:
        for formula in gap.get("formulas") or []:
            nf = normalize_formula(formula) or formula.strip()
            key = nf.lower()
            if key not in seen:
                seen.add(key)
                hosts.append(nf)
    return hosts


# 热电领域中文主题词 → 英文检索关键词（覆盖 11 条 Gap 的主题）
KEYWORD_MAP: dict[str, str] = {
    "共掺杂": "codoping",
    "掺杂": "doping",
    "能带收敛": "band convergence",
    "晶格热导率": "lattice thermal conductivity",
    "载流子迁移率": "carrier mobility",
    "阳离子空位": "cation vacancy",
    "空位": "vacancy",
    "第一性原理": "first-principles",
    "相变温度": "phase transition temperature",
    "功率因子": "power factor",
    "热电优值": "figure of merit",
    "反位缺陷": "antisite defect",
    "热稳定性": "thermal stability",
    "主动学习": "active learning",
    "机器学习势函数": "machine learning potential",
    "声子输运": "phonon transport",
    "断裂韧性": "fracture toughness",
    "力学性能": "mechanical properties",
    "填充方钴矿": "skutterudite",
    "高分辨率": "high-resolution TEM",
    "界面散射": "interface scattering",
    "异质结": "heterostructure",
    "能带对齐": "band alignment",
    "协同机制": "synergistic mechanism",
    "定量": "quantitative",
    "系统": "systematic",
    "高熵": "high-entropy",
    "符号回归": "symbolic regression",
    "组分设计": "composition design",
    "组分-性能": "composition-property",
}


def _pick_keywords(statement: str, max_kw: int = 2) -> list[str]:
    """从 Gap 陈述提取英文关键词（KEYWORD_MAP 命中的中文词，去重保序）。

    互斥消歧：子词命中时只保留最具体词（如「共掺杂」命中则跳过「掺杂」）。
    """
    kws: list[str] = []
    for zh, en in KEYWORD_MAP.items():
        if zh not in statement:
            continue
        if en in kws:
            continue
        # 若已有该词作为子串（如 codoping 已含 doping），跳过冗余
        if any(kw != en and (en in kw or kw in en) for kw in kws):
            continue
        kws.append(en)
        if len(kws) >= max_kw:
            break
    return kws


def build_query_for_gap(gap: dict) -> str:
    """单条 Gap → 英文检索查询（母体 + 主题关键词 + 热电限定）。

    查询 = 母体化学式 + 主题词（至多 2 个）+ thermoelectric，控制长度
    （对齐 Sciverse 语义检索习惯；review_gap_novelty 的 _novelty_query 控 200 字符）。
    """
    formulas = gap.get("formulas") or []
    if formulas:
        host = normalize_formula(formulas[0]) or formulas[0].strip()
    else:
        host = ""
    kws = _pick_keywords(gap.get("statement") or "")
    parts = [host] + kws + ["thermoelectric"]
    return " ".join(parts).strip()


def generate_supplement_plan(gaps: dict) -> dict:
    """生成补检计划：缺失母体清单 + 逐条查询 + 批量命令。"""
    missing_gaps = find_evidence_missing_gaps(gaps)
    hosts = extract_missing_hosts(missing_gaps)
    # 逐条 Gap 查询（母体可能对应多条 Gap）
    query_items: list[dict] = []
    for gap in missing_gaps:
        formula = (gap.get("formulas") or [""])[0]
        host = normalize_formula(formula) or formula.strip()
        query_items.append(
            {
                "host": host,
                "gap_type": gap.get("gap_type"),
                "statement": gap.get("statement"),
                "query": build_query_for_gap(gap),
                "gap_idx": gap.get("idx"),
            }
        )
    commands = [
        'python scripts/run_retrieval.py "%s" --top-k 5 --mode fast' % item["query"]
        for item in query_items
    ]
    return {
        "n_missing_gaps": len(missing_gaps),
        "missing_hosts": hosts,
        "queries": query_items,
        "batch_commands": commands,
        "next_steps": [
            "1) 夜间联网逐条执行 batch_commands（或脚本内 --run 批量）",
            "2) 重跑 python scripts/backfill_gap_evidence.py（retrieval 通道命中即回填）",
            "3) 审计复验 python scripts/run_audit_report.py 验证 Gap 可追溯率提升",
        ],
    }


def save_plan(plan: dict, out_path: Path) -> None:
    """落盘补检计划 JSON。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

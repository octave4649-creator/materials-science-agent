"""字段级 F1 计算器：LLM 抽取 vs 规则抽取 vs 人工 gold 的字段对齐评测。

对齐 `.trae/rules/00-project-rules.md` 7.2 评测规范与
`DEVELOPMENT-GUIDE.md` 6.1「抽取质量：字段级 F1、准确率（对照人工标注的抽取结果）」。

六类字段的匹配语义：
- formula：化学式归一化后完全相等（binary）
- composition：组成描述归一化 token 互含
- structure：space_group/lattice/phase 三个原子子字段独立匹配
- properties：性能列表 (name, value) 归一化匹配，贪心去重配对
- methods：方法列表 (type, software) 归一化匹配，贪心去重配对
- synthesis：precursors/temperature/atmosphere/duration 独立匹配

字段对齐语义（LLM 五段式 vs 规则四字段维度不对等）：
- gold 与 pred 同为空的原子字段不计入分母（视为目标 schema 不支持该字段，
  如规则式不产出 structure/methods），避免空字段膨胀分数
- gold 非空 pred 空 → fn（漏检）；gold 空 pred 非空 → fp（幻觉/过度抽取）
"""
from __future__ import annotations

import re
from typing import Any

from src.extraction.extractor import normalize_formula

# 数值匹配容差：相对 5% 或绝对 0.05，取大者
_NUM_REL_TOL = 0.05
_NUM_ABS_TOL = 0.05

# 原子字段拆解键：字段大类 → 原子子字段键
_ATOMIC_KEYS: dict[str, tuple[str, ...]] = {
    "composition": ("composition",),
    "structure": ("space_group", "lattice", "phase"),
    "synthesis": ("precursors", "temperature", "atmosphere", "duration"),
}


def _norm(text: Any) -> str:
    """归一化：小写 + 去非字母数字字符 + 压缩空白（用于互含判断）。"""
    if text is None:
        return ""
    s = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff.]+", "", str(text)).lower()
    return s


def _num(value: Any) -> float | None:
    """尝试解析数值；解析失败返回 None。"""
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _num_match(a: Any, b: Any) -> bool:
    """数值容差匹配（相对 5% + 绝对 0.05 兜底）。"""
    na, nb = _num(a), _num(b)
    if na is None or nb is None:
        return False
    return abs(na - nb) <= max(_NUM_ABS_TOL, _NUM_REL_TOL * max(abs(na), abs(nb)))


def _text_match(a: Any, b: Any) -> bool:
    """文本互含匹配（任一方向包含即命中，抗字段描述差异）。"""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return na in nb or nb in na


def _prop_match(gold: dict[str, Any], pred: dict[str, Any]) -> bool:
    """性能条目匹配：name 互含 + value 数值容差。"""
    name_ok = _text_match(gold.get("name"), pred.get("name"))
    if not name_ok:
        return False
    if gold.get("value") is None and pred.get("value") is None:
        return True  # 双方都无数值，仅按名称匹配
    return _num_match(gold.get("value"), pred.get("value"))


def _method_match(gold: dict[str, Any], pred: dict[str, Any]) -> bool:
    """方法条目匹配：type 互含或 software 互含。"""
    if _text_match(gold.get("type"), pred.get("type")):
        return True
    return _text_match(gold.get("software"), pred.get("software"))


def _field_atoms(record: dict[str, Any], field: str) -> list[tuple[str, Any, dict[str, Any]]]:
    """把记录字段拆成原子项列表 [(key, display, meta)]，仅保留非空项。

    空-空字段（gold 与 pred 都无）不计入分母——字段对齐语义。
    """
    atoms: list[tuple[str, Any, dict[str, Any]]] = []
    if field == "formula":
        formula = (record.get("material") or {}).get("formula")
        if formula:
            atoms.append(("formula", formula, {"raw": formula}))
    elif field == "properties":
        for p in record.get("properties") or []:
            if isinstance(p, dict) and p.get("name"):
                atoms.append((f"prop:{_norm(p['name'])}", p.get("value"), p))
    elif field == "methods":
        for m in record.get("methods") or []:
            if isinstance(m, dict) and (m.get("type") or m.get("software")):
                atoms.append((f"method:{_norm(m.get('type'))}", m.get("software"), m))
    elif field in _ATOMIC_KEYS:
        if field in ("composition", "structure"):
            node = (record.get("material") or {}).get(field)
        else:
            node = record.get(field)
        if isinstance(node, dict):
            for key in _ATOMIC_KEYS[field]:
                if node.get(key):
                    atoms.append((f"{field}:{key}", node.get(key), {"key": key}))
        elif node:
            atoms.append((f"{field}:value", node, {"key": "value"}))
    return atoms


def _match(
    gold_item: tuple[str, Any, dict[str, Any]],
    pred_item: tuple[str, Any, dict[str, Any]],
    field: str,
) -> bool:
    """单原子项匹配：按字段大类分发到对应匹配器。"""
    _, gv, gmeta = gold_item
    _, pv, pmeta = pred_item
    if field == "formula":
        # 化学式归一化后完全相等（binary 匹配）
        return bool(
            gv and pv and normalize_formula(str(gv)) == normalize_formula(str(pv))
        )
    if field == "properties":
        return _prop_match(gmeta, pmeta)
    if field == "methods":
        return _method_match(gmeta, pmeta)
    # composition / structure / synthesis：文本互含
    return _text_match(gv, pv)


def field_confusion(
    gold: dict[str, Any], pred: dict[str, Any], field: str
) -> tuple[int, int, int]:
    """单字段混淆计数：贪心配对 gold 原子项 → pred 原子项。

    返回 (tp, fp, fn)：
    - tp：gold 项被 pred 正确命中
    - fn：gold 非空项未被 pred 命中（漏检）
    - fp：pred 非空项未匹配任何 gold 项（幻觉/过度抽取）

    空-空字段项（gold 空且 pred 空）不产生任何计数。
    """
    gold_atoms = _field_atoms(gold, field)
    pred_atoms = _field_atoms(pred, field)
    if not gold_atoms and not pred_atoms:
        return 0, 0, 0
    used: set[int] = set()
    tp = 0
    for g in gold_atoms:
        for i, p in enumerate(pred_atoms):
            if i in used:
                continue
            if _match(g, p, field):
                used.add(i)
                tp += 1
                break
    fn = len(gold_atoms) - tp
    fp = len(pred_atoms) - tp
    return tp, fp, fn


def confusion_to_metrics(tp: int, fp: int, fn: int) -> dict[str, float]:
    """混淆计数 → {precision, recall, f1}（防除零）。

    precision 语义：无预测（tp=fp=0）且存在漏检（fn>0）时视为 1.0——
    「没有预测就没有假阳性」，避免惩罚能力缺失而非幻觉。
    全零（空-空字段）→ 全 0。
    """
    if tp == 0 and fp == 0 and fn > 0:
        precision = 1.0
    else:
        precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


_FIELDS = ("formula", "composition", "structure", "properties", "methods", "synthesis")


def extraction_f1(
    gold_records: list[dict[str, Any]], pred_records: list[dict[str, Any]]
) -> dict[str, Any]:
    """批量字段级 F1：逐样本逐字段累加混淆 → 微平均 + 宏平均。

    参数:
        gold_records: 人工标注/参考 gold（model_dump 后的 dict 列表）
        pred_records: 待评抽取路径输出（与 gold_records 同序对齐）

    返回:
        {
          "per_field": {字段: {tp,fp,fn,precision,recall,f1}},
          "micro": {precision, recall, f1},
          "macro": {precision, recall, f1},
        }
    """
    if len(gold_records) != len(pred_records):
        raise ValueError(f"gold({len(gold_records)}) 与 pred({len(pred_records)}) 样本数不一致")
    totals: dict[str, list[int]] = {f: [0, 0, 0] for f in _FIELDS}
    per_sample: list[dict[str, Any]] = []
    for gi, gold in enumerate(gold_records):
        sample: dict[str, Any] = {"idx": gi}
        for field in _FIELDS:
            tp, fp, fn = field_confusion(gold, pred_records[gi], field)
            totals[field][0] += tp
            totals[field][1] += fp
            totals[field][2] += fn
            sample[field] = {"tp": tp, "fp": fp, "fn": fn}
        per_sample.append(sample)
    per_field: dict[str, dict[str, float]] = {}
    micro_tp = micro_fp = micro_fn = 0
    for field in _FIELDS:
        tp, fp, fn = totals[field]
        micro_tp += tp
        micro_fp += fp
        micro_fn += fn
        per_field[field] = confusion_to_metrics(tp, fp, fn)
    nonempty = [f for f in _FIELDS if _nonempty(per_field[f])]
    n = max(len(nonempty), 1)
    macro = {
        "precision": round(
            sum(per_field[f]["precision"] for f in nonempty) / n, 4
        ),
        "recall": round(
            sum(per_field[f]["recall"] for f in nonempty) / n, 4
        ),
        "f1": round(
            sum(per_field[f]["f1"] for f in nonempty) / n, 4
        ),
    }
    return {
        "per_field": per_field,
        "micro": confusion_to_metrics(micro_tp, micro_fp, micro_fn),
        "macro": macro,
        "per_sample": per_sample,
    }


def _nonempty(m: dict[str, float]) -> bool:
    """字段是否有任何混淆计数（空-空字段排除出 macro 平均）。"""
    return m["tp"] > 0 or m["fp"] > 0 or m["fn"] > 0

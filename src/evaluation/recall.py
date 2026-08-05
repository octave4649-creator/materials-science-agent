"""已知关系召回率计算：搜索算法 top-k 候选是否命中期望掺杂方案。

对齐 `.trae/rules/05-route-a-SPR.md` 第 4 节（搜索算法能力评测）与
`DEVELOPMENT-GUIDE.md` 6.2「发现质量：数据库验证通过率、新知比例」。

匹配语义（宽松命中，容忍公式命名差异）：
- host：化学式归一化后相等（`normalize_formula` 处理 LaTeX/HTML 变体）
- dopant：元素符号大小写不敏感相等
- concentration：与期望浓度绝对偏差 ≤ 容差（默认 1.5%，覆盖 GA 交叉均值/
  变异网格取整带来的偏差）

known_facts 标注 schema（写入 gaps.json 顶层）：
{
  "id": "kf-01",
  "relation": "关系陈述（可证伪）",
  "host": "母体化学式",
  "dopant": "掺杂元素",
  "concentration": 期望掺杂摩尔百分数,
  "formulas": ["母体"],
  "reference": "文献/证据来源",
  "note": "评测说明"
}
"""
from __future__ import annotations

from typing import Any

from src.extraction.extractor import normalize_formula

DEFAULT_CONC_TOL = 1.5  # 浓度容差（绝对百分点）


def candidate_matches(
    candidate: Any, expected: dict[str, Any], conc_tol: float = DEFAULT_CONC_TOL
) -> bool:
    """单个候选是否命中期望掺杂方案（host + dopant + 浓度容差）。

    参数:
        candidate: 搜索产物候选（含 host/dopant/concentration 字段，
            如 src.search.schemas.Candidate）
        expected: known_fact 标注（host/dopant/concentration）
        conc_tol: 浓度容差（绝对百分点）

    返回:
        True 表示命中（该候选等价于期望掺杂方案）。
    """
    exp_host = normalize_formula(str(expected.get("host") or ""))
    exp_dopant = str(expected.get("dopant") or "").upper()
    exp_conc = _as_float(expected.get("concentration"))
    if not exp_host or not exp_dopant or exp_conc is None:
        return False
    cand_host = normalize_formula(str(_get(candidate, "host") or ""))
    cand_dopant = str(_get(candidate, "dopant") or "").upper()
    cand_conc = _as_float(_get(candidate, "concentration"))
    if cand_host != exp_host or cand_dopant != exp_dopant:
        return False
    return cand_conc is not None and abs(cand_conc - exp_conc) <= conc_tol


def hit_at_k(candidates: list[Any], expected: dict[str, Any], k: int) -> bool:
    """前 k 名候选内是否命中期望掺杂方案。"""
    if k <= 0:
        return False
    return any(candidate_matches(c, expected) for c in candidates[:k])


def hit_at_ks(
    candidates: list[Any], expected: dict[str, Any], ks: tuple[int, ...] = (1, 3, 5)
) -> dict[str, bool]:
    """一次评估多个 @k（避免重复遍历）。"""
    result: dict[str, bool] = {}
    for k in sorted(ks):
        result[f"hit@{k}"] = hit_at_k(candidates, expected, k)
    return result


def aggregate_recall(hits: list[bool]) -> float:
    """跨已知关系的命中率（@k 用同一 k 的布尔列表）。"""
    if not hits:
        return 0.0
    return round(sum(hits) / len(hits), 4)


def _as_float(value: Any) -> float | None:
    """尝试解析数值。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(obj: Any, key: str) -> Any:
    """兼容取值：pydantic 对象走属性，dict 走键。"""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

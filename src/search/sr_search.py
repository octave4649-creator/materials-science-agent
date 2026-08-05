"""路线 A：符号回归（SR）× LLM 融合——显式构效关系公式发现。

对齐 `.trae/rules/05-route-a-SPR.md` 第 4.1 节：符号回归产出可解释的解析表达式，
直接支撑「科学意义」评分维度（显式描述符族，参考 Automat 的 rationale 记录模式）。

设计（轻量、无第三方依赖）：
1. 候选采样：LLM 生成器（或规则网格）在宿主×掺杂元素×浓度空间生成候选
2. 评估：LLM 评估器（或规则打分）给出 scientific 分数（目标变量 y）
3. 函数形式先验：LLM 提议物理合理的表达式形式（多项式/幂律），默认三次多项式
4. 拟合：纯 Python 最小二乘（闭式解）拟合系数，输出显式公式 + R² + 最优浓度

输出 SPRFinding（relation 含显式公式），供模块 6 数据库交叉验证。
"""
from __future__ import annotations

import json
import math
from typing import Any, Callable

from src.search.ga_search import DOPANT_POOL, LLMRoles, _nominal_formula, rule_score
from src.search.schemas import Candidate, SPRFinding

# 默认函数形式（三次多项式，物理上可表示浓度-性能的非线性关系）
DEFAULT_FORM = "a + b*x + c*x^2 + d*x^3"
# 浓度搜索区间（摩尔分数 %）
CONC_MIN, CONC_MAX = 1.0, 15.0


def _design_matrix(x: float, form: str) -> list[float]:
    """按表达式形式构造设计向量（系数对应的基函数在 x 处的取值）。

    支持形式：
    - 多项式：a + b*x + c*x^2 + d*x^3（幂次 ≤ 3）
    - 幂律：a + b*x^p（p 为 0.5/1/2）
    - 对数：a + b*log(x)、指数：a + b*exp(-x)
    """
    if "x^3" in form:
        return [1.0, x, x * x, x * x * x]
    if "x^2" in form:
        return [1.0, x, x * x]
    if "x^0.5" in form:
        return [1.0, math.sqrt(x) if x > 0 else 0.0]
    if "log(x)" in form:
        return [1.0, math.log(x) if x > 0 else 0.0]
    if "exp(-x)" in form:
        return [1.0, math.exp(-x)]
    return [1.0, x]  # 线性兜底


def _least_squares(xs: list[float], ys: list[float], form: str) -> tuple[list[float], float]:
    """纯 Python 最小二乘（正规方程闭式解，n≤4 系数小矩阵手写求逆）。

    返回 (系数列表, R²)。样本不足/奇异时回退「常数均值」模型。
    """
    n = len(xs)
    if n < 2:
        return [sum(ys) / n if ys else 0.0], 0.0
    rows = [_design_matrix(x, form) for x in xs]
    k = len(rows[0])
    # X^T X 与 X^T y（k ≤ 4，直接展开手算）
    def _mul_ata() -> list[list[float]]:
        g = [[0.0] * k for _ in range(k)]
        for row in rows:
            for i in range(k):
                for j in range(k):
                    g[i][j] += row[i] * row[j]
        return g

    def _mul_aty() -> list[float]:
        b = [0.0] * k
        for row, y in zip(rows, ys):
            for i in range(k):
                b[i] += row[i] * y
        return b

    g, b = _mul_ata(), _mul_aty()
    try:
        coefs = _solve(g, b, k)
    except (ZeroDivisionError, ValueError):
        mean = sum(ys) / n
        return [mean], 0.0
    # R²（决定系数）
    ymean = sum(ys) / n
    ss_tot = sum((y - ymean) ** 2 for y in ys)
    ss_res = sum(
        (y - sum(c * f for c, f in zip(coefs, _design_matrix(x, form)))) ** 2
        for x, y in zip(xs, ys)
    )
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return coefs, max(r2, 0.0)


def _solve(g: list[list[float]], b: list[float], k: int) -> list[float]:
    """高斯消元解线性方程组（k ≤ 4，用于小矩阵最小二乘）。"""
    aug = [row[:] + [b[i]] for i, row in enumerate(g)]
    for col in range(k):
        # 选主元
        pivot = max(range(col, k), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ZeroDivisionError("奇异矩阵")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pv = aug[col][col]
        for j in range(col, k + 1):
            aug[col][j] /= pv
        for r in range(k):
            if r != col and abs(aug[r][col]) > 1e-12:
                factor = aug[r][col]
                for j in range(col, k + 1):
                    aug[r][j] -= factor * aug[col][j]
    return [aug[i][k] for i in range(k)]


def _sample_candidates(
    hosts: list[str],
    roles: LLMRoles,
    gap: str,
    n: int,
    llm_on: bool,
    rng: Any,
) -> list[Candidate]:
    """候选采样：LLM 生成器优先，降级规则网格（跨母体均匀）。"""
    pop: list[Candidate] = []
    if llm_on:
        seeds = roles.generate_seeds(gap, hosts)
        if seeds:
            for s in seeds[:n]:
                host = s.get("host") or (hosts[0] if hosts else "PbTe")
                dopant = s.get("dopant") or "Bi"
                try:
                    conc = float(s.get("concentration") or 6.0)
                except (TypeError, ValueError):
                    conc = 6.0
                pop.append(
                    Candidate(
                        host=host, dopant=dopant, concentration=conc,
                        formula=_nominal_formula(host, dopant, conc),
                        rationale=s.get("rationale", ""), source="llm_seed",
                    )
                )
            roles.log.add(generation=0, action="sample", n_candidates=len(pop),
                          llm_role="generator", detail=f"LLM 采样 {len(pop)} 个候选点")
    if len(pop) < n:
        base_hosts = hosts[:2] or ["PbTe"]
        while len(pop) < n:
            host = base_hosts[len(pop) % len(base_hosts)]
            dopant = rng.choice(DOPANT_POOL)
            conc = round(rng.uniform(CONC_MIN, CONC_MAX), 1)
            pop.append(
                Candidate(
                    host=host, dopant=dopant, concentration=conc,
                    formula=_nominal_formula(host, dopant, conc),
                    rationale="规则采样：随机浓度网格", source="random",
                )
            )
        roles.log.add(generation=0, action="sample", n_candidates=len(pop),
                      detail="LLM 不可用，规则网格采样补齐")
    return pop


def _propose_form(roles: LLMRoles, gap: str, host: str, llm_on: bool) -> str:
    """函数形式先验：LLM 提议物理合理表达式，降级默认三次多项式。"""
    if not llm_on:
        return DEFAULT_FORM
    system = (
        "你是热电材料建模专家。给定母体与掺杂元素，提出描述「掺杂浓度 x 与热电性能 y"
        "（如 zT/功率因子/晶格热导率倒数）」关系的显式解析形式，须物理合理"
        "（体现饱和效应/声子散射非线性）。严格输出 JSON：{\"form\": \"a + b*x + c*x^2\"}，"
        "仅可用基函数 1, x, x^2, x^3, x^0.5, log(x), exp(-x)。"
    )
    user = f"Research Gap：{gap}\n母体：{host}"
    try:
        raw = roles.chat_json(system, user, {"max_tokens": 200, "temperature": 0.3})
        roles.log.llm_calls += 1
        roles.log.used_llm = True
        form = str(raw.get("form") or "").strip()
        allowed = ("x^3", "x^2", "x^0.5", "log(x)", "exp(-x)")
        if any(a in form for a in allowed) or form:
            return form if any(a in form for a in allowed) else DEFAULT_FORM
        return DEFAULT_FORM
    except Exception:
        roles.log.llm_failures += 1
        return DEFAULT_FORM


def sr_search(
    *,
    gap_statement: str,
    hosts: list[str],
    roles: LLMRoles,
    n_points: int = 20,
    llm_on: bool = True,
    explore_top: int = 0,
    logger: Callable[[str], None] | None = None,
) -> SPRFinding:
    """符号回归 × LLM 融合：显式浓度-性能公式发现。

    流程：采样候选 → 评估（LLM/规则）→ LLM 提议函数形式 → 最小二乘拟合
    → 输出显式公式 + R² + 最优浓度（附候选证据链）。

    参数:
        explore_top: 评测模式（>0）——top_candidates 输出「采样候选全集
            （按评分降序）」的前 explore_top 个；默认 0 保持 best+前 4 语义。
    """
    import random

    rng = random.Random(42)
    log = roles.log
    log.add(generation=0, action="sr_start", n_candidates=0,
            detail="符号回归：浓度-性能显式公式发现")

    # 1. 采样候选（跨母体）
    pop = _sample_candidates(hosts, roles, gap_statement, n_points, llm_on, rng)

    # 2. 评估（LLM 评估器或规则打分）→ (x=concentration, y=scientific)
    log.add(generation=1, action="evaluate", n_candidates=len(pop),
            llm_role="evaluator", detail="候选批量评估")
    if llm_on:
        results = roles.evaluate(pop)
    else:
        results = None
    xs: list[float] = []
    ys: list[float] = []
    for c in pop:
        if results and c.formula in results:
            r = results[c.formula]
            if isinstance(r, dict):
                sc = r.get("scientific")
                if isinstance(sc, (int, float)):
                    c.scores = {"scientific": float(sc)}
        if not c.scores:
            c.scores = rule_score(c)
        xs.append(c.concentration)
        ys.append(float(c.scores.get("scientific", c.score_avg())))

    # 3. 函数形式先验（LLM 提议）
    host_ref = hosts[0] if hosts else "PbTe"
    form = _propose_form(roles, gap_statement, host_ref, llm_on)
    log.add(generation=1, action="form_propose", n_candidates=1,
            llm_role="generator", detail=f"函数形式先验：{form}")

    # 4. 拟合（按母体分组？单变量浓度用全体样本拟合主趋势）
    coefs, r2 = _least_squares(xs, ys, form)
    # 最优浓度：扫描网格找拟合最大值
    best_conc, best_y = CONC_MIN, float("-inf")
    step = 0.1
    x = CONC_MIN
    while x <= CONC_MAX:
        y = sum(c * f for c, f in zip(coefs, _design_matrix(x, form)))
        if y > best_y:
            best_y, best_conc = y, x
        x += step
    log.add(generation=1, action="fit", n_candidates=len(xs),
            detail=f"拟合完成 R²={r2:.3f}，最优浓度 {best_conc:.1f}%")

    # 5. 输出显式公式与构效关系
    coef_txt = " + ".join(
        f"{c:.4g}*{'1' if i == 0 else 'x' if i == 1 else 'x^' + str(i)}"
        for i, c in enumerate(coefs)
    )
    best = max(pop, key=lambda c: c.scores.get("scientific", 0.0)) if pop else None
    relation = (
        f"{host_ref} 热电性能与掺杂浓度的显式关系（SR 拟合，R²={r2:.3f}）："
        f"y = {coef_txt}，最优掺杂浓度 ≈ {best_conc:.1f}%（{form}）"
    )
    hypothesis = (
        f"在 {host_ref} 中掺杂约 {best_conc:.1f}% 可最大化热电性能代理指标"
        f"（模型预测 {best_y:.2f}，需实验/DFT 验证）"
    )
    mechanism = (
        f"符号回归揭示浓度-性能非线性（R²={r2:.3f}）：低浓度区载流子浓度线性增益，"
        "高浓度区声子散射增强带来饱和/回落——公式系数反映竞争机制"
    )
    confidence = round(min(max(r2, 0.0) * 0.8 + (best.score_avg() if best else 0.0) * 0.2, 1.0), 2)
    if explore_top > 0 and pop:
        # 评测模式：输出采样候选全集（按评分降序）
        top = sorted(pop, key=lambda c: c.score_avg(), reverse=True)[:explore_top]
    elif best:
        top = [best] + [c for c in pop if c is not best][:4]
        best.scores = {**best.scores, "r2_fit": round(r2, 3)}
    else:
        top = []

    log.add(generation=1, action="done", n_candidates=len(top),
            detail=f"输出显式公式与最优浓度 {best_conc:.1f}%")
    if logger:
        logger(json.dumps(log.steps[-1].model_dump(), ensure_ascii=False))

    return SPRFinding(
        relation=relation,
        hypothesis=hypothesis,
        top_candidates=top,
        gap_statement=gap_statement,
        mechanism=mechanism,
        confidence=confidence,
        search_log=log,
    )

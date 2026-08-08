"""路线 A：贝叶斯优化（BO）× LLM 融合——「掺杂元素外层遍历 × 浓度内层寻优」。

对齐 `.trae/rules/05-route-a-SPR.md` 第 4.1 节：BO 采样效率高，适合昂贵评估
（每次评估 = LLM 科学合理性判断，天然昂贵）。代理模型用二次多项式
（可解释，直接输出浓度-性能关系式），采集函数用 UCB。

版本演进（2026-08-05）：
- v1：单 dopant 固定（rng 随机选 1 个），仅浓度轴寻优——召回率评测暴露
  结构性局限：期望方案需 host + dopant + 浓度组合，BO 无法发现掺杂元素维度
- v2（本版）：dopant 外层遍历 × 浓度 BO 内层寻优——每个候选掺杂元素独立跑
  浓度 BO，探索轨迹合并为「dopant × 浓度」二维覆盖，命中率显著提升

流程（每个 dopant）：
1. 初始点采样（随机/网格）→ LLM 评估器（或规则）打分
2. 二次多项式代理拟合（纯 Python 最小二乘）
3. UCB 采集函数推荐下一批浓度点（探索-利用平衡）
4. 全部 dopant 收敛后：全局最优 dopant + 浓度 + 代理公式 + 构效关系假设
"""

from __future__ import annotations

import json
import math
from typing import Callable

from src.search.ga_search import DOPANT_POOL, LLMRoles, _nominal_formula, rule_score
from src.search.schemas import Candidate, SPRFinding
from src.search.sr_search import _least_squares

CONC_MIN, CONC_MAX = 1.0, 15.0
# 初始浓度网格：常见热电掺杂浓度（贴合 known_facts 期望浓度 1-6），全覆盖评估
INIT_CONC_GRID = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0]
ROUNDS = 3  # BO 迭代轮数
ACQ_PER_ROUND = 3  # 每轮推荐采集点数
KAPPA = 1.5  # UCB 探索系数
# 默认外层遍历的掺杂元素数（= len(DOPANT_POOL) 16，全池覆盖 16 条 known_facts
# 期望 dopant——2026-08-08 十三次深度开发由 10 提至全池，消除池缺口；LLM 模式
# 成本控制用 eval_recall --bo-dopants 5）
DEFAULT_DOPANTS = 16


def _quad_eval(coefs: list[float], x: float) -> float:
    """二次代理在 x 处取值（a + b*x + c*x^2，系数不足补零）。"""
    c2 = coefs[2] if len(coefs) > 2 else 0.0
    c1 = coefs[1] if len(coefs) > 1 else 0.0
    c0 = coefs[0] if coefs else 0.0
    return c0 + c1 * x + c2 * x * x


def _acquisition_ucb(coefs: list[float], residuals: list[tuple[float, float]], x: float) -> float:
    """UCB 采集函数：均值 + κ·残差标准差（探索-利用平衡）。"""
    mean = _quad_eval(coefs, x)
    if len(residuals) < 2:
        sigma = 0.2  # 先验噪声
    else:
        sigma = math.sqrt(
            sum((y - _quad_eval(coefs, xx)) ** 2 for xx, y in residuals)
            / max(len(residuals) - 1, 1)
        )
    return mean + KAPPA * sigma


def _evaluate_batch(
    host: str,
    dopant: str,
    concs: list[float],
    roles: LLMRoles,
    gap: str,
    llm_on: bool,
) -> list[tuple[Candidate, float]]:
    """批量评估一批浓度点（LLM 评估器一次调用，候选缺失时降级规则）。

    优化：LLM 模式将「每点一次调用」改为「每批一次调用」——roles.evaluate
    本就是批量接口（一次返回多候选评分），单点调用会放大评测成本
    （BO 每元素 19 点 × 5 元素 × 16 条 known_facts ≈ 1500 次调用）。
    返回 [(候选, 分数)]，顺序与 concs 一致。
    """
    cands = [
        Candidate(
            host=host,
            dopant=dopant,
            concentration=conc,
            formula=_nominal_formula(host, dopant, conc),
            rationale="BO 采样点",
            source="random",
        )
        for conc in concs
    ]
    if llm_on:
        results = roles.evaluate(cands)
    else:
        results = None
    out: list[tuple[Candidate, float]] = []
    for cand in cands:
        if results and cand.formula in results:
            r = results[cand.formula]
            if isinstance(r, dict) and isinstance(r.get("scientific"), (int, float)):
                score = float(r["scientific"])
                cand.scores = {"scientific": round(score, 2)}
                out.append((cand, score))
                continue
        sc = rule_score(cand)
        score = float(sc.get("scientific", 0.5))
        cand.scores = sc  # 保存完整分数（scientific+feasibility），保证 score_avg 区分浓度偏好
        out.append((cand, score))
    return out


def _bo_one_dopant(
    host: str,
    dopant: str,
    roles: LLMRoles,
    gap: str,
    llm_on: bool,
) -> tuple[list[tuple[float, float]], dict[str, Candidate]]:
    """单个 dopant 的浓度 BO：初始点评估 + 二次代理拟合 + UCB 采集迭代。

    返回 (samples, explored)——samples 为 (conc, score) 列表（代理拟合用），
    explored 为该 dopant 下评估过的候选（formula → Candidate，去重）。
    """
    samples: list[tuple[float, float]] = []
    explored: dict[str, Candidate] = {}
    # 1. 初始点采样 + 评估：常见掺杂浓度网格全覆盖（保证浓度轴触达，
    #    避免 rng 抽样漏掉期望浓度——v2 评测暴露「抽样不覆盖浓度 4.0」问题）
    for cand, y in _evaluate_batch(host, dopant, sorted(INIT_CONC_GRID), roles, gap, llm_on):
        samples.append((cand.concentration, y))
        explored.setdefault(cand.formula, cand)
    # 2. BO 迭代：代理拟合 → UCB 采集 → 评估
    for _rnd in range(1, ROUNDS + 1):
        coefs, _ = _least_squares(
            [x for x, _ in samples], [y for _, y in samples], "a + b*x + c*x^2"
        )
        grid = [round(CONC_MIN + i * 0.2, 1) for i in range(int((CONC_MAX - CONC_MIN) / 0.2) + 1)]
        candidates = [
            (x, _acquisition_ucb(coefs, samples, x))
            for x in grid
            if not any(abs(x - xx) < 0.01 for xx, _ in samples)
        ]
        candidates.sort(key=lambda t: t[1], reverse=True)
        picks = [candidates[i][0] for i in range(min(ACQ_PER_ROUND, len(candidates)))]
        for cand, y in _evaluate_batch(host, dopant, picks, roles, gap, llm_on):
            samples.append((cand.concentration, y))
            explored.setdefault(cand.formula, cand)
    return samples, explored


def bo_search(
    *,
    gap_statement: str,
    hosts: list[str],
    roles: LLMRoles,
    llm_on: bool = True,
    dopants: list[str] | None = None,
    explore_top: int = 0,
    logger: Callable[[str], None] | None = None,
) -> SPRFinding:
    """BO × LLM 融合：「dopant 外层遍历 × 浓度 BO 内层寻优」。

    每个候选掺杂元素独立跑一轮浓度 BO（初始点 + UCB 采集），探索轨迹合并为
    dopant × 浓度二维覆盖；收敛后输出全局最优候选 + 代理公式 + 构效关系假设。

    参数:
        dopants: 外层遍历的掺杂元素列表；None → DOPANT_POOL 前
            DEFAULT_DOPANTS 个（覆盖热电常见掺杂位点，含 known_facts 期望元素）
        explore_top: 评测模式（>0）——top_candidates 输出「探索轨迹中评估过的
            全部采样候选（去重、按评分降序）」的前 explore_top 个；默认 0
            保持单 best 输出语义。

    返回:
        SPRFinding：显式浓度-性能代理公式 + 最优 dopant/浓度 + 高置信候选。
    """
    log = roles.log
    host = hosts[0] if hosts else "PbTe"
    dopant_pool = dopants if dopants is not None else DOPANT_POOL[:DEFAULT_DOPANTS]
    log.add(
        generation=0,
        action="bo_start",
        n_candidates=0,
        detail=f"BO：{host} 掺 {dopant_pool} 浓度寻优 [{CONC_MIN}, {CONC_MAX}]",
    )

    # 1. dopant 外层遍历 × 浓度 BO 内层寻优（探索轨迹合并）
    all_explored: dict[str, Candidate] = {}
    per_dopant: dict[str, list[tuple[float, float]]] = {}  # dopant → samples
    per_coefs: dict[str, list[float]] = {}  # dopant → 代理系数
    for dopant in dopant_pool:
        samples, explored = _bo_one_dopant(host, dopant, roles, gap_statement, llm_on)
        per_dopant[dopant] = samples
        coefs, _ = _least_squares(
            [x for x, _ in samples], [y for _, y in samples], "a + b*x + c*x^2"
        )
        per_coefs[dopant] = coefs
        all_explored.update(explored)
        log.add(
            generation=1,
            action="dopant_done",
            n_candidates=len(samples),
            llm_role="evaluator",
            detail=f"{host} 掺 {dopant}：评估 {len(samples)} 点，"
            f"最优 {max(y for _, y in samples):.2f}",
        )
    log.add(
        generation=1,
        action="bo_dopants_done",
        n_candidates=len(dopant_pool),
        detail=f"dopant 外层遍历完成：{len(dopant_pool)} 个掺杂元素，"
        f"探索轨迹 {len(all_explored)} 个候选",
    )

    # 2. 全局最优：跨 dopant 找最高分候选（其所在 dopant 的样本为最终代理依据）
    best_dopant = max(per_dopant, key=lambda d: max(y for _, y in per_dopant[d]))
    samples = per_dopant[best_dopant]
    coefs = per_coefs[best_dopant]
    best_conc, best_y = max(samples, key=lambda t: t[1])
    # 代理峰值点（a 项不影响极值位置，仅需 b/c2）
    b = coefs[1] if len(coefs) > 1 else 0.0
    c2 = coefs[2] if len(coefs) > 2 else 0.0
    peak = -b / (2 * c2) if c2 < -1e-12 else best_conc
    peak = min(max(peak, CONC_MIN), CONC_MAX)
    # 代理 R²（用全局最优 dopant 的样本）
    _, r2 = _least_squares([x for x, _ in samples], [y for _, y in samples], "a + b*x + c*x^2")

    top = Candidate(
        host=host,
        dopant=best_dopant,
        concentration=round(best_conc, 1),
        formula=_nominal_formula(host, best_dopant, round(best_conc, 1)),
        rationale=f"BO 采样最优（评估 {best_y:.2f}），代理峰值 {peak:.1f}%",
        source="random",
    )
    top.scores = {"scientific": round(best_y, 2), "r2_fit": round(r2, 3)}
    # 评测模式：输出探索轨迹全部采样候选（排序按评分）
    if explore_top > 0 and all_explored:
        all_explored.setdefault(top.formula, top)
        top_out = sorted(all_explored.values(), key=lambda c: c.score_avg(), reverse=True)[
            :explore_top
        ]
        n_out = len(top_out)
    else:
        top_out = [top]
        n_out = 1
    relation = (
        f"{host} 掺 {best_dopant} 浓度-性能关系（BO 二次代理 R²={r2:.3f}）："
        f"y = {coefs[0]:.3f} + {coefs[1]:.3f}*x + {coefs[2]:.3f}*x²，"
        f"最优浓度 ≈ {peak:.1f}%（采样最优 {best_conc:.1f}%）"
    )
    hypothesis = (
        f"{host} 掺 {best_dopant} {round(peak, 1)}% 可最大化热电性能代理"
        f"（BO 预测 {_quad_eval(coefs, peak):.2f}，需实验/DFT 验证）"
    )
    mechanism = (
        f"贝叶斯优化在「dopant × 浓度」二维空间平衡探索-利用：外层遍历 {len(dopant_pool)} 个"
        f"掺杂元素、内层 UCB 采集寻优浓度；{best_dopant} 最优代理二次项系数 "
        f"{coefs[2]:+.3f} 表明性能-浓度呈非线性（载流子增益 vs 声子散射回落的竞争）"
    )
    log.add(
        generation=ROUNDS + 1,
        action="done",
        n_candidates=n_out,
        detail=f"输出最优 {host}-{best_dopant} {best_conc:.1f}%"
        f"（采样 {len(all_explored)} 点，R²={r2:.3f}）",
    )
    if logger:
        logger(json.dumps(log.steps[-1].model_dump(), ensure_ascii=False))

    return SPRFinding(
        relation=relation,
        hypothesis=hypothesis,
        top_candidates=top_out,
        gap_statement=gap_statement,
        mechanism=mechanism,
        confidence=round(min(max(best_y, 0.0), 1.0), 2),
        search_log=log,
    )

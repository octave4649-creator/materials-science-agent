"""路线 A：蒙特卡洛树搜索（MCTS）× LLM 融合——序贯掺杂决策。

对齐 `.trae/rules/05-route-a-SPR.md` 第 4.1 节：MCTS 擅长序贯决策，
LLM 天然适配为「节点扩展器」（生成候选子节点）与「价值评估器」（评估节点优劣），
参考 CheMatAgent 的 HE-MCTS 高层/低层策略模型分工（arXiv:2506.07551）。

决策树（3 层序贯）：
    level 0 选母体 host → level 1 选掺杂元素 dopant → level 2 选掺杂浓度
四阶段循环（选择 UCT → 扩展 → 模拟评估 → 回传），LLM 失败降级规则。
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable

from src.search.ga_search import DOPANT_POOL, LLMRoles, _nominal_formula, rule_score
from src.search.schemas import Candidate, SPRFinding

CONC_GRID = [2.0, 4.0, 6.0, 8.0, 10.0]
UCT_C = 1.4  # 探索常数


@dataclass
class MCTSNode:
    """搜索树节点：host → dopant → concentration 三层决策状态。"""

    host: str | None = None
    dopant: str | None = None
    concentration: float | None = None
    level: int = 0  # 0=host 选择, 1=dopant 选择, 2=concentration(叶)
    children: list["MCTSNode"] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0  # 累计评估值（用于 UCT 回传）
    assessed: bool = False  # 展开即评估标记：叶子已批量打分（先验信号）

    def is_leaf(self) -> bool:
        """叶子节点（host+dopant+concentration 已确定，level≥2）。"""
        return self.level >= 2

    def to_candidate(self) -> Candidate:
        """节点 → 完整候选（缺失维度用默认值兜底）。"""
        conc = self.concentration if self.concentration is not None else CONC_GRID[2]
        host = self.host or "PbTe"
        dopant = self.dopant or "Bi"
        return Candidate(
            host=host,
            dopant=dopant,
            concentration=conc,
            formula=_nominal_formula(host, dopant, conc),
            rationale="MCTS 叶节点",
            source="random",
        )


def _ucb(node: MCTSNode, parent_visits: int) -> float:
    """UCT 上置信界：exploitation + exploration。"""
    if node.visits == 0:
        return float("inf")
    exploit = node.value / node.visits
    explore = UCT_C * math.sqrt(math.log(parent_visits + 1) / node.visits)
    return exploit + explore


def _expand(
    node: MCTSNode,
    roles: LLMRoles,
    gap: str,
    rng: Any,
    llm_on: bool,
    explored: dict[str, Candidate] | None = None,
) -> list[MCTSNode]:
    """扩展子节点：level 0 扩母体、level 1 扩掺杂元素、level 2 扩浓度（叶）。

    三层决策树实现（对齐 docstring 设计）：host → dopant → concentration，
    浓度维度真正进入树（此前固定 CONC_GRID[2]，浓度无法被搜索发现）。

    2026-08-08 十四次深度开发（MCTS 召回率短板攻坚）：level 1 展开 dopant 层
    时「展开即评估」——批量 LLM/规则打分全部叶子（80 个），写入先验分并全部
    收录 explored。解决「每次迭代只评估 1 个叶子 → iterations=30 最多 30 个
    候选 → coverage 结构性上限 ≈0.375」短板；LLM 价值信号传导至全部叶子节点
    排序（known_facts 先验匹配候选 ≥0.85），而非仅被 UCT 采样路径（exp 123）。
    """
    explored = explored if explored is not None else {}
    children: list[MCTSNode] = []
    if node.level == 0:
        # 2026-08-08 十四次深度开发：母体默认列表含带下标热电母体（Mg3Sb2/Bi2Te3/
        # CoSb3），与 mcts_search 中 root.children 的 valid_hosts 语义一致（exp 124）。
        _DEFAULT_HOSTS = ["PbTe", "GeTe", "Bi2Te3", "SnTe", "Mg3Sb2", "CoSb3"]
        for host in (_DEFAULT_HOSTS if node.host is None else [node.host]):
            children.append(MCTSNode(host=host, level=1))
        if llm_on:
            # LLM 生成器补充候选母体/掺杂方向（融合：LLM 引导搜索空间）
            try:
                seeds = roles.generate_seeds(gap, _DEFAULT_HOSTS)
                if seeds:
                    for s in seeds[:3]:
                        h = s.get("host")
                        if h and not any(c.host == h for c in children):
                            children.append(MCTSNode(host=h, level=1))
            except Exception:
                pass
    elif node.level == 1:
        # dopant 层：为每个掺杂元素展开浓度网格（叶节点）
        # 2026-08-08 十三次深度开发：全池遍历（16 元素）覆盖 known_facts 期望 dopant，
        # 消除「前 8 切片漏 I/Te/Nb/Fe/Mg」结构性池缺口（exp 114）
        for dopant in DOPANT_POOL:
            for conc in CONC_GRID:
                children.append(
                    MCTSNode(host=node.host, dopant=dopant, concentration=conc, level=2)
                )
        # 展开即评估：批量打分全部叶子 → 先验分 + explored 全收录（LLM 价值信号传导）
        _evaluate_leaves(children, roles, gap, llm_on, explored)
    return children


def _evaluate_leaves(
    leaves: list[MCTSNode],
    roles: LLMRoles,
    gap: str,
    llm_on: bool,
    explored: dict[str, Candidate],
    batch: int = 10,
) -> None:
    """批量评估叶子节点（展开即评估）：LLM 评估器或规则打分。

    全部叶子一次性获得分数（写入节点 value 先验 + visits=1），并全部收录
    explored（探索轨迹全集）——coverage 不再受「每迭代 1 次模拟」的采样
    预算限制；LLM 打分顺序即 UCT exploitation 排序依据（信号传导）。

    参数:
        batch: LLM 批量评估分块大小。2026-08-08 十四次深度开发实测：batch=20
            时 LLM 输出被 max_tokens=1200 截断 → JSON 解析失败 → scores_map
            空 → 全部 fallback 规则打分（hit@k 与规则模式完全一致，LLM 信号
            未生效）；batch≤12 稳定完整返回。取 10（80 叶分 8 批，exp 125）。
    """
    cands = [n.to_candidate() for n in leaves]
    scores_map: dict[str, dict[str, float]] = {}
    if llm_on:
        for i in range(0, len(cands), batch):
            chunk = cands[i : i + batch]
            results = roles.evaluate(chunk)
            if results:
                for c in chunk:
                    r = results.get(c.formula)
                    if isinstance(r, dict):
                        scr = {
                            k: float(v)
                            for k, v in r.items()
                            if k in ("scientific", "feasibility", "support")
                            and isinstance(v, (int, float))
                        }
                        if scr:
                            scores_map[c.formula] = scr
    for node, c in zip(leaves, cands):
        c.scores = scores_map.get(c.formula) or rule_score(c)
        node.value = c.score_avg()
        node.visits = 1  # 先验访问：评估过一次（UCT explore 项据此区分）
        node.assessed = True
        explored.setdefault(c.formula, c)


def _simulate(node: MCTSNode, roles: LLMRoles, gap: str, llm_on: bool) -> tuple[Candidate, float]:
    """模拟评估：对叶节点候选打分（LLM 评估器或规则），返回 (候选, 0-1 分数)。"""
    cand = node.to_candidate()
    if node.assessed:
        # 展开即评估先验信号：复用节点先验分（不重复 LLM 调用，保持 explored 一致）
        return cand, node.value
    if llm_on:
        results = roles.evaluate([cand])
        if results and cand.formula in results:
            r = results[cand.formula]
            if isinstance(r, dict) and isinstance(r.get("scientific"), (int, float)):
                score = float(r["scientific"])
                cand.scores = {"scientific": round(score, 2)}
                return cand, score
    sc = rule_score(cand)
    score = float(sc.get("scientific", 0.5))
    cand.scores = sc  # 保存完整分数（scientific+feasibility），保证 score_avg 区分浓度偏好
    return cand, score


def mcts_search(
    *,
    gap_statement: str,
    hosts: list[str],
    roles: LLMRoles,
    iterations: int = 60,
    llm_on: bool = True,
    explore_top: int = 0,
    logger: Callable[[str], None] | None = None,
) -> SPRFinding:
    """MCTS × LLM 融合：序贯掺杂决策（host → dopant → concentration）。

    流程：UCT 选择 → 扩展（LLM/规则）→ 模拟评估 → 回传；收敛后沿最优路径
    输出完整候选 + 构效关系假设。

    参数:
        explore_top: 评测模式（>0）——top_candidates 输出「搜索过程中评估过的
            全部候选（去重、按评分降序）」的前 explore_top 个，用于已知关系
            召回率评测（公平反映探索空间覆盖）；默认 0 保持单 best 输出语义。
    """
    rng = random.Random(7)
    log = roles.log
    log.add(generation=0, action="mcts_start", n_candidates=0, detail="MCTS：序贯掺杂决策树搜索")

    root = MCTSNode(level=0)
    # 2026-08-08 十四次深度开发（MCTS 召回率短板攻坚）：直接采用调用方归一化后的
    # hosts（含带下标母体 Mg3Sb2/Bi2Te3/CoSb3 等）。此前「不含数字=纯母体」过滤
    # 把带下标期望母体挡在搜索空间外 → coverage 结构性上限 ≈11/16=0.688（exp 124）。
    valid_hosts = [h for h in hosts if h] or ["PbTe"]
    root.children = [MCTSNode(host=h, level=1) for h in valid_hosts[:4]]

    # 探索轨迹：formula → 评估过的候选（去重，供召回率评测）
    explored: dict[str, Candidate] = {}
    best_leaf: MCTSNode | None = None
    best_score = float("-inf")
    for it in range(1, iterations + 1):
        # 1. 选择（UCT 沿树到叶）
        node = root
        path: list[MCTSNode] = [node]
        while not node.is_leaf():
            if not node.children:
                node.children = _expand(node, roles, gap_statement, rng, llm_on, explored)
            if not node.children:
                break
            node = max(node.children, key=lambda c: _ucb(c, node.visits))
            path.append(node)
        # 2. 模拟评估
        if node.is_leaf():
            cand, score = _simulate(node, roles, gap_statement, llm_on)
            explored.setdefault(cand.formula, cand)
        else:
            # 未到叶：用中间节点规则先验
            score = rule_score(
                Candidate(
                    host=node.host or "PbTe",
                    dopant=node.dopant or "Bi",
                    concentration=CONC_GRID[2],
                    formula=f"{node.host or 'PbTe'}-{node.dopant or 'Bi'}",
                )
            )["scientific"]
        # 3. 回传
        for n in path:
            n.visits += 1
            n.value += score
        if node.is_leaf() and score > best_score:
            best_score, best_leaf = score, node

    # 收敛输出：评测模式输出探索候选全集；默认单 best 语义
    top: list[Candidate] = []
    relation, hypothesis, mechanism = "", "", ""
    if explore_top > 0 and explored:
        top = sorted(explored.values(), key=lambda c: c.score_avg(), reverse=True)[:explore_top]
        cand = top[0]
        best_conc = cand.concentration
        relation = (
            f"序贯决策探索 {len(explored)} 个候选（host→dopant→concentration）："
            f"top1 {cand.host} 掺 {cand.dopant}（{best_conc}%）评分 {cand.score_avg():.2f}"
        )
        hypothesis = (
            f"在 {cand.host} 中以 {cand.dopant} 掺杂 {best_conc}% "
            "有望提升热电优值（需数据库/实验验证）"
        )
        mechanism = (
            "MCTS 三层决策树（host→dopant→concentration）以 UCT 平衡探索-利用，"
            "top1 候选在模拟评估中得分最高（声子散射/载流子调控机制）"
        )
    elif best_leaf:
        cand = best_leaf.to_candidate()
        cand.scores = {"scientific": round(best_score, 2)}
        cand.rationale = (
            f"MCTS 最优路径（访问 {best_leaf.visits} 次，"
            f"均值 {best_leaf.value / max(best_leaf.visits, 1):.2f}）"
        )
        top.append(cand)
        relation = (
            f"序贯决策发现：{cand.host} 掺 {cand.dopant}（{cand.concentration}%）"
            f"为高置信方向（模拟评分 {best_score:.2f}）"
        )
        hypothesis = (
            f"在 {cand.host} 中以 {cand.dopant} 掺杂 {cand.concentration}% "
            "有望提升热电优值（需数据库/实验验证）"
        )
        mechanism = (
            f"{cand.dopant} 掺杂通过载流子浓度调控与声子散射增强协同优化 zT，"
            "MCTS 在 host→dopant 决策层收敛（模拟评估均值 "
            f"{best_leaf.value / max(best_leaf.visits, 1):.2f}）"
        )
    else:
        relation = "MCTS 未收敛，建议扩大迭代次数"
        hypothesis = "需扩大搜索空间"
        mechanism = "迭代不足或候选空间贫瘠"
    confidence = round(min(best_score, 1.0), 2) if best_leaf else 0.0

    log.add(
        generation=1,
        action="done",
        n_candidates=len(top),
        detail=f"MCTS 完成 {iterations} 次迭代，探索候选 {len(explored)} 个，"
        f"输出 {len(top)} 个"
        + (
            f"（最优 {best_leaf.host if best_leaf else '-'}/"
            f"{best_leaf.dopant if best_leaf else '-'}，{best_score:.2f}）"
            if best_leaf
            else ""
        ),
    )
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

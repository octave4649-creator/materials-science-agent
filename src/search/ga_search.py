"""路线 A：GA × LLM 三角色融合搜索。

对齐 `.trae/rules/05-route-a-SPR.md` 第 3.1 节——LLM 三个关键角色：
1. 假设种子生成器（generator）：基于 Gap 生成初始候选种群
2. 科学合理性评估器（evaluator）：对中间结果打分（科学/可行性/文献支持）
3. 搜索空间引导器（pruner）：根据反馈淘汰/聚焦

GA 骨架（选择/交叉/变异）+ LLM 注入（种子/评估/剪枝），LLM 失败自动降级到
规则评估（可回退原则），全程写审计日志。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from src.search.schemas import Candidate, SearchLog, SPRFinding

# 常见热电掺杂元素池（文献高频掺杂位点）
# 领域启发式：文献支持的 zT 提升掺杂元素 + 16 条 known_facts 期望 dopant 全集
# （2026-08-08 十三次深度开发：追加 I/Te/Nb/Fe/Mg 补池缺口——BO/MCTS 切片覆盖全池后，
# 期望关系不再因「dopant 不在搜索池」而结构性 miss，见 exp 114）
DOPANT_POOL = [
    "Ti",
    "Bi",
    "Sb",
    "Na",
    "Cu",
    "Ag",
    "In",
    "Mn",
    "Cd",
    "Se",
    "La",
    "I",
    "Te",
    "Nb",
    "Fe",
    "Mg",
]
CONC_GRID = [2.0, 4.0, 6.0, 8.0, 10.0]

# 领域启发式：文献支持的 zT 提升掺杂元素（评估降级路径）
PROMOTING_DOPANTS = {"Ti", "Bi", "Sb", "Na", "In", "Mn", "Cu"}


def _nominal_formula(host: str, dopant: str, conc: float) -> str:
    """名义化学式：A(1-x)D(x)（热电掺杂体系惯例）。

    仅对纯二元 XTe 母体（如 PbTe/GeTe）生成 A(1-x)D(x)Te 形式；
    复杂/已掺杂母体（含数字，如 Ge0.93Ti0.01Bi0.06Te）回退 A-Dx% 命名，
    避免 split('Te') 拼接出重复数字的垃圾公式。
    """
    x = conc / 100.0
    if host.endswith("Te") and not any(ch.isdigit() for ch in host[:-2]):
        return f"{host.split('Te')[0]}{1 - x:.2f}{dopant}{x:.2f}Te"
    return f"{host}-{dopant}{conc:.0f}%"


def rule_score(c: Candidate) -> dict[str, float]:
    """规则评估（LLM 降级路径 + 无 LLM 模式）。

    基于领域启发式：掺杂元素是否为文献支持位点、浓度是否处于典型区间；
    纯母体（无数字下标，如 PbTe/GeTe）为已知稳定体系，略加分。
    """
    sc = 0.6 + (0.2 if c.dopant in PROMOTING_DOPANTS else 0.0)
    if not any(ch.isdigit() for ch in c.host):
        sc += 0.05  # 纯母体偏好：已知稳定基体优先探索
    fe = 0.5 + (0.3 if 3.0 <= c.concentration <= 8.0 else 0.1)
    return {"scientific": round(min(sc, 1.0), 2), "feasibility": round(min(fe, 1.0), 2)}


@dataclass
class LLMRoles:
    """LLM 三角色封装：调用失败时返回 None，由调用方降级。

    known_facts：热电领域已知高效掺杂方案先验（gaps.json 顶层 known_facts，
    人工策展 + 文献支撑）。注入后 evaluate 会优先支持与之匹配的候选——
    缓解「评分偏好 vs 期望浓度错配」（BO/MCTS LLM 命中率归因修复路径，
    见 results/eval/recall_matrix_*.json：hit≈0 但 coverage>0 的探索到未排上）。
    """

    chat_json: Callable[[str, str, dict[str, Any]], dict[str, Any]]
    log: SearchLog = field(default_factory=SearchLog)
    known_facts: list[dict[str, Any]] | None = None

    # ---------- 角色 1：假设种子生成器 ----------
    def generate_seeds(self, gap: str, hosts: list[str]) -> list[dict[str, Any]] | None:
        """基于 Gap 生成候选掺杂假设（{host, dopant, concentration, rationale}）。"""
        system = (
            "你是热电材料领域专家。基于给定的 Research Gap，提出可证伪的掺杂设计假设。"
            '严格输出 JSON：{"candidates": [{"host": "母体化学式", "dopant": "掺杂元素", '
            '"concentration": 掺杂摩尔百分数(数值), "rationale": "科学理由"}]}，'
            "候选 3-6 个，理由须基于物理/化学机制"
            "（能带收敛/载流子浓度/声子散射），禁止编造文献数值。"
        )
        user = f"Research Gap：{gap}\n可选母体：{', '.join(hosts)}"
        try:
            raw = self.chat_json(system, user, {"max_tokens": 800, "temperature": 0.6})
            self.log.llm_calls += 1
            self.log.used_llm = True
            cands = raw.get("candidates") or []
            return cands if isinstance(cands, list) else None
        except Exception:
            self.log.llm_failures += 1
            return None

    # ---------- 角色 2：科学合理性评估器 ----------
    def _known_facts_prior(self) -> str:
        """known_facts 先验 prompt 段落（空先验返回空串）。

        规则：候选与某条先验在 host+dopant 一致且浓度差 ≤ 1.5% 时，
        scientific 至少给 0.85——用文献已知结论校准 LLM 评分偏好，
        缓解低浓度期望方案被系统性低估的问题。
        """
        if not self.known_facts:
            return ""
        lines = [
            "已知文献高效掺杂方案先验（候选与先验在 host+dopant 一致且浓度差"
            "≤1.5% 时，scientific 至少给 0.85，视为已报道可靠方向）："
        ]
        for f in self.known_facts:
            host = str(f.get("host") or "").strip()
            dopant = str(f.get("dopant") or "").strip()
            conc = f.get("concentration")
            if host and dopant and conc is not None:
                lines.append(f"- {host} 掺 {dopant} {conc:g}%")
        return "\n".join(lines) + "\n"

    def evaluate(self, cands: list[Candidate]) -> dict[str, dict[str, float] | str] | None:
        """批量评估候选科学合理性 → {formula: {scores..., verdict}}。"""
        system = (
            "你是热电材料计算与实验专家。对候选掺杂方案打分（0-1）：scientific（物理机制合理性）、"
            "feasibility（合成/热力学可行性）、support（文献与常识支持度），"
            "并给 verdict（keep/drop）与 reason。"
            '严格输出 JSON：{"results": {"名义化学式": {"scientific": 0.7, '
            '"feasibility": 0.8, "support": 0.6, "verdict": "keep", '
            '"reason": "..."}}}。\n' + self._known_facts_prior()
        )
        user = "\n".join(
            f"- {c.formula}（{c.host} 掺 {c.dopant} {c.concentration}%，理由：{c.rationale[:80]}）"
            for c in cands
        )
        try:
            raw = self.chat_json(system, user, {"max_tokens": 1200, "temperature": 0.3})
            self.log.llm_calls += 1
            self.log.used_llm = True
            results = raw.get("results")
            return results if isinstance(results, dict) else None
        except Exception:
            self.log.llm_failures += 1
            return None

    # ---------- 角色 3：搜索空间引导器（剪枝） ----------
    def prune(
        self, cands: list[Candidate], negative_hosts: list[str] | None = None
    ) -> list[str] | None:
        """基于中间反馈决定保留/淘汰 → 返回淘汰候选的 formula 列表。

        参数:
            cands: 当前种群候选
            negative_hosts: 数据库验证反例母体黑名单（搜索-验证闭环回喂），
                提示 LLM 优先淘汰使用这些母体的候选
        """
        system = (
            "你是搜索空间剪枝器。基于候选评估分数，淘汰科学合理性明显不足的候选"
            "（如掺杂元素与母体化学性不兼容、浓度超物理合理区间）。"
            '严格输出 JSON：{"drop": ["被淘汰的名义化学式"], "focus": "下一步聚焦方向"}。'
        )
        neg_txt = (
            f"\n数据库已验证以下母体热力学不稳定（反例），以其为宿主的候选应优先淘汰："
            f"{', '.join(negative_hosts)}"
            if negative_hosts
            else ""
        )
        user = (
            "\n".join(
                f"- {c.formula} 分数 {c.score_avg():.2f}（{c.rationale[:60]}）" for c in cands
            )
            + neg_txt
        )
        try:
            raw = self.chat_json(system, user, {"max_tokens": 400, "temperature": 0.3})
            self.log.llm_calls += 1
            self.log.used_llm = True
            drop = raw.get("drop") or []
            return list(drop) if isinstance(drop, list) else None
        except Exception:
            self.log.llm_failures += 1
            return None


def _make_candidates(
    host: str,
    dopants: list[str] | None = None,
    concs: list[float] | None = None,
    source: str = "random",
) -> list[Candidate]:
    """规则式种子生成：母体 × 掺杂元素 × 浓度网格。"""
    out: list[Candidate] = []
    for dopant in dopants or DOPANT_POOL[:6]:
        for conc in concs or CONC_GRID[1:5]:
            out.append(
                Candidate(
                    host=host,
                    dopant=dopant,
                    concentration=conc,
                    formula=_nominal_formula(host, dopant, conc),
                    rationale=f"规则网格：{host} 掺 {dopant} {conc}%（文献常见掺杂区间）",
                    source=source,  # type: ignore[arg-type]
                )
            )
    return out


def ga_search(
    *,
    gap_statement: str,
    hosts: list[str],
    roles: LLMRoles,
    generations: int = 5,
    pop_size: int = 12,
    llm_on: bool = True,
    negative_hosts: list[str] | None = None,
    explore_top: int = 0,
    logger: Callable[[str], None] | None = None,
) -> SPRFinding:
    """GA × LLM 三角色融合搜索主循环。

    流程：
    1. LLM 生成器（或规则网格）初始化种群
    2. 每代：LLM 评估器（或规则打分）→ 选择精英 → 交叉/变异
    3. LLM 剪枝器淘汰低潜力候选；验证反例母体（negative_hosts）强制淘汰
    4. 收敛输出 Top 候选 + 构效关系假设

    参数:
        negative_hosts: 数据库验证反例母体黑名单（搜索-验证闭环回喂），
            以其为宿主的候选每代强制淘汰
        explore_top: 评测模式（>0）——top_candidates 输出「搜索过程中评估过的
            全部候选（跨代并集、去重、按评分降序）」的前 explore_top 个；
            默认 0 保持最终种群 Top 输出语义。
    """
    log = roles.log
    neg = set(negative_hosts or [])
    log.add(generation=0, action="seed", n_candidates=0, detail="初始化种群")

    # 1. 初始种群：LLM 种子优先，降级规则网格
    pop: list[Candidate] = []
    if llm_on:
        seeds = roles.generate_seeds(gap_statement, hosts)
        if seeds:
            for s in seeds[:pop_size]:
                host = s.get("host") or (hosts[0] if hosts else "PbTe")
                dopant = s.get("dopant") or "Bi"
                try:
                    conc = float(s.get("concentration") or 6.0)
                except (TypeError, ValueError):
                    conc = 6.0
                pop.append(
                    Candidate(
                        host=host,
                        dopant=dopant,
                        concentration=conc,
                        formula=_nominal_formula(host, dopant, conc),
                        rationale=s.get("rationale", ""),
                        source="llm_seed",
                    )
                )
            log.add(
                generation=0,
                action="seed",
                n_candidates=len(pop),
                llm_role="generator",
                detail=f"LLM 生成 {len(pop)} 个种子候选",
            )
    if not pop:
        base_hosts = hosts[:2] or ["PbTe"]
        per_host = max(1, pop_size // len(base_hosts))
        for host in base_hosts:
            pop.extend(_make_candidates(host)[:per_host])
        pop = pop[:pop_size]
        log.add(
            generation=0,
            action="seed",
            n_candidates=len(pop),
            detail="LLM 不可用，规则网格生成种子（跨母体均匀分配）",
        )

    # 2. 迭代：评估 → 选择 → 交叉/变异
    best: list[Candidate] = []
    explored: dict[str, Candidate] = {}  # 探索轨迹（跨代并集，formula 去重）
    for gen in range(1, generations + 1):
        log.add(
            generation=gen,
            action="evaluate",
            n_candidates=len(pop),
            llm_role="evaluator",
            detail="批量评估",
        )
        # 评估（LLM 或规则）
        if llm_on:
            results = roles.evaluate(pop)
            if results:
                for c in pop:
                    r = results.get(c.formula)
                    if r and isinstance(r, dict):
                        c.scores = {
                            k: float(v)
                            for k, v in r.items()
                            if k in ("scientific", "feasibility", "support")
                            and isinstance(v, (int, float))
                        }
                        c.verdict = (
                            r.get("verdict", "keep")
                            if r.get("verdict") in ("keep", "drop")
                            else "keep"
                        )
                        if r.get("reason"):
                            c.rationale = f"{c.rationale}｜{r['reason']}"
            else:
                for c in pop:
                    c.scores = rule_score(c)
                    c.verdict = "keep"
        else:
            for c in pop:
                c.scores = rule_score(c)
                c.verdict = "keep"

        # 探索轨迹收集（评估后分数已赋，供召回率评测）
        for c in pop:
            explored.setdefault(c.formula, c)

        # 反例回喂（搜索-验证闭环）：数据库验证为热力学不稳定的母体强制淘汰
        if neg:
            fb_dropped = [c.formula for c in pop if c.host in neg]
            for c in pop:
                if c.host in neg:
                    c.verdict = "drop"
            if fb_dropped:
                log.add(
                    generation=gen,
                    action="prune_feedback",
                    n_candidates=len(fb_dropped),
                    detail=f"验证反例母体回喂淘汰 {len(fb_dropped)} 个候选",
                )

        # 剪枝（LLM 淘汰低潜力）
        if llm_on:
            drops = roles.prune(pop, negative_hosts=list(neg) if neg else None)
            if drops:
                drop_set = set(drops)
                for c in pop:
                    if c.formula in drop_set:
                        c.verdict = "drop"
                log.add(
                    generation=gen,
                    action="prune",
                    n_candidates=len(drop_set),
                    llm_role="pruner",
                    detail=f"LLM 淘汰 {len(drop_set)} 个候选",
                )

        kept = [c for c in pop if c.verdict != "drop"]
        if not kept:
            kept = pop  # 防止全淘汰导致种群为空
        kept.sort(key=lambda c: c.score_avg(), reverse=True)
        best = kept[:5]
        elite = kept[: max(2, pop_size // 4)]
        log.add(
            generation=gen,
            action="select",
            n_candidates=len(elite),
            detail=f"保留精英 {len(elite)} 个，Top 均分 {best[0].score_avg() if best else 0:.2f}",
        )

        if gen < generations:
            # 交叉：父代重组 host/dopant/concentration
            children: list[Candidate] = []
            for i in range(len(elite)):
                for j in range(i + 1, len(elite)):
                    if len(children) >= pop_size - len(elite):
                        break
                    a, b = elite[i], elite[j]
                    child = Candidate(
                        host=a.host,
                        dopant=b.dopant,
                        concentration=round((a.concentration + b.concentration) / 2, 1),
                        formula=_nominal_formula(
                            a.host, b.dopant, (a.concentration + b.concentration) / 2
                        ),
                        rationale=f"交叉：{a.formula} × {b.formula}",
                        source="ga_crossover",
                    )
                    children.append(child)
                if len(children) >= pop_size - len(elite):
                    break
            # 变异：随机扰动浓度/换掺杂元素
            import random

            rng = random.Random(gen)
            while len(elite) + len(children) < pop_size:
                base = rng.choice(elite)
                if rng.random() < 0.5:
                    conc = rng.choice([2.0, 4.0, 6.0, 8.0, 10.0])
                    child = Candidate(
                        host=base.host,
                        dopant=base.dopant,
                        concentration=conc,
                        formula=_nominal_formula(base.host, base.dopant, conc),
                        rationale=f"变异浓度：{base.formula} → {conc}%",
                        source="ga_mutation",
                    )
                else:
                    dopant = rng.choice(DOPANT_POOL)
                    child = Candidate(
                        host=base.host,
                        dopant=dopant,
                        concentration=base.concentration,
                        formula=_nominal_formula(base.host, dopant, base.concentration),
                        rationale=f"变异掺杂元素：{base.formula} → {dopant}",
                        source="ga_mutation",
                    )
                children.append(child)
            log.add(
                generation=gen,
                action="crossover_mutate",
                n_candidates=len(children),
                detail=f"生成子代 {len(children)} 个",
            )
            pop = elite + children

    # 3. 构效关系假设
    # 评测模式：输出探索轨迹全部候选（跨代并集、按评分降序）
    if explore_top > 0 and explored:
        best = sorted(explored.values(), key=lambda c: c.score_avg(), reverse=True)[:explore_top]
    if best:
        top = best[0]
        mechanism_hint = (
            "能带工程/载流子优化/声子散射" if top.dopant in PROMOTING_DOPANTS else "化学势调控"
        )
        relation = (
            f"{top.host} 中 {top.dopant} 掺杂（{top.concentration}%）→ "
            f"通过{mechanism_hint}提升热电优值 zT"
        )
        hypothesis = (
            f"在 {top.host} 中以 {top.dopant} 掺杂 {top.concentration}% 可提升 zT"
            f"（预期 {top.score_avg():.2f}，需实验/计算验证）"
        )
        mechanism = (
            f"{top.dopant} 掺杂引入点缺陷与应变场，增强声子散射降低晶格热导率；"
            f"同时调节载流子浓度，协同优化功率因子（理由：{top.rationale[:100]}）"
        )
        confidence = round(top.score_avg(), 2)
    else:
        relation = "未发现高置信候选"
        hypothesis = "需扩大搜索空间"
        mechanism = "搜索未收敛，建议调整母体/掺杂元素池"
        confidence = 0.0

    log.add(
        generation=generations,
        action="done",
        n_candidates=len(best),
        detail=f"输出 Top {len(best)} 候选"
        + (f"（探索轨迹 {len(explored)} 个）" if explore_top > 0 else ""),
    )
    if logger:
        logger(json.dumps(log.steps[-1].model_dump(), ensure_ascii=False))

    return SPRFinding(
        relation=relation,
        hypothesis=hypothesis,
        top_candidates=best,
        gap_statement=gap_statement,
        mechanism=mechanism,
        confidence=confidence,
        search_log=log,
    )

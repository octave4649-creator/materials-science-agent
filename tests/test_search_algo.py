"""模块 5 扩展：SR/MCTS/BO × LLM 融合搜索测试（规则模式 + LLM 模式 + 降级）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.search_agent import SearchAgent
from src.common.llm import LLMError
from src.search.bo_search import bo_search
from src.search.ga_search import LLMRoles
from src.search.mcts_search import mcts_search
from src.search.schemas import SearchLog, SPRFinding
from src.search.sr_search import (
    DEFAULT_FORM,
    _least_squares,
    sr_search,
)


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认清空 LLM key（测试规则降级路径）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def _fake_chat(responder):
    """按 system 内容分发角色的 fake chat_json。"""

    def _chat(system: str, user: str, kw: dict) -> dict:
        if "热电材料建模专家" in system:
            return responder("form")
        if "candidates" in system and "打分" not in system and "剪枝" not in system:
            return responder("generate")
        if "打分" in system:
            return responder("evaluate")
        if "剪枝" in system:
            return responder("prune")
        return responder("unknown")

    return _chat


# ---------- 最小二乘（SR 核心） ----------


def test_least_squares_linear_exact() -> None:
    """线性数据 y=2+3x → 系数精确恢复（a=2, b=3）。"""
    xs = [1.0, 2.0, 3.0, 4.0]
    ys = [5.0, 8.0, 11.0, 14.0]
    coefs, r2 = _least_squares(xs, ys, "a + b*x")
    assert abs(coefs[0] - 2.0) < 1e-6
    assert abs(coefs[1] - 3.0) < 1e-6
    assert r2 > 0.999


def test_least_squares_singular_fallback() -> None:
    """奇异/样本不足 → 回退常数均值，不抛异常。"""
    coefs, r2 = _least_squares([1.0], [0.5], DEFAULT_FORM)
    assert coefs  # 常数均值兜底
    assert r2 == 0.0


def test_least_squares_quadratic() -> None:
    """二次数据 y=1+2x-0.5x² → 系数近似恢复。"""
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [1 + 2 * x - 0.5 * x * x for x in xs]
    coefs, r2 = _least_squares(xs, ys, DEFAULT_FORM)
    assert abs(coefs[0] - 1.0) < 1e-6
    assert abs(coefs[1] - 2.0) < 1e-6
    assert abs(coefs[2] - (-0.5)) < 1e-6
    assert r2 > 0.99


# ---------- SR 主循环 ----------


def test_sr_search_rule_mode() -> None:
    """无 LLM：规则采样 + 规则打分 + 三次多项式拟合 → 显式公式输出。"""
    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    finding = sr_search(
        gap_statement="GeTe 掺杂浓度对 zT 的影响",
        hosts=["GeTe", "PbTe"],
        roles=roles,
        n_points=12,
        llm_on=False,
    )
    assert isinstance(finding, SPRFinding)
    assert "y =" in finding.relation  # 显式公式
    assert "最优掺杂浓度" in finding.relation
    assert finding.hypothesis
    assert finding.top_candidates
    assert finding.search_log.steps
    assert not roles.log.used_llm


def test_sr_search_llm_form_proposal() -> None:
    """LLM 模式：生成器采样种子 + form 提议注入拟合。"""
    log = SearchLog()

    def responder(role: str) -> dict:
        if role == "form":
            return {"form": "a + b*x + c*x^2"}
        if role == "generate":
            return {
                "candidates": [
                    {"host": "GeTe", "dopant": "Ti", "concentration": 4.0,
                     "rationale": "能带收敛"},
                    {"host": "GeTe", "dopant": "Bi", "concentration": 8.0,
                     "rationale": "声子散射"},
                ]
            }
        if role == "evaluate":
            return {"results": {}}
        return {"drop": []}

    roles = LLMRoles(chat_json=_fake_chat(responder), log=log)
    finding = sr_search(
        gap_statement="GeTe 掺杂浓度对 zT 的影响",
        hosts=["GeTe", "PbTe"],
        roles=roles,
        n_points=8,
        llm_on=True,
    )
    assert roles.log.used_llm
    assert roles.log.llm_calls > 0
    assert "x^2" in finding.relation or "R²" in finding.relation


def test_sr_search_llm_degraded() -> None:
    """LLM 全失败 → 降级规则采样/拟合，流水线不中断。"""
    log = SearchLog()

    def boom(system: str, user: str, kw: dict) -> dict:
        raise LLMError("mock down")

    roles = LLMRoles(chat_json=boom, log=log)
    finding = sr_search(
        gap_statement="PbTe 掺杂",
        hosts=["PbTe"],
        roles=roles,
        n_points=8,
        llm_on=True,
    )
    assert log.llm_failures > 0
    assert finding.top_candidates  # 降级后仍有输出


# ---------- MCTS ----------


def test_mcts_search_rule_mode() -> None:
    """无 LLM：UCT 选择 + 规则模拟 → 收敛输出最优路径候选。"""
    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    finding = mcts_search(
        gap_statement="PbTe 掺杂 zT 提升",
        hosts=["PbTe", "GeTe"],
        roles=roles,
        iterations=40,
        llm_on=False,
    )
    assert isinstance(finding, SPRFinding)
    assert finding.top_candidates
    assert finding.confidence > 0
    assert finding.search_log.steps
    assert not roles.log.used_llm


def test_mcts_search_llm_mode() -> None:
    """LLM 模式：评估器参与叶节点模拟，审计 llm_calls>0。"""
    log = SearchLog()

    def responder(role: str) -> dict:
        if role == "evaluate":
            return {"results": {"PbTe-Ti6%": {"scientific": 0.85, "verdict": "keep"}}}
        return {"drop": []}

    roles = LLMRoles(chat_json=_fake_chat(responder), log=log)
    finding = mcts_search(
        gap_statement="PbTe 掺杂 zT 提升",
        hosts=["PbTe"],
        roles=roles,
        iterations=20,
        llm_on=True,
    )
    assert roles.log.used_llm
    assert roles.log.llm_calls > 0
    assert finding.top_candidates


def test_mcts_three_layer_tree_explores_concentration() -> None:
    """三层决策树：浓度维度真正进入树（此前固定 CONC_GRID[2]=6.0）。

    回归防护：MCTS 若浓度不入树，探索候选浓度将全部相同，无法召回
    浓度 ≠6 的期望掺杂关系（召回率评测暴露的真实缺陷）。
    """
    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    finding = mcts_search(
        gap_statement="GeTe 掺杂浓度寻优",
        hosts=["GeTe"],
        roles=roles,
        iterations=80,
        llm_on=False,
        explore_top=8,
    )
    assert len(finding.top_candidates) >= 3
    concs = {c.concentration for c in finding.top_candidates}
    assert len(concs) >= 2, f"浓度维度未进入树，探索候选浓度单一：{concs}"


def test_mcts_explore_top_default_single_best() -> None:
    """默认语义保持：explore_top=0 时仅输出单 best；>0 输出探索候选集。

    注意：SearchLog 按调用实例隔离，单测须为每次搜索创建独立 roles，
    避免共享 log 导致 steps[-1] 指向后一次调用（n_candidates 失真）。
    """
    common = {"gap_statement": "GeTe 掺杂", "hosts": ["GeTe"],
              "llm_on": False, "iterations": 40}
    single = mcts_search(
        **common, roles=LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    )
    assert len(single.top_candidates) == 1
    assert single.search_log.steps[-1].n_candidates == 1
    multi = mcts_search(
        **common, roles=LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog()),
        explore_top=5,
    )
    assert len(multi.top_candidates) == 5
    assert multi.search_log.steps[-1].n_candidates == 5


def test_mcts_expand_evaluates_all_leaves() -> None:
    """展开即评估：dopant 层一次展开全部叶子（16 dopant × 5 conc = 80 个）。

    回归防护：此前「每迭代只评估 1 个叶子」导致 explored 候选数 ≈ iterations，
    覆盖率受采样预算限制（cov 0.375 短板）；本测试断言 explore_top 输出覆盖
    全部 80 个叶子的 formula（LLM/规则先验信号传导至全叶子）。
    """
    from src.search.mcts_search import CONC_GRID, DOPANT_POOL, mcts_search

    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    finding = mcts_search(
        gap_statement="GeTe 掺杂浓度寻优",
        hosts=["GeTe"],
        roles=roles,
        iterations=5,  # 迭代数极小：若展开即评估，覆盖率不依赖迭代预算
        llm_on=False,
        explore_top=10000,
    )
    cands = finding.top_candidates
    exp_n = len(DOPANT_POOL) * len(CONC_GRID)
    # 全部叶子 formula 应被评估收录（不同 dopant×conc 组合）
    seen = {(c.dopant, c.concentration) for c in cands}
    assert len(seen) == exp_n, (
        f"展开即评估应覆盖全部 {exp_n} 个叶子组合，实际 {len(seen)}"
    )
    assert finding.search_log.steps[-1].n_candidates == exp_n


def test_mcts_llm_signal_propagates_to_leaves() -> None:
    """LLM 评估器价值信号传导至叶子排序：高分候选进入 explore_top 前列。

    回归防护：此前 LLM 只评估被 UCT 采样路径的叶子，未采样叶子无信号
    （LLM 价值信号传导不足，hit@k 低）；本测试断言 LLM 打分（known_facts
    先验匹配候选 ≥0.85）能抬升对应叶子在探索轨迹中的排序位置。
    """
    from src.search.mcts_search import mcts_search

    log = SearchLog()

    def responder(role: str) -> dict:
        if role == "evaluate":
            # 仅给期望候选打高分，其余规则兜底
            return {"results": {"Ge0.94I0.06Te": {"scientific": 0.9,
                                                  "feasibility": 0.9}}}
        return {"drop": []}

    roles = LLMRoles(chat_json=_fake_chat(responder), log=log)
    finding = mcts_search(
        gap_statement="GeTe 掺杂 I 提升 zT",
        hosts=["GeTe"],
        roles=roles,
        iterations=20,
        llm_on=True,
        explore_top=10,
    )
    assert roles.log.used_llm
    assert roles.log.llm_calls > 0
    # LLM 高分候选应排进前 10（信号传导），且分数保留
    target = next((c for c in finding.top_candidates if c.dopant == "I"), None)
    assert target is not None, "I 掺杂候选应被展开即评估收录"
    assert target.score_avg() > 0.8, f"LLM 信号未传导至 I 候选：{target.score_avg()}"


def test_explore_top_algo_consistent() -> None:
    """四算法 explore_top 口径一致：输出数 = min(explore_top, 探索候选数)。"""
    from src.search.bo_search import bo_search
    from src.search.ga_search import ga_search
    from src.search.sr_search import sr_search

    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    common = {"gap_statement": "GeTe 掺杂浓度对 zT 的影响", "hosts": ["GeTe"],
              "roles": roles, "llm_on": False, "explore_top": 5}
    for finding in (
        ga_search(**common, generations=2, pop_size=10),
        bo_search(**common),
        sr_search(**common, n_points=12),
    ):
        assert 1 <= len(finding.top_candidates) <= 5
        # 排序：候选按评分降序（explore_top 口径）
        scores = [c.score_avg() for c in finding.top_candidates]
        assert scores == sorted(scores, reverse=True)


# ---------- BO ----------


def test_bo_search_rule_mode() -> None:
    """无 LLM：初始点评估 + 二次代理 + UCB 采集 → 最优浓度输出。"""
    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    finding = bo_search(
        gap_statement="GeTe 掺杂浓度寻优",
        hosts=["GeTe"],
        roles=roles,
        llm_on=False,
    )
    assert isinstance(finding, SPRFinding)
    assert "最优浓度" in finding.relation
    assert finding.top_candidates
    assert finding.top_candidates[0].scores.get("r2_fit") is not None
    assert finding.search_log.steps


def test_bo_search_llm_evaluation() -> None:
    """LLM 模式：评估器参与初始点与采集点评分。"""
    log = SearchLog()

    def responder(role: str) -> dict:
        if role == "evaluate":
            return {"results": {"GeTe-Ti5%": {"scientific": 0.8}}}
        return {"drop": []}

    roles = LLMRoles(chat_json=_fake_chat(responder), log=log)
    finding = bo_search(
        gap_statement="GeTe 掺杂浓度寻优",
        hosts=["GeTe"],
        roles=roles,
        llm_on=True,
    )
    assert roles.log.used_llm
    assert roles.log.llm_calls > 0
    assert finding.top_candidates


def test_bo_search_dopant_dimension() -> None:
    """v2 增强：dopant 外层遍历 × 浓度 BO 内层寻优——探索轨迹覆盖多个掺杂元素。

    回归防护：v1 单 dopant 固定（仅浓度轴），召回率评测对「dopant+浓度」组合
    期望方案恒 miss；本测试断言 explore_top 输出中 dopant 维度多样性 ≥2。
    """
    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    finding = bo_search(
        gap_statement="GeTe 掺杂浓度寻优",
        hosts=["GeTe"],
        roles=roles,
        llm_on=False,
        dopants=["Ti", "Bi", "Na"],
        explore_top=10,
    )
    dopants_seen = {c.dopant for c in finding.top_candidates}
    assert len(dopants_seen) >= 2, f"dopant 维度应覆盖多个元素，实际 {dopants_seen}"
    assert len(finding.top_candidates) == 10


def test_bo_search_dopants_param_scope() -> None:
    """dopants 参数限定搜索空间：仅遍历指定掺杂元素，不越界。"""
    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    finding = bo_search(
        gap_statement="SnTe 掺杂浓度寻优",
        hosts=["SnTe"],
        roles=roles,
        llm_on=False,
        dopants=["In"],
        explore_top=20,
    )
    dopants_seen = {c.dopant for c in finding.top_candidates}
    assert dopants_seen == {"In"}
    # 默认单 best 语义保持：explore_top=0 时输出 1 个候选
    single = bo_search(
        gap_statement="SnTe 掺杂浓度寻优",
        hosts=["SnTe"],
        roles=LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog()),
        llm_on=False,
        dopants=["In", "Cd"],
    )
    assert len(single.top_candidates) == 1
    assert single.top_candidates[0].dopant in ("In", "Cd")


# ---------- SearchAgent 集成 ----------


def _gaps(tmp_path: Path) -> Path:
    """构造含 1 条 Gap 的清单。"""
    path = tmp_path / "gaps.json"
    path.write_text(
        json.dumps(
            {
                "domain": "thermoelectric",
                "gaps": [
                    {
                        "gap_type": "未探索方向",
                        "statement": "GeTe 中 Ti 掺杂浓度对 zT 的影响未被系统研究",
                        "rationale": "覆盖率分析发现空白",
                        "formulas": ["GeTe"],
                        "evidence_ids": ["doc0"],
                        "novelty": "新知",
                        "confidence": 0.8,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_search_agent_sr_mode(tmp_path: Path) -> None:
    """SearchAgent algo='sr'：消费 gaps.json → 显式公式 finding 落盘。"""
    out = tmp_path / "out"
    agent = SearchAgent(gaps_path=_gaps(tmp_path), output_dir=out)
    results = agent.run(top_n=1, pop_size=8, use_llm=False, algo="sr")
    assert len(results) == 1
    payload = json.loads(results[0].out_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
    assert "y =" in payload["relation"]
    assert payload["top_candidates"]
    assert payload["evidence_ids"] == ["doc0"]


def test_search_agent_invalid_algo(tmp_path: Path) -> None:
    """algo 非法 → ValueError。"""
    agent = SearchAgent(gaps_path=_gaps(tmp_path), output_dir=tmp_path / "out")
    with pytest.raises(ValueError):
        agent.run(use_llm=False, algo="random_forest")

"""路线 A 搜索 Agent 测试：种子生成/评估/剪枝降级、GA 收敛、审计日志、落盘。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.search_agent import SearchAgent
from src.common.llm import LLMError
from src.search.ga_search import LLMRoles, ga_search, rule_score
from src.search.schemas import Candidate, SearchLog, SPRFinding


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认清空 LLM key（测试规则降级路径）。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def _gaps(tmp_path: Path) -> Path:
    """构造含 1 条 Gap 的清单（热电：PbTe 掺杂）。"""
    path = tmp_path / "gaps.json"
    path.write_text(
        json.dumps(
            {
                "domain": "thermoelectric",
                "n_entries": 1,
                "gaps": [
                    {
                        "gap_type": "未探索方向",
                        "statement": "PbTe 中 Ti/Bi 协同掺杂对 zT 的影响未被系统研究",
                        "rationale": "覆盖率分析发现掺杂维度空白",
                        "formulas": ["PbTe", "GeTe"],
                        "evidence_ids": ["doc0"],
                        "novelty": "新知",
                        "operability": "以 PbTe 为种子搜索掺杂-性能关联",
                        "confidence": 0.8,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _mk_candidate(host: str = "PbTe", dopant: str = "Ti", conc: float = 6.0) -> Candidate:
    """构造候选。"""
    return Candidate(
        host=host,
        dopant=dopant,
        concentration=conc,
        formula=f"{host}-{dopant}{conc:.0f}%",
        rationale="test",
    )


def _fake_chat(responder):
    """构造可注入的 chat_json（支持按角色分发）。"""

    def _chat(system: str, user: str, kw: dict) -> dict:
        if "candidates" in system and "打分" not in system and "剪枝" not in system:
            return responder("generate")
        if "打分" in system:
            return responder("evaluate")
        if "剪枝" in system:
            return responder("prune")
        return responder("unknown")

    return _chat


# ---------- 规则评估 ----------


def test_rule_score_promoting_dopant() -> None:
    """文献支持掺杂元素 + 典型浓度区间 → 高分。"""
    c = _mk_candidate(dopant="Ti", conc=6.0)
    s = rule_score(c)
    assert s["scientific"] >= 0.7
    assert s["feasibility"] >= 0.7


def test_rule_score_extreme_conc() -> None:
    """非典型浓度 → 可行性分低。"""
    c = _mk_candidate(dopant="Ti", conc=10.0)
    s = rule_score(c)
    assert s["feasibility"] < 0.7


# ---------- LLM 三角色 ----------


def test_generator_degraded_on_error() -> None:
    """生成器失败 → 返回 None（调用方降级规则网格）。"""
    log = SearchLog()

    def boom(system: str, user: str, kw: dict) -> dict:
        raise LLMError("mock down")

    roles = LLMRoles(chat_json=boom, log=log)
    assert roles.generate_seeds("gap", ["PbTe"]) is None
    assert log.llm_failures == 1


def test_evaluator_parses_scores() -> None:
    """评估器解析分数与 verdict。"""
    log = SearchLog()

    def responder(role: str) -> dict:
        if role == "evaluate":
            return {
                "results": {
                    "PbTe-Ti6%": {"scientific": 0.8, "feasibility": 0.7,
                                  "support": 0.6, "verdict": "keep", "reason": "能带收敛"},
                }
            }
        return {"drop": [], "focus": "x"}

    roles = LLMRoles(chat_json=_fake_chat(responder), log=log)
    cands = [_mk_candidate()]
    results = roles.evaluate(cands)
    assert results is not None
    assert "PbTe-Ti6%" in results
    assert results["PbTe-Ti6%"]["scientific"] == 0.8  # type: ignore[union-attr]


def test_pruner_returns_drop_list() -> None:
    """剪枝器返回淘汰列表。"""
    log = SearchLog()

    def responder(role: str) -> dict:
        if role == "prune":
            return {"drop": ["PbTe-Ti6%"], "focus": "聚焦 Ti 掺杂"}
        return {"results": {}}

    roles = LLMRoles(chat_json=_fake_chat(responder), log=log)
    drops = roles.prune([_mk_candidate()])
    assert drops == ["PbTe-Ti6%"]


# ---------- GA 主循环 ----------


def test_ga_search_rule_mode() -> None:
    """无 LLM：规则网格种子 + 规则评估，仍收敛输出候选。"""
    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    finding = ga_search(
        gap_statement="PbTe 掺杂 zT 提升",
        hosts=["PbTe"],
        roles=roles,
        generations=3,
        pop_size=10,
        llm_on=False,
    )
    assert isinstance(finding, SPRFinding)
    assert len(finding.top_candidates) > 0
    assert finding.confidence > 0
    assert finding.search_log.steps, "搜索审计日志应非空"
    assert not roles.log.used_llm


def test_ga_search_llm_mode() -> None:
    """LLM 模式：生成器产种子 → 评估打分 → 剪枝淘汰，审计 llm_calls>0。"""
    log = SearchLog()

    def responder(role: str) -> dict:
        if role == "generate":
            return {
                "candidates": [
                    {"host": "PbTe", "dopant": "Ti", "concentration": 6.0,
                     "rationale": "能带收敛"},
                    {"host": "PbTe", "dopant": "Na", "concentration": 4.0,
                     "rationale": "载流子优化"},
                ]
            }
        if role == "evaluate":
            return {
                "results": {
                    "Pb0.94Ti0.06Te": {"scientific": 0.9, "feasibility": 0.8,
                                       "support": 0.7, "verdict": "keep", "reason": "好"},
                    "Pb0.96Na0.04Te": {"scientific": 0.6, "feasibility": 0.7,
                                       "support": 0.5, "verdict": "keep", "reason": "中"},
                }
            }
        if role == "prune":
            return {"drop": ["Pb0.96Na0.04Te"], "focus": "聚焦 Ti"}
        return {"drop": [], "focus": "x"}

    roles = LLMRoles(chat_json=_fake_chat(responder), log=log)
    finding = ga_search(
        gap_statement="PbTe 掺杂 zT 提升",
        hosts=["PbTe"],
        roles=roles,
        generations=2,
        pop_size=8,
        llm_on=True,
    )
    assert roles.log.used_llm
    assert roles.log.llm_calls > 0
    assert finding.top_candidates
    assert finding.top_candidates[0].scores.get("scientific", 0) >= 0.6
    # 审计：seed 动作带 generator 角色
    roles_marked = [s for s in roles.log.steps if s.llm_role == "generator"]
    assert roles_marked


# ---------- SearchAgent 端到端 ----------


def test_search_agent_rule_mode(tmp_path: Path) -> None:
    """SearchAgent：消费 gaps.json → finding 落盘 + 证据链回填。"""
    out = tmp_path / "out"
    agent = SearchAgent(gaps_path=_gaps(tmp_path), output_dir=out)
    results = agent.run(top_n=1, generations=2, pop_size=8, use_llm=False)
    assert len(results) == 1
    res = results[0]
    assert res.out_path and res.out_path.is_file()
    payload = json.loads(res.out_path.read_text(encoding="utf-8"))
    assert payload["gap_statement"].startswith("PbTe 中 Ti/Bi")
    assert payload["evidence_ids"] == ["doc0"]
    assert payload["novelty"] == "新知"
    assert payload["top_candidates"]


def test_search_agent_empty_gaps(tmp_path: Path) -> None:
    """Gap 清单为空 → 返回空列表不报错。"""
    path = tmp_path / "empty.json"
    path.write_text('{"gaps": []}', encoding="utf-8")
    agent = SearchAgent(gaps_path=path, output_dir=tmp_path / "out")
    assert agent.run(use_llm=False) == []


def test_search_agent_offset(tmp_path: Path) -> None:
    """offset 分批：跳过前 N 条 Gap，只处理后续条目。"""
    path = tmp_path / "two.json"
    path.write_text(
        json.dumps(
            {
                "gaps": [
                    {"statement": "Gap A", "formulas": ["PbTe"], "evidence_ids": []},
                    {"statement": "Gap B", "formulas": ["GeTe"], "evidence_ids": []},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    agent = SearchAgent(gaps_path=path, output_dir=tmp_path / "out")
    results = agent.run(top_n=1, offset=1, use_llm=False)
    assert len(results) == 1
    assert "Gap B" in results[0].finding.gap_statement


# ---------- known_facts 先验注入（BO/MCTS LLM 命中率归因修复） ----------


def test_known_facts_prior_empty_by_default() -> None:
    """未注入先验时 prior 段落为空串（向后兼容，既有调用不受影响）。"""
    roles = LLMRoles(chat_json=lambda s, u, k: {}, log=SearchLog())
    assert roles._known_facts_prior() == ""


def test_known_facts_prior_renders_facts() -> None:
    """注入先验后渲染 host-dopant-concentration 清单。"""
    roles = LLMRoles(
        chat_json=lambda s, u, k: {},
        log=SearchLog(),
        known_facts=[
            {"id": "kf-01", "host": "PbTe", "dopant": "Na", "concentration": 2.0},
            {"id": "kf-06", "host": "PbTe", "dopant": "I", "concentration": 1.0},
        ],
    )
    prior = roles._known_facts_prior()
    assert "PbTe 掺 Na 2%" in prior
    assert "PbTe 掺 I 1%" in prior
    assert "0.85" in prior  # 校准规则明确写出
    # 缺字段的条目跳过，不崩（无 "- xxx 掺" 列表行）
    roles2 = LLMRoles(chat_json=lambda s, u, k: {},
                      known_facts=[{"id": "x", "host": ""}])
    assert "- " not in roles2._known_facts_prior()


def test_evaluate_injects_prior_into_system_prompt() -> None:
    """evaluate 的 system prompt 实际包含先验段落（经 fake chat 捕获验证）。"""
    captured: dict[str, str] = {}

    def capture(system: str, user: str, kw: dict) -> dict:
        captured["system"] = system
        return {"results": {}}

    roles = LLMRoles(
        chat_json=capture,
        log=SearchLog(),
        known_facts=[{"id": "kf-01", "host": "PbTe", "dopant": "Na",
                      "concentration": 2.0}],
    )
    roles.evaluate([_mk_candidate()])
    assert "已知文献高效掺杂方案先验" in captured["system"]
    assert "PbTe 掺 Na 2%" in captured["system"]


def test_evaluate_prior_absent_without_facts() -> None:
    """未注入先验时 system prompt 不含先验段落（行为与旧版一致）。"""
    captured: dict[str, str] = {}

    def capture(system: str, user: str, kw: dict) -> dict:
        captured["system"] = system
        return {"results": {}}

    roles = LLMRoles(chat_json=capture, log=SearchLog())
    roles.evaluate([_mk_candidate()])
    assert "已知文献高效掺杂方案先验" not in captured["system"]

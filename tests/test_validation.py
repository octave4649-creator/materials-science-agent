"""模块 6 数据库交叉验证测试：三类判定、OQMD 解析、Agent 全流程（全部 mock，无网络）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.validation_agent import ValidationAgent, _validate_candidate
from src.validation.oqmd_client import OQMDClient
from src.validation.parent_parser import parse_integer_parent
from src.validation.schemas import DBEntry


def _fake_oqmd(best: DBEntry | None):
    """构造假 OQMD 客户端（按 host 返回固定结果）。"""

    class _Fake:
        def best_entry(self, composition: str) -> DBEntry | None:  # noqa: D102
            if best is not None and best.formula == composition:
                return best
            return None

    return _Fake()


def _cand(host: str = "PbTe", dopant: str = "Ti", conc: float = 4.0) -> dict:
    """构造候选 dict（对齐 finding JSON 结构）。"""
    return {
        "host": host,
        "dopant": dopant,
        "concentration": conc,
        "formula": f"{host}-{dopant}{conc:.0f}%",
        "rationale": "test",
        "source": "llm_seed",
        "scores": {"scientific": 0.8},
        "verdict": "keep",
    }


def _stable_pbte() -> DBEntry:
    return DBEntry(
        db="oqmd", formula="PbTe", entry_id="4061853",
        delta_e=-0.18, stability=0.02, band_gap=0.0, is_stable=True,
        source_url="https://oqmd.org/oqmdapi/formationenergy?composition=PbTe",
    )


def _stable_gete() -> DBEntry:
    return DBEntry(
        db="oqmd", formula="GeTe", entry_id="4062333",
        delta_e=-0.086, stability=0.002, band_gap=0.753, is_stable=True,
        source_url="https://oqmd.org/oqmdapi/formationenergy?composition=GeTe",
    )


# ---------- A/B 位拆分纯母体解析器（t3：验证失败项优化） ----------


def test_parent_parser_ax_type() -> None:
    """AX 型分数宿主 → 整数母体（GeTe）。"""
    assert parse_integer_parent("Ge0.93Ti0.01Bi0.06Te") == "GeTe"
    assert parse_integer_parent("Pb0.94Ti0.06Te") == "PbTe"


def test_parent_parser_a2x3_type() -> None:
    """A2X3 型合金成分 → 整数母体（Sb2Te3）。"""
    assert parse_integer_parent("Bi0.5Sb1.5Te3") == "Sb2Te3"


def test_parent_parser_failure() -> None:
    """无法解析（多掺杂 + 连接、计量型不支持）→ None。"""
    assert parse_integer_parent("Pb0.97Na+Sr0.03Te") is None
    assert parse_integer_parent("X0.5Y0.5Te2") is None
    assert parse_integer_parent("") is None
    assert parse_integer_parent("GeTe") == "GeTe"  # 整数 AX 幂等
    assert parse_integer_parent("123") is None  # 非化学式


# ---------- 三类判定 ----------


def test_verdict_known_stable_host() -> None:
    """母体在库且稳定 → 已知。"""
    r = _validate_candidate(_cand(), _fake_oqmd(_stable_pbte()), use_mp=False)
    assert r.verdict == "已知"
    assert r.novel_dopant is True  # 掺杂为库外扩展
    assert any(c.property == "stability" for c in r.checks)


def test_verdict_counterexample_unstable_host() -> None:
    """母体在库但热力学不稳定 → 反例。"""
    unstable = DBEntry(
        db="oqmd", formula="PbTe", entry_id="x",
        delta_e=0.5, stability=0.4, is_stable=False,
    )
    r = _validate_candidate(_cand(), _fake_oqmd(unstable), use_mp=False)
    assert r.verdict == "反例"


def test_verdict_novel_missing_host() -> None:
    """母体不在库 → 新知。"""
    r = _validate_candidate(_cand(host="PbSe"), _fake_oqmd(None), use_mp=False)
    assert r.verdict == "新知"


def test_verdict_failed_fractional_host() -> None:
    """分数掺杂宿主无法解析出整数母体 → 验证失败（不伪装结论）。"""
    r = _validate_candidate(_cand(host="Pb0.97Na+Sr0.03Te"), _fake_oqmd(None),
                            use_mp=False)
    assert r.verdict == "验证失败"
    assert "无法解析" in r.reason


def test_rerun_fractional_host_with_parent() -> None:
    """分数宿主解析出整数母体 → 按纯母体重验 → 已知，parent_formula 留痕。"""
    r = _validate_candidate(
        _cand(host="Ge0.93Ti0.01Bi0.06Te"), _fake_oqmd(_stable_gete()),
        use_mp=False,
    )
    assert r.verdict == "已知"
    assert r.parent_formula == "GeTe"
    assert "A/B 位拆分" in r.reason
    assert r.novel_dopant is True


# ---------- OQMD 客户端 ----------


def test_integer_composition_guard() -> None:
    """分数成分被跳过直查（防 OQMD 超时）。"""
    c = OQMDClient()
    assert c._is_integer_composition("PbTe") is True
    assert c._is_integer_composition("Pb0.94Ti0.06Te") is False


def test_oqmd_parse_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """OQMD 响应解析 → 归一化 DBEntry。"""
    c = OQMDClient()

    class _FakeResp:
        def raise_for_status(self) -> None:  # noqa: D102
            return None

        def json(self) -> dict:  # noqa: D102
            return {
                "data": [
                    {"name": "TePb", "delta_e": -0.18, "stability": 0.02,
                     "band_gap": 0.0, "formationenergy_id": 4061853},
                    {"name": "TePb", "delta_e": -0.16, "stability": 0.03,
                     "band_gap": 0.0, "formationenergy_id": 4061854},
                ]
            }

    captured: dict = {}

    def _fake_get(url: str, params: dict, timeout: float, follow_redirects: bool):
        captured["url"] = url
        captured["params"] = params
        return _FakeResp()

    monkeypatch.setattr("src.validation.oqmd_client.httpx.get", _fake_get)
    entries = c.query_formation_energy("PbTe")
    assert len(entries) == 2
    assert entries[0].db == "oqmd"
    assert entries[0].formula == "TePb"
    assert entries[0].delta_e == -0.18
    assert entries[0].is_stable is True  # stability 0.02 ≤ 0.1
    assert captured["params"]["composition"] == "PbTe"


def test_oqmd_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """网络错误 → OQMDError。"""
    c = OQMDClient()

    def _boom(url: str, params: dict, timeout: float, follow_redirects: bool):
        import httpx

        raise httpx.ConnectError("down")

    monkeypatch.setattr("src.validation.oqmd_client.httpx.get", _boom)
    with pytest.raises(Exception, match="OQMD"):
        c.query_formation_energy("PbTe")


# ---------- ValidationAgent 全流程 ----------


def _write_finding(d: Path, name: str = "finding_20260804T000000_1.json") -> Path:
    p = d / name
    p.write_text(
        json.dumps(
            {
                "gap_statement": "PbTe 掺杂 zT 提升",
                "evidence_ids": ["doc0"],
                "top_candidates": [
                    _cand("PbTe", "Ti", 4.0),
                    _cand("PbTe", "Na", 6.0),
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return p


def test_validation_agent_e2e(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agent 全流程：findings → 验证 → 落盘（OQMD 结果注入）。"""
    findings = tmp_path / "findings"
    findings.mkdir()
    _write_finding(findings)
    out = tmp_path / "validation"
    monkeypatch.setattr(
        "src.agent.validation_agent.OQMDClient",
        lambda *a, **k: _fake_oqmd(_stable_pbte()),
    )
    monkeypatch.setattr("src.agent.validation_agent.mp_available", lambda: False)
    agent = ValidationAgent(findings_dir=findings, output_dir=out)
    paths = agent.run(use_mp=False)
    assert len(paths) == 1
    payload = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert payload["source_finding"].endswith("finding_20260804T000000_1.json")
    assert payload["evidence_ids"] == ["doc0"]
    assert len(payload["results"]) == 2
    assert all(r["verdict"] == "已知" for r in payload["results"])
    assert all(r["novel_dopant"] for r in payload["results"])


def test_validation_agent_empty_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无 findings → 返回空不报错。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "out"
    monkeypatch.setattr("src.agent.validation_agent.mp_available", lambda: False)
    agent = ValidationAgent(findings_dir=empty, output_dir=out)
    assert agent.run(use_mp=False) == []

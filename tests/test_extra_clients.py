"""模块 6 可选增强路径测试：NOMAD（OPTIMADE）/ AFLOW（AFLUX）客户端（全部 mock，无网络）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

from src.validation.aflow_client import AFLOWClient, AFLOWError
from src.validation.nomad_client import NOMADClient, NOMADError, elements_from_formula


def _load_extra_check():
    """加载 scripts/run_extra_db_check.py 为模块（check_one 存在性判定）。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_extra_db_check.py"
    spec = importlib.util.spec_from_file_location("run_extra_db_check", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_extra_db_check"] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    """固定状态码与 JSON 的伪响应。"""

    def __init__(self, status_code: int = 200, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=httpx.Request("GET", "x"), response=self
            )

    def json(self):
        return self._payload


# ---------- NOMAD ----------


def test_nomad_elements_from_formula() -> None:
    """元素提取：排序去重，空输入返回空。"""
    assert elements_from_formula("GeTe") == ["Ge", "Te"]
    assert elements_from_formula("Ca5In2Sb6") == ["Ca", "In", "Sb"]
    assert elements_from_formula("ZrNiSn") == ["Ni", "Sn", "Zr"]
    assert elements_from_formula("") == []


def test_nomad_build_filter() -> None:
    """OPTIMADE filter 表达式格式。"""
    assert NOMADClient._build_filter(["Ge", "Te"]) == 'elements HAS ALL "Ge", "Te"'


def test_nomad_query_structures(monkeypatch) -> None:
    """正常查询：解析 chemical_formula_reduced / elements / id / source_url。"""
    calls: list[str] = []

    def _fake_get(url, **kwargs):
        calls.append(url)
        return _FakeResp(
            payload={
                "data": [
                    {
                        "id": "NOMAD_1",
                        "attributes": {
                            "chemical_formula_reduced": "GeTe",
                            "elements": ["Ge", "Te"],
                            "nelements": 2,
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(httpx, "get", _fake_get)
    client = NOMADClient()
    out = client.query_structures("GeTe")
    assert len(out) == 1
    assert out[0]["db"] == "nomad"
    assert out[0]["formula"] == "GeTe"
    assert out[0]["entry_id"] == "NOMAD_1"
    assert out[0]["nelements"] == 2
    assert "optimade" in calls[0]
    assert client.count_structures("GeTe") == 1


def test_nomad_query_empty(monkeypatch) -> None:
    """命中 0 条 → 空列表；count=0。"""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp(payload={"data": []}))
    client = NOMADClient()
    assert client.query_structures("GeTe") == []
    assert client.count_structures("GeTe") == 0


def test_nomad_empty_formula(monkeypatch) -> None:
    """空成分 → 直接空列表，不触发网络。"""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("不应请求网络"))
    client = NOMADClient()
    assert client.query_structures("") == []
    assert client.count_structures("  ") == 0


def test_nomad_network_failure(monkeypatch) -> None:
    """持续网络错误 → NOMADError；count 返回 None（查询失败区别于命中 0）。"""
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down"))
    )
    client = NOMADClient()
    with pytest.raises(NOMADError):
        client.query_structures("GeTe")
    assert client.count_structures("GeTe") is None


def test_nomad_4xx_no_retry(monkeypatch) -> None:
    """4xx 参数错误 → 直接抛 NOMADError（不重试）。"""
    n = {"calls": 0}

    def _fake_get(*a, **k):
        n["calls"] += 1
        return _FakeResp(status_code=400, payload={})

    monkeypatch.setattr(httpx, "get", _fake_get)
    with pytest.raises(NOMADError):
        NOMADClient().query_structures("GeTe")
    assert n["calls"] == 1


def test_nomad_cache(monkeypatch) -> None:
    """进程内缓存：重复查询不重打网络。"""
    n = {"calls": 0}

    def _fake_get(*a, **k):
        n["calls"] += 1
        return _FakeResp(payload={"data": []})

    monkeypatch.setattr(httpx, "get", _fake_get)
    client = NOMADClient()
    client.query_structures("GeTe")
    client.query_structures("GeTe")
    assert n["calls"] == 1


# ---------- AFLOW ----------


def test_aflow_matchbook() -> None:
    """matchbook 构造：species 列表 + nspecies。"""
    assert AFLOWClient._matchbook("GeTe") == "species(Ge,Te),nspecies(2)"
    assert AFLOWClient._matchbook("Mg3Sb2") == "species(Mg,Sb),nspecies(2)"
    assert AFLOWClient._matchbook("ZrNiSn") == "species(Ni,Sn,Zr),nspecies(3)"
    assert AFLOWClient._matchbook("") is None


def test_aflow_query_species(monkeypatch) -> None:
    """正常查询：DBEntry 映射（enthalpy→delta_e、Egap→band_gap、is_stable）。"""
    urls: list[str] = []

    def _fake_get(url, **kwargs):
        urls.append(url)
        return _FakeResp(
            payload=[
                {
                    "compound": "GeTe",
                    "auid": "aflow:abc123",
                    "aurl": "http://aflowlib.duke.edu/AFLOWDATA/ICSD_WEB/ABC/GeTe",
                    "enthalpy_formation_atom": -0.09,
                    "Egap": 0.75,
                    "spacegroup_relax": 225,
                }
            ]
        )

    monkeypatch.setattr(httpx, "get", _fake_get)
    client = AFLOWClient()
    out = client.query_species("GeTe")
    assert len(out) == 1
    assert out[0].db == "aflow"
    assert out[0].formula == "GeTe"
    assert out[0].entry_id == "aflow:abc123"
    assert out[0].delta_e == pytest.approx(-0.09)
    assert out[0].band_gap == pytest.approx(0.75)
    assert out[0].is_stable is True
    assert out[0].spacegroup == "225"
    assert "aflux" in urls[0]


def test_aflow_query_non_list(monkeypatch) -> None:
    """非数组响应（异常 JSON）→ 空列表。"""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp(payload={"error": "x"}))
    assert AFLOWClient().query_species("GeTe") == []


def test_aflow_empty_formula(monkeypatch) -> None:
    """空成分 → 直接空列表。"""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("不应请求网络"))
    assert AFLOWClient().query_species("") == []


def test_aflow_network_failure(monkeypatch) -> None:
    """持续网络错误 → AFLOWError；best_entry 返回 None。"""
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down"))
    )
    client = AFLOWClient()
    with pytest.raises(AFLOWError):
        client.query_species("GeTe")
    assert client.best_entry("GeTe") is None


def test_aflow_best_entry(monkeypatch) -> None:
    """best_entry 取形成焓最小者（未收录返回 None）。"""
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: _FakeResp(
            payload=[
                {"compound": "GeTe", "enthalpy_formation_atom": 0.05},
                {"compound": "GeTe", "enthalpy_formation_atom": -0.12},
            ]
        ),
    )
    client = AFLOWClient()
    best = client.best_entry("GeTe")
    assert best is not None
    assert best.delta_e == pytest.approx(-0.12)
    assert best.is_stable is True


# ---------- run_extra_db_check.check_one 存在性判定 ----------


class _FakeNOMAD:
    """假 NOMAD 客户端：n 条命中或抛错。"""

    def __init__(self, n: int | None, err: bool = False) -> None:
        self._n = n
        self._err = err

    def query_structures(self, formula: str):
        if self._err:
            from src.validation.nomad_client import NOMADError

            raise NOMADError("NOMAD 不可用（测试）")
        return [{"db": "nomad", "formula": formula} for _ in range(self._n or 0)]


class _FakeAFLOW:
    """假 AFLOW 客户端：命中/0 命中/抛错。"""

    def __init__(self, hit: bool, err: bool = False) -> None:
        self._hit = hit
        self._err = err

    def query_species(self, formula: str):
        if self._err:
            from src.validation.aflow_client import AFLOWError

            raise AFLOWError("AFLOW 不可用（测试）")
        return [{"formula": formula}] if self._hit else []

    def best_entry(self, formula: str):
        from src.validation.schemas import DBEntry

        if not self._hit:
            return None
        return DBEntry(db="aflow", formula=formula, entry_id="x", delta_e=-0.1)


def test_check_one_present_aflow_only() -> None:
    """AFLOW 命中（NOMAD 不可达）→ present：阳性证据不因另一库失联被丢弃。"""
    mod = _load_extra_check()
    rec = mod.check_one("GeTe", _FakeNOMAD(0, err=True), _FakeAFLOW(True))
    assert rec["existence"] == "present"
    assert rec["nomad_n_structures"] is None
    assert "佐证母体已知" in rec["note"]


def test_check_one_absent_both_reachable() -> None:
    """两库均可达且 0 命中 → absent（佐证新知，需双库确证）。"""
    mod = _load_extra_check()
    rec = mod.check_one("XxYy", _FakeNOMAD(0), _FakeAFLOW(False))
    assert rec["existence"] == "absent"
    assert "佐证母体新知" in rec["note"]


def test_check_one_unreachable_partial() -> None:
    """一库 0 命中、另一库不可达 → unreachable（不误判新知）。"""
    mod = _load_extra_check()
    rec = mod.check_one("XxYy", _FakeNOMAD(0, err=True), _FakeAFLOW(False))
    assert rec["existence"] == "unreachable"
    assert "留痕" in rec["note"]

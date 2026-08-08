"""AFLOW（Automatic-FLOW for Materials Discovery）AFLUX 客户端（模块 6 可选增强路径）。

对齐 `.trae/rules/03-materials-databases.md` 第 5 节：
- AFLOW REST API（AFLUX）：https://aflow.org/API/aflux/，免 Key
- 定位：晶体对称性验证（spacegroup / prototype）+ 形成焓（enthalpy_formation_atom），
  补强路线 A「晶体结构」维度的交叉验证论证

AFLUX 调用格式（F. Rose et al., Comput. Mater. Sci. 137, 362 (2017)）：
  https://aflow.org/API/aflux/?<matchbook>,<directives>
- matchbook：species(X,Y) 元素过滤 + nspecies(N) 物种数过滤
- directives：paging(n) 页码（默认 64 条/页）；format(json) 为默认输出
- 查询字符串含括号/逗号，按官方示例直接拼接 URL（httpx 不重复编码）
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx

from .schemas import DBEntry

AFLOW_BASE = "https://aflow.org/API/aflux"
TIMEOUT = 25.0
MAX_RETRIES = 2  # 服务端 5xx/超时重试（指数退避）
RETRY_BASE_DELAY = 2.0

_ELEM_RE = re.compile(r"[A-Z][a-z]?")


class AFLOWError(Exception):
    """AFLOW 查询异常。"""


class AFLOWClient:
    """AFLUX 搜索接口封装（进程内缓存）。"""

    def __init__(
        self, *, base_url: str = AFLOW_BASE, timeout: float = TIMEOUT
    ) -> None:
        """初始化。

        参数:
            base_url: AFLUX API 根地址
            timeout: 单请求超时（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cache: dict[str, list[DBEntry]] = {}

    @staticmethod
    def _matchbook(formula: str) -> str | None:
        """化学式 → AFLUX matchbook 字符串（species 列表 + 物种数）。

        参数:
            formula: 成分（如 GeTe / Mg3Sb2 / ZrNiSn）

        返回:
            "species(Ge,Te),nspecies(2)" 形式；无有效元素返回 None。
        """
        elems = sorted(set(_ELEM_RE.findall(formula or "")))
        if not elems:
            return None
        species = ",".join(elems)
        return f"species({species}),nspecies({len(elems)})"

    def query_species(self, formula: str, *, limit: int = 5) -> list[DBEntry]:
        """按成分查询 AFLOW 结构（spacegroup / 形成焓 / 带隙）。

        参数:
            formula: 成分（如 GeTe / ZrNiSn）
            limit: 返回条数上限（每页默认 64 条，取前 limit）

        返回:
            归一化 DBEntry 列表；命中 0 条返回空列表。

        异常:
            AFLOWError: 网络错误 / 非 2xx（连续重试失败）
        """
        formula = formula.strip()
        if not formula:
            return []
        matchbook = self._matchbook(formula)
        if matchbook is None:
            return []
        cached = self._cache.get(formula)
        if cached is not None:
            return cached
        # 实测：AFLUX 需在 URL 中显式请求字段，否则 enthalpy_formation_atom/Egap 返回 None
        url = f"{self.base_url}/?enthalpy_formation_atom,Egap,{matchbook},paging(1)"
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.get(url, timeout=self.timeout, follow_redirects=True)
                resp.raise_for_status()
                data = resp.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and 400 <= exc.response.status_code < 500
                ):
                    raise AFLOWError(f"AFLOW 查询失败（{formula}）: {exc}") from exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (2**attempt))
        else:
            raise AFLOWError(f"AFLOW 查询失败（{formula}）: {last_exc}") from last_exc
        entries = self._normalize(formula, data, matchbook)
        self._cache[formula] = entries
        return entries

    def best_entry(self, formula: str) -> DBEntry | None:
        """取最稳定条目（min 形成焓；无焓时取第一条）。"""
        try:
            entries = self.query_species(formula)
        except AFLOWError:
            return None
        if not entries:
            return None
        return min(
            entries,
            key=lambda e: (
                e.delta_e if e.delta_e is not None else 1e9,
                e.band_gap if e.band_gap is not None else 1e9,
            ),
        )

    def _normalize(self, comp: str, data: Any, matchbook: str) -> list[DBEntry]:
        """AFLUX 响应 → DBEntry 列表。

        实测响应为 dict（键 "N of Total"，值含 compound/spacegroup_relax/
        enthalpy_formation_atom/Egap 等字段）；兼容 list 形态兜底。
        """
        if isinstance(data, dict):
            items = list(data.values())
        elif isinstance(data, list):
            items = data
        else:
            return []
        out: list[DBEntry] = []
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            enthalpy = item.get("enthalpy_formation_atom")
            band_gap = item.get("Egap")
            spacegroup = item.get("spacegroup_relax")
            out.append(
                DBEntry(
                    db="aflow",
                    formula=item.get("compound") or comp,
                    entry_id=str(item.get("auid") or ""),
                    delta_e=float(enthalpy) if isinstance(enthalpy, (int, float)) else None,
                    stability=None,  # AFLOW 不提供 hull，仅形成焓
                    band_gap=float(band_gap) if isinstance(band_gap, (int, float)) else None,
                    is_stable=(
                        float(enthalpy) < 0.0
                        if isinstance(enthalpy, (int, float)) else None
                    ),
                    spacegroup=(
                        str(spacegroup) if spacegroup not in (None, "") else None
                    ),
                    source_url=(
                        item.get("aurl")
                        or f"{self.base_url}/?enthalpy_formation_atom,Egap,{matchbook},paging(1)"
                    ),
                )
            )
        return out[:5]

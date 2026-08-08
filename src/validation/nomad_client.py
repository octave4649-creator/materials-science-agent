"""NOMAD（Novel Materials Discovery）OPTIMADE 客户端（模块 6 可选增强路径）。

对齐 `.trae/rules/03-materials-databases.md` 第 4 节：
- NOMAD 遵循 OPTIMADE 标准化访问协议，访问 https://nomad-lab.eu/prod/optimade/v1
- 免 Key 公开访问，原始数据可复现
- 定位：原始数据「存在性」证据 + 结构计数（NOMAD structures 端点不提供 hull，
  不参与稳定性判定，仅作存在性交叉验证，补强路线 A 可信性论证）

已知限制（exp.md 经验记录）：
- 用元素集合过滤（elements HAS ALL）而非化学计量精确匹配——OPTIMADE reduced
  formula 要求元素字母序（ZrNiSn → NiSnZr），精确匹配易失配；元素级更稳
- 命中含目标元素的全部结构（多种化学计量），计数即存在性证据
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx

NOMAD_BASE = "https://nomad-lab.eu/prod/optimade/v1"
TIMEOUT = 20.0
MAX_RETRIES = 2  # 服务端 5xx/超时重试（指数退避）
RETRY_BASE_DELAY = 2.0

_ELEM_RE = re.compile(r"[A-Z][a-z]?")


class NOMADError(Exception):
    """NOMAD 查询异常。"""


def elements_from_formula(formula: str) -> list[str]:
    """化学式 → 排序去重元素列表（如 Ca5In2Sb6 → [Ca, In, Sb]）。"""
    elems = _ELEM_RE.findall(formula or "")
    return sorted(set(elems))


class NOMADClient:
    """NOMAD OPTIMADE structures 端点封装（进程内缓存）。"""

    def __init__(
        self, *, base_url: str = NOMAD_BASE, timeout: float = TIMEOUT
    ) -> None:
        """初始化。

        参数:
            base_url: OPTIMADE API 根地址
            timeout: 单请求超时（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cache: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _build_filter(elements: list[str]) -> str:
        """元素列表 → OPTIMADE filter 表达式。"""
        quoted = ", ".join(f'"{e}"' for e in elements)
        return f"elements HAS ALL {quoted}"

    def query_structures(
        self, formula: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        """按成分查询 NOMAD 结构（元素级过滤）。

        参数:
            formula: 成分（如 GeTe / ZrNiSn）
            limit: 返回条数上限

        返回:
            命中结构摘要列表；命中 0 条返回空列表。

        异常:
            NOMADError: 网络错误 / 非 2xx（连续重试失败）
        """
        formula = formula.strip()
        if not formula:
            return []
        cached = self._cache.get(formula)
        if cached is not None:
            return cached
        elements = elements_from_formula(formula)
        if not elements:
            return []
        last_exc: Exception | None = None
        resp: httpx.Response | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.get(
                    f"{self.base_url}/structures",
                    params={
                        "filter": self._build_filter(elements),
                        "page_limit": limit,
                    },
                    timeout=self.timeout,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                # 网络被拦截/站点返回 HTML 时 json 解析失败，给出可读提示
                if isinstance(exc, ValueError) and (
                    resp is not None
                    and (resp.text or "").lstrip().startswith("<")
                ):
                    raise NOMADError(
                        f"NOMAD 查询失败（{formula}）: 站点返回非 JSON（HTML），"
                        "可能网络拦截或 OPTIMADE 端点不可用"
                    ) from exc
                last_exc = exc
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and 400 <= exc.response.status_code < 500
                ):
                    raise NOMADError(f"NOMAD 查询失败（{formula}）: {exc}") from exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (2**attempt))
        else:
            raise NOMADError(f"NOMAD 查询失败（{formula}）: {last_exc}") from last_exc
        structures = self._normalize(formula, data)
        self._cache[formula] = structures
        return structures

    def count_structures(self, formula: str) -> int | None:
        """库中存在性计数（None 表示查询失败，区别于命中 0 条）。"""
        try:
            return len(self.query_structures(formula))
        except NOMADError:
            return None

    def _normalize(self, comp: str, data: Any) -> list[dict[str, Any]]:
        """OPTIMADE 响应 → 结构摘要列表。"""
        items = (data or {}).get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        out: list[dict[str, Any]] = []
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            attrs = item.get("attributes") or {}
            out.append(
                {
                    "db": "nomad",
                    "formula": attrs.get("chemical_formula_reduced") or comp,
                    "entry_id": str(item.get("id") or ""),
                    "elements": attrs.get("elements") or [],
                    "nelements": attrs.get("nelements"),
                    "source_url": (
                        f"{self.base_url}/structures?filter="
                        f"{self._build_filter(elements_from_formula(comp))}"
                    ),
                }
            )
        return out

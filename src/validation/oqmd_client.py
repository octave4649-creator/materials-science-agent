"""OQMD（Open Quantum Materials Database）REST 客户端。

开放 API 免 Key（对齐 `.trae/rules/03-materials-databases.md` 第 3 节），
作为模块 6 主验证路径；MP（需 Key）为增强路径（见 mp_client.py）。

已知限制（exp.md 经验记录）：
- 分数掺杂成分（如 Pb0.94Ti0.06Te）查询易超时，本客户端仅查询整数成分
  （母体 host），掺杂方案通过 novel_dopant 标记表达「库外扩展」。
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from .schemas import DBEntry

OQMD_BASE = "https://oqmd.org/oqmdapi"
TIMEOUT = 15.0
STABILITY_THRESHOLD = 0.1  # energy above hull (eV/atom) 稳定性阈值

# 命中整数成分（含小数点的分数成分不直接查询，避免 OQMD 超时）
_FRACTION_RE = re.compile(r"\d\.\d")


class OQMDError(Exception):
    """OQMD 查询异常。"""


class OQMDClient:
    """OQMD formationenergy 接口封装（进程内缓存）。"""

    def __init__(self, *, base_url: str = OQMD_BASE, timeout: float = TIMEOUT) -> None:
        """初始化。

        参数:
            base_url: OQMD API 根地址
            timeout: 单请求超时（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cache: dict[str, list[DBEntry]] = {}

    @staticmethod
    def _is_integer_composition(comp: str) -> bool:
        """成分是否整数化学计量（分数成分查询 OQMD 易超时）。"""
        return not _FRACTION_RE.search(comp)

    def query_formation_energy(self, composition: str, *, limit: int = 3) -> list[DBEntry]:
        """按成分查询形成能/稳定性。

        参数:
            composition: 成分（如 PbTe / GeTe / Bi2Te3）
            limit: 返回条数上限

        返回:
            归一化 DBEntry 列表；成分命中 0 条返回空列表。

        异常:
            OQMDError: 网络错误 / 非 2xx
        """
        comp = composition.strip()
        if not comp:
            return []
        if not self._is_integer_composition(comp):
            # 分数成分不直查：返回空（调用方走母体验证路径）
            return []
        cached = self._cache.get(comp)
        if cached is not None:
            return cached
        try:
            resp = httpx.get(
                f"{self.base_url}/formationenergy",
                params={"composition": comp, "limit": limit},
                timeout=self.timeout,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OQMDError(f"OQMD 查询失败（{comp}）: {exc}") from exc
        entries = self._normalize(comp, data)
        self._cache[comp] = entries
        return entries

    def best_entry(self, composition: str) -> DBEntry | None:
        """取最稳定条目（min stability；无 stability 时 min delta_e）。

        返回 None 表示成分未收录或不可查询。
        """
        try:
            entries = self.query_formation_energy(composition)
        except OQMDError:
            return None
        if not entries:
            return None
        return min(
            entries,
            key=lambda e: (
                e.stability if e.stability is not None else 1e9,
                e.delta_e if e.delta_e is not None else 1e9,
            ),
        )

    def is_stable(self, composition: str) -> bool | None:
        """成分是否热力学稳定（hull 距离 < 阈值且形成能 < 0）。

        返回 None 表示无法判定（未收录/查询失败）。
        """
        entry = self.best_entry(composition)
        if entry is None:
            return None
        hull = entry.stability if entry.stability is not None else 0.0
        delta_e = entry.delta_e if entry.delta_e is not None else 0.0
        return hull <= STABILITY_THRESHOLD and delta_e < 0

    def _normalize(self, comp: str, data: Any) -> list[DBEntry]:
        """OQMD 响应 → DBEntry 列表。"""
        raw = (data or {}).get("data") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return []
        out: list[DBEntry] = []
        for item in raw[:10]:
            if not isinstance(item, dict):
                continue
            stability = item.get("stability")
            delta_e = item.get("delta_e")
            band_gap = item.get("band_gap")
            out.append(
                DBEntry(
                    db="oqmd",
                    formula=item.get("name") or comp,
                    entry_id=str(item.get("formationenergy_id") or item.get("entry_id") or ""),
                    delta_e=float(delta_e) if isinstance(delta_e, (int, float)) else None,
                    stability=float(stability) if isinstance(stability, (int, float)) else None,
                    band_gap=float(band_gap) if isinstance(band_gap, (int, float)) else None,
                    is_stable=(
                        float(stability) <= STABILITY_THRESHOLD
                        if isinstance(stability, (int, float)) else None
                    ),
                    source_url=(
                        f"{self.base_url}/formationenergy?composition={comp}&limit=10"
                    ),
                )
            )
        # 稳定性排序去重（按 formula+delta_e）
        seen: set[tuple[str, float | None]] = set()
        unique: list[DBEntry] = []
        for e in sorted(out, key=lambda e: e.stability if e.stability is not None else 1e9):
            key = (e.formula, e.delta_e)
            if key in seen:
                continue
            seen.add(key)
            unique.append(e)
        return unique[:3]

"""Sciverse API 封装：语义检索 / 结构化检索 / 原文读取 / 字段枚举。

原则（00-project-rules.md 5.1）：
- token 从环境变量 / 凭据文件解析，禁止硬编码、禁止入库
- 检索结果缓存到 data/cache/，避免重复调用消耗配额
- 网络/API 错误 try/except 包裹，抛出统一 SciverseError 供上层降级
- 证据链记录由上层（RetrievalAgent）负责，本类只返回原始结果 + 调用元信息
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sciverse import AgentToolsClient

from src.common.config import CACHE_DIR, sciverse_base_url, sciverse_token


class SciverseError(Exception):
    """Sciverse 调用失败（未配置 token / 网络错误 / 接口异常）。"""


class SciverseClient:
    """对 AgentToolsClient 的轻封装：缓存 + 统一错误 + 调用元信息。"""

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        cache_dir: Path = CACHE_DIR,
    ) -> None:
        self._token = token or sciverse_token()
        self._base_url = base_url or sciverse_base_url()
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 对外接口 ----------

    async def semantic_search(
        self, query: str, top_k: int = 10, mode: str = "balanced"
    ) -> dict[str, Any]:
        """语义证据检索（agentic-search）：自然语言找可引用证据片段。

        mode: fast(关键词~200ms) / balanced(混合~600ms，默认) / quality(LLM 改写~2-4s)
        """
        return await self._cached_call(
            "semantic_search", query=query, top_k=top_k, mode=mode
        )

    async def search_papers(self, query: str, **filters: Any) -> dict[str, Any]:
        """结构化元数据检索（meta-search）：按年份/期刊/作者等精确过滤。

        常用 filters：year_from / year_to / journals / authors / subjects /
        title_contains / sort_by_year / page / page_size
        """
        kwargs = {"query": query, **filters}
        return await self._cached_call("search_papers", **kwargs)

    async def read_content(
        self, doc_id: str, offset: int = 0, limit: int = 4096
    ) -> dict[str, Any]:
        """原文片段读取（content）：按字节区间回读，防止只看 snippet 下结论。"""
        return await self._cached_call(
            "read_content", doc_id=doc_id, offset=offset, limit=limit
        )

    async def list_catalog(self) -> dict[str, Any]:
        """字段 introspection（meta-catalog）：Agent 接入第一步，防编造字段。"""
        return await self._cached_call("list_catalog")

    # ---------- 内部实现 ----------

    def _cache_key(self, method: str, **kwargs: Any) -> str:
        """根据方法名 + 稳定参数生成缓存键。"""
        payload = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"{method}_{digest}"

    def _load_cache(self, key: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _save_cache(self, key: str, data: dict[str, Any]) -> None:
        path = self.cache_dir / f"{key}.json"
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass  # 缓存写失败不影响主流程

    async def _call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        """实际调用 SDK；token 缺失与网络错误统一转 SciverseError。"""
        if not self._token:
            raise SciverseError(
                "未配置 Sciverse token：请设置 SCIVERSE_API_TOKEN 环境变量"
                "或运行 `sciverse auth login`。"
            )
        try:
            async with AgentToolsClient(token=self._token, base_url=self._base_url) as c:
                fn = getattr(c, method)
                return await fn(**kwargs)
        except ValueError as exc:
            raise SciverseError(f"Sciverse 参数错误（{method}）：{exc}") from exc
        except Exception as exc:  # 网络/超时/服务端错误统一收敛
            raise SciverseError(f"Sciverse 调用失败（{method}）：{exc}") from exc

    async def _cached_call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        """缓存优先的调用：命中缓存直接返回，未命中调用后落盘。"""
        key = self._cache_key(method, **kwargs)
        if (cached := self._load_cache(key)) is not None:
            return cached
        result = await self._call(method, **kwargs)
        self._save_cache(key, result)
        return result

"""SciverseClient 封装单测：mock SDK，验证缓存 / 错误处理 / 调用透传。"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

import src.retrieval.sciverse_client as mod
from src.retrieval.sciverse_client import SciverseClient, SciverseError


class FakeAgentToolsClient:
    """替身：记录调用并返回预设结果，不触碰网络。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "FakeAgentToolsClient":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def semantic_search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("semantic_search", kwargs))
        return {"hits": [{"doc_id": "d1", "title": "Paper One"}]}

    async def search_papers(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search_papers", kwargs))
        return {"results": [], "total_count": 0}


def _client(tmp_path, **overrides) -> SciverseClient:
    return SciverseClient(token="sv-test", base_url="http://fake", cache_dir=tmp_path, **overrides)


def test_semantic_search_passthrough(monkeypatch, tmp_path) -> None:
    """semantic_search 透传到 SDK 并返回结果。"""
    monkeypatch.setattr(mod, "AgentToolsClient", FakeAgentToolsClient)
    client = _client(tmp_path)
    result = asyncio.run(client.semantic_search("query", top_k=3, mode="fast"))
    assert result["hits"][0]["doc_id"] == "d1"


def test_caching_avoids_duplicate_calls(monkeypatch, tmp_path) -> None:
    """相同参数第二次调用命中缓存，不再次请求 SDK。"""
    monkeypatch.setattr(mod, "AgentToolsClient", FakeAgentToolsClient)
    client = _client(tmp_path)
    asyncio.run(client.semantic_search("q"))
    asyncio.run(client.semantic_search("q"))
    # 缓存层不实例化 SDK，无法直接读 calls；改为用计数替身
    calls: list[str] = []

    class CountingClient(FakeAgentToolsClient):
        async def semantic_search(self, **kwargs: Any) -> dict[str, Any]:
            calls.append("x")
            return {"hits": []}

    monkeypatch.setattr(mod, "AgentToolsClient", CountingClient)
    asyncio.run(client.semantic_search("q2"))
    asyncio.run(client.semantic_search("q2"))
    assert len(calls) == 1  # 第二次命中缓存


def test_missing_token_raises(monkeypatch, tmp_path) -> None:
    """未配置 token 时抛出 SciverseError 而非底层 ValueError。"""
    monkeypatch.setattr(mod, "AgentToolsClient", FakeAgentToolsClient)
    # 屏蔽真实凭据文件兜底（~/.sciverse/credentials.json），确保走未配置分支
    monkeypatch.setattr("src.retrieval.sciverse_client.sciverse_token", lambda: None)
    client = SciverseClient(token="", base_url="http://fake", cache_dir=tmp_path)
    with pytest.raises(SciverseError):
        asyncio.run(client.semantic_search("q"))


def test_search_papers_passes_filters(monkeypatch, tmp_path) -> None:
    """结构化检索过滤器原样透传。"""
    captured: dict[str, Any] = {}

    class CaptureClient(FakeAgentToolsClient):
        async def search_papers(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"results": []}

    monkeypatch.setattr(mod, "AgentToolsClient", CaptureClient)
    client = _client(tmp_path)
    asyncio.run(client.search_papers("thermo", year_from=2023, page_size=5))
    assert captured["query"] == "thermo"
    assert captured["year_from"] == 2023
    assert captured["page_size"] == 5

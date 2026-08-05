"""LLM 统一接入层测试：无 key 时行为正确（不真实调用网络）。"""
from __future__ import annotations

import json

import pytest

from src.common import llm
from src.common.llm import LLMNotConfiguredError, llm_available, llm_chat_json


@pytest.fixture(autouse=True)
def _no_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有测试均清空 LLM key，避免污染外部环境。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def test_llm_available_false_without_key() -> None:
    """无 key 时 llm_available 返回 False。"""
    assert llm_available() is False


def test_llm_chat_json_raises_without_key() -> None:
    """无 key 时调用抛 LLMNotConfiguredError。"""
    with pytest.raises(LLMNotConfiguredError, match="未配置 LLM API Key"):
        llm_chat_json("sys", "user")


def test_llm_available_true_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置 key 后 llm_available 返回 True。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    assert llm_available() is True


def test_model_name_default() -> None:
    """默认模型名可读取。"""
    assert isinstance(llm.model_name(), str)


def test_chat_json_params_dict_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三位置调用约定：(system, user, {"max_tokens": N, "temperature": T})。

    回归防护：LLMRoles（模块 5）按此契约调用 llm_chat_json，
    曾因 `params` 未声明导致每次调用抛 TypeError、LLM 全量降级。
    """
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    captured: dict = {}

    class _FakeResp:
        def raise_for_status(self) -> None:  # noqa: D102
            return None

        def json(self) -> dict:  # noqa: D102
            return {"choices": [{"message": {"content": json.dumps({"ok": 1})}}]}

    def _fake_post(url: str, json: dict, headers: dict, timeout: float) -> _FakeResp:
        captured["url"] = url
        captured["payload"] = json
        return _FakeResp()

    monkeypatch.setattr(llm.httpx, "post", _fake_post)
    result = llm_chat_json("sys", "user", {"max_tokens": 10, "temperature": 0.1})
    assert result == {"ok": 1}
    assert captured["payload"]["max_tokens"] == 10
    assert captured["payload"]["temperature"] == 0.1

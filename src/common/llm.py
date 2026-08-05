"""LLM 统一接入层。

对接 OpenAI 兼容 Chat Completions 接口（可配置 base_url 指向任意兼容服务）。
密钥走环境变量，禁止硬编码（00-project-rules.md 9.3）。
未配置 key 时抛 LLMNotConfiguredError，由上层降级（规则式抽取）而非崩溃。
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .config import _load_env

# 默认模型（可通过 LLM_MODEL 覆盖）
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 60.0


class LLMError(Exception):
    """LLM 调用异常基类。"""


class LLMNotConfiguredError(LLMError):
    """未配置 LLM API Key。"""


def _llm_config() -> tuple[str, str, str]:
    """读取 LLM 配置（api_key / base_url / model）。

    兼容 OPENAI_API_KEY / LLM_API_KEY / DEEPSEEK_API_KEY 三个变量名
    （对齐 sciverse_token 的双变量名兼容先例，见 exp.md）。
    使用 DeepSeek key 且未显式指定端点时，默认走 DeepSeek 官方接口。
    """
    _load_env()
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    use_deepseek = not api_key and bool(os.getenv("DEEPSEEK_API_KEY"))
    if use_deepseek:
        api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = (os.getenv("LLM_BASE_URL") or "").rstrip("/") or (
        "https://api.deepseek.com/v1" if use_deepseek else DEFAULT_BASE_URL
    )
    model = os.getenv("LLM_MODEL") or (
        "deepseek-chat" if use_deepseek else DEFAULT_MODEL
    )
    return api_key, base_url, model


def llm_chat_json(
    system_prompt: str,
    user_prompt: str,
    params: dict[str, Any] | None = None,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """调用 LLM 并解析 JSON 输出。

    参数:
        system_prompt: 系统提示（含 schema 约束）
        user_prompt: 用户提示（含待抽取原文片段）
        params: 可选参数字典（兼容 `(system, user, {"max_tokens": ...})` 三位置调用约定）
        max_tokens: 输出最大 token 数
        temperature: 采样温度（抽取任务建议低温）

    返回:
        解析后的 JSON dict。

    异常:
        LLMNotConfiguredError: 未配置 API Key
        LLMError: 网络错误 / 非 2xx / JSON 解析失败
    """
    if params:
        max_tokens = int(params.get("max_tokens", max_tokens))
        temperature = float(params.get("temperature", temperature))
    api_key, base_url, model = _llm_config()
    if not api_key:
        raise LLMNotConfiguredError(
            "未配置 LLM API Key（LLM_API_KEY / OPENAI_API_KEY），"
            "抽取将降级为规则式抽取。详见 .trae/rules/exp.md"
        )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPError as exc:  # 网络层错误
        raise LLMError(f"LLM 调用网络错误: {exc}") from exc
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise LLMError(f"LLM 响应结构异常: {exc}") from exc
    # 解析 JSON（兼容直接 JSON 与 ```json 围栏包裹）
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            start = content.index("{")
            end = content.rindex("}") + 1
            return json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM 输出非合法 JSON: {content[:200]}") from exc


def llm_available() -> bool:
    """LLM 是否可用（用于上层选择抽取路径）。"""
    _load_env()
    return bool(
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
    )


def model_name() -> str:
    """当前模型名（审计用）。"""
    return _llm_config()[2]

"""LLM 接入快速验证：确认 llm.py 可调通 DeepSeek 并返回 JSON。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.llm import llm_available, llm_chat_json, model_name

if __name__ == "__main__":
    print(f"model: {model_name()}")
    print(f"llm_available: {llm_available()}")
    result = llm_chat_json(
        "Reply with JSON only.",
        'Return {"ok": true, "echo": "hello"}',
        max_tokens=64,
    )
    print("result:", result)

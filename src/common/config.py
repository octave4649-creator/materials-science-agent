"""配置管理：统一从环境变量 / .env 读取密钥与端点。

安全红线（00-project-rules.md 9.3）：密钥禁止硬编码、禁止入库，一律走环境变量。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

# 项目根目录（src/common/config.py -> 向上两级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = PROJECT_ROOT / "results" / "logs"
RESULTS_DIR = PROJECT_ROOT / "results"

_loaded = False


def _load_env() -> None:
    """惰性加载项目根目录 .env（不覆盖已有环境变量）。"""
    global _loaded
    if _loaded:
        return
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    _loaded = True


def sciverse_token() -> str | None:
    """Sciverse token：兼容 SCIVERSE_API_TOKEN / SCIVERSE_API_KEY 两个变量名。

    优先级：环境变量 > `sciverse auth login` 保存的凭据文件（~/.sciverse/credentials.json）。
    注意：SDK 官方变量名是 SCIVERSE_API_TOKEN，技能文档写 SCIVERSE_API_KEY，
    两个都读取可避免配置混乱（详见 exp.md 经验记录）。
    """
    _load_env()
    token = os.getenv("SCIVERSE_API_TOKEN") or os.getenv("SCIVERSE_API_KEY")
    if token:
        return token
    # 兜底：读取 CLI `sciverse auth login` 保存的凭据
    creds_path = Path.home() / ".sciverse" / "credentials.json"
    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
        return creds.get("token")
    except (OSError, json.JSONDecodeError):
        return None


def sciverse_base_url() -> str:
    """Sciverse API endpoint，默认官方地址。"""
    _load_env()
    return os.getenv("SCIVERSE_BASE_URL", "https://api.sciverse.space")


def mp_api_key() -> str | None:
    """Materials Project API Key（模块 6 使用）。"""
    _load_env()
    return os.getenv("MP_API_KEY")

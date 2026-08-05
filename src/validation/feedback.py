"""搜索-验证闭环：从验证产物提取搜索反馈（模块 5 ↔ 模块 6 迭代）。

对齐 `.trae/rules/05-route-a-SPR.md` 4.2 搜索循环第 4 步——
「LLM 分析搜索反馈 → 剪枝/聚焦搜索空间」：数据库验证结果（反例母体、
跨库分歧）回喂搜索剪枝器，形成「搜索 → 验证 → 反馈 → 再搜索」迭代闭环。

- 反例母体（在库但热力学不稳定）→ 搜索剪枝黑名单，后续搜索不再以其为宿主
- 跨库分歧（OQMD 稳定 vs MP 不稳定）→ 触发 MP 相图级核对（相图脚本另行调用）
"""
from __future__ import annotations

import json
from pathlib import Path


def extract_negative_hosts(validation_dir: str | Path) -> list[str]:
    """提取反例母体（母体在库但热力学不稳定）→ 搜索剪枝黑名单。

    参数:
        validation_dir: 验证产物目录（results/validation/）

    返回:
        去重后的反例母体列表（如 ["SiGe", "Cu2Se"]）。
    """
    d = Path(validation_dir)
    neg: list[str] = []
    seen: set[str] = set()
    for f in sorted(d.glob("validation_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for r in data.get("results", []):
            if r.get("verdict") != "反例":
                continue
            host = str(r.get("host") or "").strip()
            if host and host not in seen:
                seen.add(host)
                neg.append(host)
    return neg


def extract_disputes(validation_dir: str | Path) -> list[dict]:
    """提取跨库分歧（OQMD 与 MP 稳定性冲突）→ 供相图级核对。

    返回:
        [{"host", "candidate_formula", "oqmd_stable", "mp_stable"}]，
        仅含 entries 同时覆盖 OQMD 与 MP 且判定冲突的记录。
    """
    d = Path(validation_dir)
    disputes: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for f in sorted(d.glob("validation_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for r in data.get("results", []):
            oqmd_flags = [
                e.get("is_stable") for e in r.get("entries", [])
                if isinstance(e, dict) and e.get("db") == "oqmd"
                and e.get("is_stable") is not None
            ]
            mp_flags = [
                e.get("is_stable") for e in r.get("entries", [])
                if isinstance(e, dict) and e.get("db") == "mp"
                and e.get("is_stable") is not None
            ]
            if not oqmd_flags or not mp_flags:
                continue
            oqmd_stable = any(bool(x) for x in oqmd_flags)
            mp_stable = any(bool(x) for x in mp_flags)
            if oqmd_stable == mp_stable:
                continue
            host = str(r.get("host") or "").strip()
            cand = str(r.get("candidate_formula") or "").strip()
            key = (host, cand)
            if key in seen:
                continue
            seen.add(key)
            disputes.append(
                {
                    "host": host,
                    "candidate_formula": cand,
                    "oqmd_stable": oqmd_stable,
                    "mp_stable": mp_stable,
                }
            )
    return disputes

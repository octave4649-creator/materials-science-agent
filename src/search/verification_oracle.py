"""路线 A：基于数据库验证真值的严苛评分代理（VerificationOracle）。

背景（模块 5 阶段 4 消融公平性修复）：
原三臂消融中 full 臂用 LLM 评估器、rule 臂用规则评估器，best_score 分数来源不同、
不可直接对比，导致 LLM 融合增益失真。本模块加载 `results/validation/` 的真实
OQMD/MP 验证结果构建真值表，为三臂候选提供**同一把尺子**的严苛评分：
- 反例（母体在库但不稳定）→ 显著低分（0.15）
- 已知（母体在库且稳定）→ 高分（0.85）
- 新知（库外假设）→ 中等分（0.60，新颖性保留）
- 验证失败（分数掺杂直查失败）→ 如实低分（0.45）
- 未命中（消融候选不在验证表）→ 母体级回退匹配

对齐 `.trae/rules/05-route-a-SPR.md`：数据库交叉验证结果应反哺搜索评估，
而非只在终点验证。评分仍为 0-1 三维（scientific/feasibility/support），
与 Candidate.score_avg 契约一致。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.search.ga_search import PROMOTING_DOPANTS, Candidate

# 判定 → 母体稳定性基准分（严苛尺子的核心）
VERDICT_STABILITY = {
    "已知": 0.85,      # 母体在库且热力学稳定
    "新知": 0.60,      # 库外假设：新颖但缺乏数据库支撑
    "验证失败": 0.45,  # 无法直查：诚实低分，不伪装
    "反例": 0.15,      # 母体在库但不稳定：严苛惩罚
}
# 判定 → 文献/数据支撑度
VERDICT_SUPPORT = {
    "已知": 0.90,
    "新知": 0.60,
    "验证失败": 0.40,
    "反例": 0.20,
}
# 母体级判定优先级（同母体多条记录时高者覆盖：已知=存在稳定相最可靠）
VERDICT_PRIORITY = {"已知": 3, "反例": 2, "新知": 2, "验证失败": 1}
_UNKNOWN_STABILITY = 0.35  # 未命中且母体未知时的保守分
_HOST_STABLE = 0.80        # 未命中但母体在库且稳定


@dataclass
class OracleVerdict:
    """候选在真值表中的命中信息。"""

    formula: str
    verdict: str = "未知"
    host: str = ""
    host_stable: bool | None = None


class VerificationOracle:
    """加载 validation_*.json 构建真值表，对候选评分（无网络，纯本地查找）。"""

    def __init__(self, validation_dir: str | Path | None = None) -> None:
        self._formula_table: dict[str, OracleVerdict] = {}
        self._host_table: dict[str, OracleVerdict] = {}
        if validation_dir:
            self.load(validation_dir)

    # ---------- 构建 ----------
    def load(self, validation_dir: str | Path) -> int:
        """扫描目录下全部 validation_*.json，索引每个候选与其母体判定。

        返回索引的候选结果数。
        """
        d = Path(validation_dir)
        n = 0
        for f in sorted(d.glob("validation_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for r in data.get("results", []):
                formula = str(r.get("candidate_formula") or "").strip()
                host = str(r.get("host") or "").strip()
                verdict = str(r.get("verdict") or "未知")
                if not formula:
                    continue
                host_stable = self._parse_host_stable(r)
                v = OracleVerdict(
                    formula=formula, verdict=verdict,
                    host=host, host_stable=host_stable,
                )
                self._formula_table[formula] = v
                # 母体表按判定优先级覆盖（已知=存在稳定相最可靠，防低质量记录污染）
                # host 与 parent_formula（A/B 位拆分解析出的整数母体）一并索引，
                # 让重验结果覆盖更广（如 Bi0.5Sb1.5Te3 → Sb2Te3）
                parents = [str(r.get("parent_formula") or "").strip()]
                for h in {host, parents[0]} - {""}:
                    old = self._host_table.get(h)
                    if old is None or VERDICT_PRIORITY.get(
                        v.verdict, 0
                    ) > VERDICT_PRIORITY.get(old.verdict, 0):
                        self._host_table[h] = OracleVerdict(
                            formula=h, verdict=verdict,
                            host=h, host_stable=host_stable,
                        )
                n += 1
        return n

    @staticmethod
    def _parse_host_stable(r: dict[str, Any]) -> bool | None:
        """从 entries 推断母体是否稳定（任一库判定 stable 即 True）。"""
        stable_flags = [
            e.get("is_stable") for e in r.get("entries", [])
            if isinstance(e, dict) and e.get("is_stable") is not None
        ]
        if not stable_flags:
            return None
        return any(bool(x) for x in stable_flags)

    def lookup(self, formula: str, host: str = "") -> OracleVerdict:
        """精确命中 formula 表，未命中回退 host 表。"""
        if formula in self._formula_table:
            return self._formula_table[formula]
        if host and host in self._host_table:
            return self._host_table[host]
        return OracleVerdict(formula=formula, host=host)

    # ---------- 评分 ----------
    def score(self, c: Candidate) -> dict[str, float]:
        """严苛评分：数据库真值主导 scientific/feasibility/support 三维（0-1）。"""
        v = self.lookup(c.formula, c.host)
        stab = VERDICT_STABILITY.get(v.verdict)
        if stab is None:
            stab = _HOST_STABLE if v.host_stable is True else _UNKNOWN_STABILITY
        support = VERDICT_SUPPORT.get(v.verdict, 0.5)
        if v.verdict == "未知":
            support = 0.75 if v.host_stable is True else 0.4

        promoting = 1.0 if c.dopant in PROMOTING_DOPANTS else 0.0
        conc_ok = 1.0 if 3.0 <= c.concentration <= 8.0 else 0.0

        scientific = 0.35 + 0.25 * stab + 0.20 * promoting + 0.20 * conc_ok
        feasibility = 0.30 + 0.40 * stab + 0.20 * conc_ok + 0.10 * promoting
        return {
            "scientific": round(min(scientific, 1.0), 2),
            "feasibility": round(min(feasibility, 1.0), 2),
            "support": round(min(support, 1.0), 2),
        }

    def mean_score(self, c: Candidate) -> float:
        """候选在真值尺子上的平均分（与 Candidate.score_avg 对齐）。"""
        s = self.score(c)
        return round(
            sum(s[k] for k in ("scientific", "feasibility", "support")) / 3.0, 3
        )

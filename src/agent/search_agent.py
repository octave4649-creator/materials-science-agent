"""路线 A 搜索 Agent：消费 Gap 清单（gaps.json）→ 构效关系发现。

流水线位置：分析 Agent（Gap 识别）→ 搜索 Agent（本模块）→ 数据库验证（模块 6）。
输入：data/gaps.json 的 Gap（statement/formulas/evidence_ids 作搜索种子与证据链）。
输出：SPRFinding（构效关系陈述 + 新材料假设 + 证据链 + 搜索审计日志），落盘 results/。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.config import DATA_DIR, RESULTS_DIR
from src.common.llm import llm_available, llm_chat_json, model_name
from src.common.logging import AuditLogger
from src.search.bo_search import bo_search
from src.search.ga_search import LLMRoles, ga_search
from src.search.mcts_search import mcts_search
from src.search.schemas import SPRFinding
from src.search.sr_search import sr_search

# 支持的搜索算法
ALGOS = ("ga", "sr", "mcts", "bo")


def _default_gaps_path() -> Path:
    """默认 Gap 清单路径。"""
    return DATA_DIR / "gaps.json"


def _load_gaps(path: Path) -> dict[str, Any]:
    """加载 Gap 清单（gaps.json）。"""
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class SearchResult:
    """搜索结果：发现 + 落盘路径。"""

    finding: SPRFinding
    out_path: Path | None = None


class SearchAgent:
    """路线 A 构效关系搜索 Agent（GA × LLM 三角色）。"""

    def __init__(
        self,
        *,
        gaps_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        logger: AuditLogger | None = None,
    ) -> None:
        """初始化。

        参数:
            gaps_path: Gap 清单路径（默认 data/gaps.json）
            output_dir: 发现落盘目录（默认 results/findings/）
            logger: 审计日志器
        """
        self.gaps_path = Path(gaps_path) if gaps_path else _default_gaps_path()
        self.output_dir = Path(output_dir) if output_dir else RESULTS_DIR / "findings"
        self.logger = logger or AuditLogger("search_agent")

    def run(
        self,
        *,
        top_n: int = 3,
        generations: int = 5,
        pop_size: int = 12,
        use_llm: bool | None = None,
        domain: str = "thermoelectric",
        algo: str = "ga",
        offset: int = 0,
        negative_hosts: list[str] | None = None,
    ) -> list[SearchResult]:
        """对 Gap 清单执行搜索，输出 Top 发现。

        参数:
            top_n: 搜索的 Gap 数量上限（从 offset 起取 Gap 清单前 N 条）
            generations: 迭代次数（GA 代数 / BO 轮数 / MCTS 轮数）
            pop_size: 种群大小（GA）
            use_llm: 是否启用 LLM 三角色（默认按 llm_available 自动）
            domain: 领域标签（审计用）
            algo: 搜索算法（ga / sr / mcts / bo）
            offset: 跳过 Gap 清单前 N 条（分批搜索用，保证可断点续跑）
            negative_hosts: 验证反例母体黑名单（搜索-验证闭环回喂，GA 用）

        返回:
            每个 Gap 一个 SearchResult（finding + 落盘路径）。
        """
        gaps = _load_gaps(self.gaps_path).get("gaps", [])
        if not gaps:
            self.logger.log("search_none", "success", output_summary={"reason": "Gap 清单为空"})
            return []
        if algo not in ALGOS:
            raise ValueError(f"algo 必须是 {ALGOS} 之一，收到 {algo!r}")
        llm_on = llm_available() if use_llm is None else use_llm
        self.logger.log(
            "search_start",
            "success",
            input_summary={
                "n_gaps": len(gaps), "domain": domain, "algo": algo, "offset": offset,
            },
            output_summary={"llm_on": llm_on, "model": model_name() if llm_on else None},
        )
        results: list[SearchResult] = []
        for gap in gaps[offset:offset + top_n]:
            statement = gap.get("statement", "")
            formulas = gap.get("formulas") or []
            evidence_ids = gap.get("evidence_ids") or []
            roles = LLMRoles(chat_json=llm_chat_json)
            with self.logger.step(
                "search_gap", input_summary={"gap": statement[:80], "algo": algo}
            ):
                if algo == "sr":
                    finding = sr_search(
                        gap_statement=statement,
                        hosts=formulas or ["PbTe"],
                        roles=roles,
                        n_points=pop_size,
                        llm_on=llm_on,
                    )
                elif algo == "mcts":
                    finding = mcts_search(
                        gap_statement=statement,
                        hosts=formulas or ["PbTe"],
                        roles=roles,
                        iterations=generations * 12,
                        llm_on=llm_on,
                    )
                elif algo == "bo":
                    finding = bo_search(
                        gap_statement=statement,
                        hosts=formulas or ["PbTe"],
                        roles=roles,
                        llm_on=llm_on,
                    )
                else:
                    finding = ga_search(
                        gap_statement=statement,
                        hosts=formulas or ["PbTe"],
                        roles=roles,
                        generations=generations,
                        pop_size=pop_size,
                        llm_on=llm_on,
                        negative_hosts=negative_hosts,
                    )
            finding.evidence_ids = evidence_ids
            finding.novelty = gap.get("novelty", "待验证")  # type: ignore[assignment]
            # 落盘
            self.output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            out_path = self.output_dir / f"finding_{ts}_{len(results) + 1}.json"
            payload = finding.to_dict()
            payload["gap"] = gap
            payload["algo"] = algo  # 融合投票按算法分组（向后兼容缺省 unknown）
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self.logger.log(
                "search_gap_done",
                "success",
                output_summary={
                    "relation": finding.relation,
                    "confidence": finding.confidence,
                    "llm_calls": roles.log.llm_calls,
                    "llm_failures": roles.log.llm_failures,
                    "out": str(out_path),
                },
            )
            results.append(SearchResult(finding=finding, out_path=out_path))
        return results

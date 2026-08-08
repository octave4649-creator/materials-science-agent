"""生物材料文献检索 Agent：复用 RetrievalAgent，对接 query_expander。

对齐开发计划 T2.1：将 query_expander 产出的 6 个 Research Gap 方向布尔查询，
批量调度到 RetrievalAgent（Sciverse 双通道），跨方向去重 + 证据链合并 + 落盘。

设计原则（00-project-rules.md 4.1 / 5.1）：
1. 证据链强制：每个方向检索结果附带 EvidenceChain，合并为总链
2. 依赖注入：RetrievalAgent 可注入 mock，CI 不依赖网络（exp.md 经验 30）
3. 可观测性：每个方向记录命中数/状态/降级，审计日志可追溯
4. 可回退：单方向失败不中断，降级为 failed 状态并留痕
5. 落盘隔离：output_dir 可配置，避免测试污染真实 results/（exp.md 经验 18）
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.retrieval_agent import Paper, RetrievalAgent, RetrievalResult
from src.common.config import RESULTS_DIR
from src.common.logging import AuditLogger
from src.proteome.query_expander import (
    build_research_question,
    generate_gap_queries,
)
from src.retrieval.evidence import EvidenceChain


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _ts() -> str:
    """本地时间戳，用于落盘文件名（YYYYMMDD_HHMMSS）。"""
    return datetime.now().strftime('%Y%m%d_%H%M%S')


@dataclass
class DirectionResult:
    """单个 Research Gap 方向的检索结果摘要。"""

    direction: str  # 方向键（temperature_response / ...）
    query: str  # 实际投递的布尔查询
    description: str  # 方向描述
    n_papers: int  # 去重后该方向新增的论文数
    total_found: int  # 去重前命中总数（RetrievalAgent 返回）
    status: str  # success / partial / failed
    error: str | None = None  # 失败原因（status=failed 时填）

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容 dict。"""
        return asdict(self)


@dataclass
class BioRetrievalReport:
    """生物材料文献检索总报告。"""

    directions: list[str]  # 实际检索的方向键列表
    total_papers: int  # 跨方向去重后的论文总数
    papers: list[Paper] = field(default_factory=list)  # 去重后全部论文
    evidence: EvidenceChain = field(
        default_factory=lambda: EvidenceChain(conclusion='')
    )
    per_direction: list[DirectionResult] = field(default_factory=list)
    generated_at: str = field(default_factory=_utc_now)
    output_path: str | None = None  # 落盘路径（save 后填充）

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 兼容 dict，用于落盘与审计。"""
        return {
            'directions': self.directions,
            'total_papers': self.total_papers,
            'n_evidence_items': len(self.evidence.items),
            'papers': self.papers,
            'evidence': self.evidence.to_dict(),
            'per_direction': [d.to_dict() for d in self.per_direction],
            'generated_at': self.generated_at,
            'output_path': self.output_path,
        }

    def save(self, path: Path | None = None) -> Path:
        """落盘为 JSON 文件，返回实际写入路径。

        Args:
            path: 指定路径；None 时按时间戳自动生成到 output_dir。
        """
        target = path or (RESULTS_DIR / f'bio_retrieval_{_ts()}.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        self.output_path = str(target)
        return target


class BioRetrievalAgent:
    """生物材料文献检索 Agent。

    复用 RetrievalAgent（Sciverse 双通道），将 query_expander 的 6 个 Gap 方向
    批量调度检索，跨方向去重 + 证据链合并，输出 BioRetrievalReport。
    """

    def __init__(
        self,
        retrieval: RetrievalAgent | None = None,
        logger: AuditLogger | None = None,
        output_dir: Path = RESULTS_DIR,
    ) -> None:
        """初始化。

        Args:
            retrieval: RetrievalAgent 实例（可注入 mock，CI 不依赖网络）。
            logger: 审计日志器。
            output_dir: 报告默认落盘目录。
        """
        self.retrieval = retrieval or RetrievalAgent()
        self.logger = logger or AuditLogger('bio_retrieval_agent')
        self.output_dir = output_dir

    # ---------- 主入口：按 Gap 方向批量检索 ----------

    async def run_gap_search(
        self,
        directions: list[str] | None = None,
        top_k: int = 10,
        year_from: int | None = None,
        mode: str = 'balanced',
        dedupe: bool = True,
    ) -> BioRetrievalReport:
        """按 Research Gap 方向批量检索。

        Args:
            directions: Gap 方向键列表（temperature_response / ...）；None 检索全部 6 个。
            top_k: 每个子查询召回数。
            year_from: 起始年份过滤（结构化通道）。
            mode: 语义检索模式（fast/balanced/quality）。
            dedupe: 是否跨方向去重（默认开）。

        Returns:
            BioRetrievalReport：含去重论文清单 + 合并证据链 + 各方向摘要。
        """
        start = time.perf_counter()
        queries = generate_gap_queries(directions)
        self.logger.log(
            'gap_search_start',
            'success',
            input_summary={
                'n_directions': len(queries),
                'directions': [q['direction'] for q in queries],
                'top_k': top_k,
            },
        )

        seen: set[str] = set()  # 跨方向去重键集合
        all_papers: list[Paper] = []
        evidence = EvidenceChain(
            conclusion='生物材料（酵母蛋白质组学）文献检索证据链'
        )
        per_direction: list[DirectionResult] = []

        for q in queries:
            direction = q['direction']
            query = q['query']
            try:
                result = await self.retrieval.run(
                    query, top_k=top_k, year_from=year_from, mode=mode
                )
                n_added = 0
                for paper in result.papers:
                    if dedupe:
                        key = RetrievalAgent._dedupe_key(paper)
                        if key in seen:
                            continue
                        seen.add(key)
                    all_papers.append(paper)
                    n_added += 1
                # 合并该方向的证据项到总链
                for item in result.evidence.items:
                    evidence.add(item)
                per_direction.append(
                    DirectionResult(
                        direction=direction,
                        query=query,
                        description=q['description'],
                        n_papers=n_added,
                        total_found=result.total_found,
                        status='success' if n_added > 0 else 'partial',
                    )
                )
            except Exception as exc:  # 单方向失败不中断，降级留痕
                per_direction.append(
                    DirectionResult(
                        direction=direction,
                        query=query,
                        description=q['description'],
                        n_papers=0,
                        total_found=0,
                        status='failed',
                        error=str(exc),
                    )
                )
                self.logger.log(
                    'gap_search_direction',
                    'error',
                    input_summary={'direction': direction},
                    error=str(exc),
                )

        report = BioRetrievalReport(
            directions=[q['direction'] for q in queries],
            total_papers=len(all_papers),
            papers=all_papers,
            evidence=evidence,
            per_direction=per_direction,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        n_failed = sum(1 for d in per_direction if d.status == 'failed')
        self.logger.log(
            'gap_search_done',
            'success' if n_failed == 0 else 'warning',
            input_summary={'n_directions': len(queries)},
            output_summary={
                'total_papers': report.total_papers,
                'n_evidence': len(report.evidence.items),
                'n_failed_directions': n_failed,
            },
            duration_ms=elapsed_ms,
        )
        return report

    def run_gap_search_sync(self, **kwargs: Any) -> BioRetrievalReport:
        """同步包装，方便脚本 / CLI 直接调用。"""
        return asyncio.run(self.run_gap_search(**kwargs))

    # ---------- 辅助：按菌株-条件检索 ----------

    async def run_strain_search(
        self,
        strain: str | None = None,
        temperature: str | None = None,
        carbon_source: str | None = None,
        perturbation: str | None = None,
        top_k: int = 10,
        year_from: int | None = None,
        mode: str = 'balanced',
    ) -> RetrievalResult:
        """按菌株-条件组合检索（用 build_research_question 构建自然语言查询）。

        Args:
            strain: 菌株名（如 BAI）。
            temperature: 温度（如 30/37）。
            carbon_source: 碳源（glucose/galactose）。
            perturbation: 扰动 ID（如 #5）。
            top_k: 召回数。
            year_from: 起始年份。
            mode: 语义检索模式。

        Returns:
            RetrievalResult：单次检索结果（含证据链）。
        """
        question = build_research_question(
            strain=strain,
            temperature=temperature,
            carbon_source=carbon_source,
            perturbation=perturbation,
        )
        self.logger.log(
            'strain_search_start',
            'success',
            input_summary={'question': question},
        )
        return await self.retrieval.run(
            question, top_k=top_k, year_from=year_from, mode=mode
        )

    def run_strain_search_sync(self, **kwargs: Any) -> RetrievalResult:
        """同步包装。"""
        return asyncio.run(self.run_strain_search(**kwargs))

    # ---------- 落盘便捷方法 ----------

    def search_and_save(
        self,
        directions: list[str] | None = None,
        top_k: int = 10,
        year_from: int | None = None,
        output_path: Path | None = None,
    ) -> tuple[BioRetrievalReport, Path]:
        """一键检索 + 落盘（同步），返回 (报告, 落盘路径)。"""
        report = self.run_gap_search_sync(
            directions=directions, top_k=top_k, year_from=year_from
        )
        path = output_path or (self.output_dir / f'bio_retrieval_{_ts()}.json')
        report.save(path)
        self.logger.log(
            'search_and_save',
            'success',
            output_summary={'path': str(path), 'total_papers': report.total_papers},
        )
        return report, path

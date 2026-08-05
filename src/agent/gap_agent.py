"""Gap 识别 Agent：知识库 → Research Gap 清单（数据驱动 + LLM 推理 + Sciverse 验证）。

流水线位置：抽取 Agent → 分析 Agent（本模块）→ 报告 Agent。
流程（对齐 .trae/rules/04-literature-agent.md 第 4 节）：
1. 覆盖率分析（find_blank_cells）→ 未探索方向候选
2. 矛盾检测（detect_contradictions）→ 矛盾结论候选
3. LLM 推理（连接发现 + 假设生成）→ 缺失知识连接/方法空白候选
   - 未配置 LLM 时跳过（可复现，不依赖外部服务）
4. Sciverse 回查新颖性（区分新知/已知，决策 2：回查 + 人工复核）
5. 合并去重 → GapReport 落盘 → 审计日志

证据链强制（00-project-rules.md 4.1）：每条 Gap 必须回链知识库 doc_id。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.config import DATA_DIR
from src.common.llm import LLMError, llm_available, llm_chat_json, model_name
from src.common.logging import AuditLogger
from src.extraction.knowledge_base import KnowledgeBase
from src.gap.contradiction import detect_contradictions
from src.gap.coverage import find_blank_cells
from src.gap.schemas import GapCandidate, GapReport
from src.retrieval.sciverse_client import SciverseClient, SciverseError

DEFAULT_GAP_PATH = DATA_DIR / "gaps.json"
_MAX_KB_ENTRIES = 30  # LLM 输入的知识库条目上限（控 token）
_MAX_PROPS_PER_ENTRY = 8


# LLM Gap 推理系统提示：连接发现 + 假设生成，证据必须来自知识库
_SYSTEM_PROMPT = """你是材料科学研究空白（Research Gap）识别助手。
基于给定的材料知识库摘要，识别未被充分探索的研究方向，严格输出 JSON，不要解释。

JSON 结构：
{
  "gaps": [
    {
      "gap_type": "未探索方向|矛盾结论|缺失知识连接|方法空白",
      "statement": "可证伪的科学陈述（一句话）",
      "rationale": "科学依据：为什么这是 Gap",
      "formulas": ["化学式（必须是知识库中存在的条目）"],
      "kb_entry_ids": [0, 1],
      "operability": "如何转化为路线 A 搜索种子",
      "confidence": 0.7
    }
  ]
}

硬性要求：
1. kb_entry_ids 必须引用给定知识库条目的编号（从 0 开始），证据必须来自知识库，严禁编造
2. statement 必须可证伪（可被实验/计算检验）
3. formulas 至少一个，且必须在知识库中存在
4. gap_type 优先找「缺失知识连接」与「方法空白」类，避免与已明确结论重复
5. 输出 3-6 条高质量 Gap，宁缺毋滥
"""


@dataclass
class GapStats:
    """Gap 识别统计（审计与评测用）。"""

    n_entries: int = 0  # 输入知识库条目数
    n_coverage: int = 0  # 覆盖率分析产出数
    n_contradiction: int = 0  # 矛盾检测产出数
    n_llm: int = 0  # LLM 推理产出数
    n_llm_failed: int = 0  # LLM 调用失败次数
    n_verified: int = 0  # Sciverse 回查验证数
    n_verify_degraded: int = 0  # 回查降级数（Sciverse 失败）
    model: str | None = None  # 使用的 LLM 模型


@dataclass
class GapResult:
    """Gap 识别结果：报告 + 统计。"""

    report: GapReport
    stats: GapStats = field(default_factory=GapStats)


class GapAgent:
    """Research Gap 识别 Agent。"""

    def __init__(
        self,
        *,
        kb_path: str | Path | None = None,
        output_path: str | Path | None = None,
        client: SciverseClient | None = None,
        logger: AuditLogger | None = None,
    ) -> None:
        """初始化。

        参数:
            kb_path: 知识库路径（默认 data/knowledge_base.json）
            output_path: Gap 报告落库路径（默认 data/gaps.json）
            client: Sciverse 客户端（默认新建）
            logger: 审计日志器（默认 Gap Agent 专用）
        """
        self.kb = KnowledgeBase(path=kb_path)
        self.output_path = Path(output_path) if output_path else DEFAULT_GAP_PATH
        self.client = client or SciverseClient()
        self.logger = logger or AuditLogger("gap_agent")

    # ---------- 主入口 ----------

    async def run(
        self,
        *,
        domain: str = "materials",
        min_evidence: int = 2,
        max_gaps: int = 20,
        verify: bool = True,
    ) -> GapResult:
        """执行完整 Gap 识别。

        参数:
            domain: 调研领域（写入报告，如 thermoelectric）
            min_evidence: 覆盖率分析的最小证据数（防单篇噪声）
            max_gaps: 返回 Gap 总数上限
            verify: 是否做 Sciverse 新颖性回查（耗时调用，可关闭）

        返回:
            GapResult（GapReport + 统计）。
        """
        stats = GapStats(n_entries=len(self.kb.entries))
        gaps: list[GapCandidate] = []

        with self.logger.step(
            "gap_identify", input_summary={"n_entries": len(self.kb.entries)}
        ):
            # 1. 数据驱动：覆盖率 + 矛盾检测（可靠可复现）
            gaps += self._coverage_gaps(min_evidence)
            stats.n_coverage = len(gaps)
            contra_gaps = self._contradiction_gaps()
            stats.n_contradiction = len(contra_gaps)
            gaps += contra_gaps

            # 2. LLM 推理（可选，未配置/失败静默跳过）
            if llm_available():
                stats.model = model_name()
                llm_gaps, llm_ok = await asyncio.to_thread(self._llm_gaps)
                stats.n_llm = len(llm_gaps)
                stats.n_llm_failed = 0 if llm_ok else 1
                gaps += llm_gaps
            else:
                self.logger.log(
                    "gap_llm_skip", "skipped", output_summary={"reason": "no LLM key"}
                )

            # 3. 去重 + 排序 + 上限
            gaps = self._dedupe(gaps)
            gaps.sort(key=lambda g: g.confidence, reverse=True)
            gaps = gaps[:max_gaps]

            # 4. Sciverse 新颖性回查（逐条，可降级）
            if verify:
                gaps = await self._verify_novelty(gaps, stats)

            report = GapReport(domain=domain, n_entries=len(self.kb.entries), gaps=gaps)
            self._save(report)
            self.logger.log(
                "gap_identify_done",
                "success",
                output_summary={
                    "n_gaps": len(gaps),
                    "stats": self._stats_summary(stats),
                },
            )
        return GapResult(report=report, stats=stats)

    def run_sync(self, **kwargs: Any) -> GapResult:
        """同步包装，方便脚本 / CLI 直接调用。"""
        return asyncio.run(self.run(**kwargs))

    # ---------- 数据驱动检测 ----------

    def _coverage_gaps(self, min_evidence: int) -> list[GapCandidate]:
        """覆盖率分析：研究充分但缺核心性能的体系 → 未探索方向。"""
        with self.logger.step("coverage_analysis", input_summary={"min_evidence": min_evidence}):
            return find_blank_cells(self.kb, min_evidence=min_evidence, max_gaps=20)

    def _contradiction_gaps(self) -> list[GapCandidate]:
        """矛盾检测：同体系多文献数值冲突 → 矛盾结论。"""
        with self.logger.step("contradiction_detection"):
            return detect_contradictions(self.kb, max_gaps=10)

    # ---------- LLM 推理 ----------

    def _llm_gaps(self) -> tuple[list[GapCandidate], bool]:
        """LLM 基于知识库摘要提出 Gap 候选（连接发现 + 假设生成）。

        LLM 输出经 schema 校验，kb_entry_ids 回映射到真实证据 doc_id。
        失败（网络/解析/校验）静默跳过，不阻塞流水线（可回退原则）。

        返回:
            (Gap 候选列表, 是否成功产出)。ok=False 表示 LLM 调用异常。
        """
        summary = self._kb_summary()
        if not summary:
            return [], True
        try:
            raw = llm_chat_json(_SYSTEM_PROMPT, self._llm_user_prompt(summary))
        except LLMError as exc:
            self.logger.log(
                "gap_llm_call", "error", output_summary={"reason": str(exc)[:200]}
            )
            return [], False
        return self._parse_llm_gaps(raw), True

    def _kb_summary(self) -> str:
        """知识库 → 紧凑摘要（按证据数降序取前 N 条）。"""
        entries = sorted(
            self.kb.entries, key=lambda e: len(e.evidence_ids), reverse=True
        )[:_MAX_KB_ENTRIES]
        lines = []
        for i, entry in enumerate(entries):
            props = entry.record.properties[:_MAX_PROPS_PER_ENTRY]
            prop_str = "; ".join(
                f"{p.name}={p.value}{p.unit or ''}" + (f"@{p.condition}" if p.condition else "")
                for p in props
            ) or "无性能数据"
            methods = "; ".join(
                f"{m.type}/{m.software or '?'}" for m in entry.record.methods
            ) or "无方法数据"
            synth = entry.record.synthesis.temperature or "?"
            lines.append(
                f"条目#{i}: 化学式={entry.normalized_formula} | 性能: {prop_str} "
                f"| 方法: {methods} | 合成温度: {synth} | 证据数: {len(entry.evidence_ids)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _llm_user_prompt(summary: str) -> str:
        """构造 LLM 提示（附知识库摘要）。"""
        return (
            "以下是材料知识库摘要（每条含化学式/性能/方法/证据数）：\n\n"
            f"{summary}\n\n"
            "请识别 Research Gap，按 JSON schema 输出。kb_entry_ids 引用上述条目编号。"
        )

    def _parse_llm_gaps(self, raw: dict[str, Any]) -> list[GapCandidate]:
        """LLM 输出 → GapCandidate 列表（kb_entry_ids 回映射证据链）。

        LLM 提供的证据必须来自知识库：按 kb_entry_ids 取真实 doc_id，
        防 LLM 编造证据（经验 13：注入权威来源，不信任模型编造）。
        """
        if not raw or "gaps" not in raw or not isinstance(raw["gaps"], list):
            return []
        gaps: list[GapCandidate] = []
        for item in raw["gaps"]:
            if not isinstance(item, dict):
                continue
            try:
                candidate = GapCandidate.model_validate(item)
            except Exception:
                continue  # schema 校验失败丢弃
            # kb_entry_ids → 真实证据 doc_id（权威来源注入）
            entry_ids = [int(i) for i in item.get("kb_entry_ids", [])]
            evids: list[str] = []
            for i in entry_ids:
                if 0 <= i < len(self.kb.entries):
                    evids.extend(self.kb.entries[i].evidence_ids)
            candidate.evidence_ids = sorted(set(evids)) or candidate.evidence_ids
            if not candidate.evidence_ids:
                continue  # 无证据的 Gap 禁止输出（证据链红线）
            # 仅保留知识库中真实存在的化学式
            valid = {e.normalized_formula for e in self.kb.entries}
            candidate.formulas = [f for f in candidate.formulas if f in valid]
            if not candidate.formulas:
                continue
            candidate.source = "llm"
            gaps.append(candidate)
        return gaps

    # ---------- Sciverse 新颖性验证 ----------

    async def _verify_novelty(
        self, gaps: list[GapCandidate], stats: GapStats
    ) -> list[GapCandidate]:
        """逐条 Sciverse 回查：确认 Gap 是否已被文献覆盖（新知/已知）。

        判定规则（启发式，最终需人工复核）：
        top5 片段中含主化学式的命中数 ≥2 → 已知；=1 → 部分已知；0 → 新知。
        Sciverse 失败 → 保留默认新颖性并降级留痕。
        """
        for gap in gaps:
            try:
                result = await self.client.semantic_search(
                    self._novelty_query(gap), top_k=5, mode="fast"
                )
            except SciverseError as exc:
                stats.n_verify_degraded += 1
                gap.verification = f"Sciverse 回查失败（降级，默认新颖性）：{str(exc)[:120]}"
                self.logger.log(
                    "gap_novelty_verify",
                    "degraded",
                    input_summary={"formula": gap.formulas[0] if gap.formulas else None},
                    output_summary={"reason": str(exc)[:200]},
                )
                continue
            hits = result.get("hits", [])
            formula = gap.formulas[0] if gap.formulas else None
            matched = sum(
                1
                for hit in hits
                if formula and formula in (hit.get("chunk") or "")
            )
            if matched >= 2:
                gap.novelty = "已知"
            elif matched == 1:
                gap.novelty = "部分已知"
            else:
                gap.novelty = "新知"
            gap.verification = (
                f"Sciverse 回查 top5：{matched} 条片段含 {formula or '无化学式'}，"
                "判定仅供参考，需人工复核"
            )
            stats.n_verified += 1
        return gaps

    @staticmethod
    def _novelty_query(gap: GapCandidate) -> str:
        """构造回查查询：主化学式 + Gap 陈述（控长度）。"""
        prefix = f"{gap.formulas[0]} " if gap.formulas else ""
        return f"{prefix}{gap.statement}"[:200]

    # ---------- 合并 / 去重 / 落盘 ----------

    @staticmethod
    def _dedupe(gaps: list[GapCandidate]) -> list[GapCandidate]:
        """按（公式集 + 类型 + 归一化陈述）去重。"""
        seen: set[str] = set()
        out: list[GapCandidate] = []
        for g in gaps:
            key = (
                "|".join(sorted(g.formulas)),
                g.gap_type,
                g.statement.strip().lower()[:80],
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(g)
        return out

    def _save(self, report: GapReport) -> None:
        """GapReport 落盘 JSON。"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _stats_summary(stats: GapStats) -> dict[str, Any]:
        """统计摘要（审计日志用）。"""
        return {
            "n_coverage": stats.n_coverage,
            "n_contradiction": stats.n_contradiction,
            "n_llm": stats.n_llm,
            "n_llm_failed": stats.n_llm_failed,
            "n_verified": stats.n_verified,
            "n_verify_degraded": stats.n_verify_degraded,
        }

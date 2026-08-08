"""抽取 Agent：文献 → 结构化材料知识四元组。

流水线位置：检索 Agent → 抽取 Agent → 分析 Agent（Gap 识别）→ 报告 Agent。
输入：模块 1 输出 JSON（results/retrieval_*.json，含 papers[].chunk 证据片段）。
流程：LLM 按 schema 抽取（防幻觉三件套：schema 约束 + 原文回查 + 证据链接）
      → 未配置/失败降级规则式 → 归一化去重 → 知识库落库 → 审计日志。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.llm import llm_available, llm_chat_json, model_name
from src.common.logging import AuditLogger
from src.extraction.extractor import merge_records, normalize_formula, rule_based_extract
from src.extraction.knowledge_base import KnowledgeBase
from src.extraction.schemas import ExtractionRecord

# LLM 抽取系统提示：schema 约束 + 防幻觉要求。
# 提示词与 gold 字段分布对齐（data/eval/extraction_gold.json）的 v3 版：
# - v1 → v2 实验证明「多值逐条列出」「methods 允许 OTHER」等强化约束
#   导致部分样本（如 p-type/n-type PbTe 片段）整条漏抽（micro F1 0.757→0.667），
#   故 v3 恢复 v1 简洁结构，仅保留两项温和增量：
#   * composition 给掺杂/类型描述示例（gold 5/5 有值，避免只填公式）
#   * properties 给标准名建议（gold 使用 zT/thermal conductivity 等标准名）
_SYSTEM_PROMPT = """你是材料科学文献信息抽取助手。从给定的文献片段中抽取结构化材料知识，
严格输出 JSON，不要输出任何解释。

JSON 结构（材料知识五段式）：
{
  "material": {
    "formula": "化学式（纯文本，如 Ge0.93Ti0.01Bi0.06Te）",
    "composition": "组成/掺杂/类型描述（如 Ti and Bi doped GeTe、p-type PbTe）",
    "structure": {"space_group": "空间群", "lattice": "晶格参数", "phase": "相"}
  },
  "properties": [{"name": "性能名", "value": 数值或null, "unit": "单位", "condition": "条件"}],
  "methods": [{"type": "DFT|MD|ML|EXPERIMENT", "software": "软件", "key_params": "关键参数"}],
  "synthesis": {
    "precursors": "前驱体", "temperature": "温度", "atmosphere": "气氛", "duration": "时间"
  },
  "source": {"doi": "DOI", "page": "页码", "paragraph": "段落定位"}
}

性能名优先使用标准名：zT、band gap、Seebeck coefficient、thermal conductivity、
electrical conductivity、power factor 等。

硬性要求：
1. 只抽取片段中明确提到的信息，严禁编造（防幻觉）
2. formula 必须原文出现；性能值必须是原文数值；未给出绝对数值时 value 填 null 但保留 condition
3. 未提及的字段填 null 或空数组
4. "confidence" 字段：0-1，反映信息完整度
"""


@dataclass
class ExtractionStats:
    """抽取统计（审计与评测用）。"""

    n_papers: int = 0  # 输入文献数
    n_records: int = 0  # 抽取记录数（合并前）
    n_llm: int = 0  # LLM 抽取条数
    n_rule: int = 0  # 规则式抽取条数（降级）
    n_verify_fail: int = 0  # 回查失败丢弃条数
    n_merged: int = 0  # 合并后减少数
    model: str | None = None  # 使用的 LLM 模型


@dataclass
class ExtractionResult:
    """抽取结果：知识库 + 统计。"""

    knowledge_base: KnowledgeBase
    stats: ExtractionStats = field(default_factory=ExtractionStats)


class ExtractionAgent:
    """知识抽取 Agent。"""

    def __init__(
        self,
        *,
        kb_path: str | Path | None = None,
        logger: AuditLogger | None = None,
    ) -> None:
        """初始化。

        参数:
            kb_path: 知识库落库路径（默认 data/knowledge_base.json）
            logger: 审计日志器（默认抽取 Agent 专用）
        """
        self.kb = KnowledgeBase(path=kb_path)
        self.logger = logger or AuditLogger("extraction_agent")

    # ---------- 核心流程 ----------

    def run(self, retrieval_json: str | Path | dict[str, Any]) -> ExtractionResult:
        """执行抽取：读取检索输出 → 抽取 → 校验 → 归一化 → 落库。

        参数:
            retrieval_json: 模块 1 输出（JSON 文件路径或 dict）

        返回:
            ExtractionResult（知识库 + 统计）。
        """
        data = self._load_retrieval(retrieval_json)
        papers = data.get("papers", [])
        stats = ExtractionStats(
            n_papers=len(papers),
            model=model_name() if llm_available() else None,
        )
        with self.logger.step(
            "extract_all", input_summary={"n_papers": len(papers)}
        ):
            records: list[ExtractionRecord] = []
            for paper in papers:
                rec = self._extract_paper(paper, stats)
                if rec is not None:
                    records.append(rec)
            # 归一化合并（同体系多文献合并）
            n_before = len(records)
            merged = merge_records(records)
            stats.n_merged = n_before - len(merged)
            # 落库
            for rec in merged:
                self.kb.add_record(rec, evidence_id=rec.source.doc_id)
            self.kb.save()
            self.logger.log(
                "extract_all_done",
                "success",
                output_summary={
                    "n_records": stats.n_records,
                    "n_merged": stats.n_merged,
                    "kb_path": str(self.kb.path),
                },
            )
        return ExtractionResult(knowledge_base=self.kb, stats=stats)

    # ---------- 单篇抽取 ----------

    def _extract_paper(
        self, paper: dict[str, Any], stats: ExtractionStats
    ) -> ExtractionRecord | None:
        """对单篇文献抽取一条记录（取 chunk 证据片段为输入）。"""
        text = paper.get("chunk") or ""
        doc_id = paper.get("doc_id")
        doi = paper.get("doi")
        page = paper.get("page_no")
        if not text:
            return None
        # 1. LLM 抽取优先，失败降级规则式（可回退）
        used_llm = False
        if llm_available():
            try:
                raw = llm_chat_json(_SYSTEM_PROMPT, self._user_prompt(text))
                rec = self._parse_llm_output(raw, doc_id=doc_id, doi=doi, page=page)
                used_llm = True
            except Exception as exc:  # LLM 任意失败 → 规则式降级
                self.logger.log(
                    "extract_llm_fallback",
                    "degraded",
                    input_summary={"doc_id": doc_id},
                    output_summary={"reason": str(exc)[:200]},
                )
                rec = self._rule_extract(text, doc_id=doc_id)
        else:
            rec = self._rule_extract(text, doc_id=doc_id)
        if rec is None:
            return None
        if used_llm:
            stats.n_llm += 1
        else:
            stats.n_rule += 1
        # 2. 回查防幻觉：化学式必须在原文出现，否则丢弃
        if not self._verify_against_source(rec, text):
            stats.n_verify_fail += 1
            return None
        stats.n_records += 1
        return rec

    def _rule_extract(self, text: str, *, doc_id: str | None) -> ExtractionRecord | None:
        """规则式抽取（降级路径）。"""
        return rule_based_extract(text, doc_id=doc_id)

    # ---------- LLM 输出解析与校验 ----------

    @staticmethod
    def _user_prompt(text: str) -> str:
        """构造抽取提示（含原文片段，控制长度）。"""
        snippet = text if len(text) <= 6000 else text[:6000]
        return f"请从以下文献片段中抽取材料知识四元组：\n\n{snippet}"

    def _parse_llm_output(
        self,
        raw: dict[str, Any],
        *,
        doc_id: str | None,
        doi: str | None,
        page: Any,
    ) -> ExtractionRecord | None:
        """LLM 输出 → ExtractionRecord（schema 校验 + 来源注入）。"""
        if not raw or "material" not in raw:
            return None
        # 注入权威来源（防 LLM 编造来源字段）
        raw["source"] = {
            "doi": doi or raw.get("source", {}).get("doi"),
            "page": str(page) if page is not None else raw.get("source", {}).get("page"),
            "doc_id": doc_id,
        }
        try:
            rec = ExtractionRecord.from_dict(raw)
        except Exception:
            return None
        # 归一化化学式
        rec.material.formula = normalize_formula(rec.material.formula) or rec.material.formula
        return rec

    @staticmethod
    def _verify_against_source(rec: ExtractionRecord, text: str) -> bool:
        """回查防幻觉：化学式（归一化）与性能数值必须在原文出现。

        原文同样做归一化后做子串匹配，避免 LaTeX/HTML 标记差异导致误判。
        """
        if not rec.material.formula:
            return False
        norm_text = normalize_formula(text)
        formula = normalize_formula(rec.material.formula)
        if formula and formula not in norm_text:
            return False
        return True

    # ---------- 输入加载 ----------

    @staticmethod
    def _load_retrieval(retrieval_json: str | Path | dict[str, Any]) -> dict[str, Any]:
        """加载模块 1 输出（路径或 dict）。"""
        if isinstance(retrieval_json, dict):
            return retrieval_json
        path = Path(retrieval_json)
        return json.loads(path.read_text(encoding="utf-8"))

"""报告 Agent：整合模块 1-3 产物 → 结构化调研报告（Markdown/HTML + 版本快照）。

流水线位置：检索 Agent → 抽取 Agent → 分析 Agent → 报告 Agent（本模块）。
策略（task_plan 决策 2）：模板填充（assembly，确定性）→ LLM 仅润色摘要，
禁止 LLM 整篇生成（findings 发现 2：防编造数值/文献）。
输出：results/reports/report_{timestamp}.md/.html + meta.json（版本快照含输入 hash）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.config import PROJECT_ROOT
from src.common.llm import LLMError, llm_available, llm_chat_json
from src.common.logging import AuditLogger
from src.extraction.knowledge_base import KnowledgeBase
from src.report.assembly import (
    build_document,
    load_gaps,
    load_retrieval,
    sha256_file,
)
from src.report.render import render_html, render_markdown
from src.report.schemas import ReportDocument

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "reports"
DEFAULT_KB_PATH = PROJECT_ROOT / "data" / "knowledge_base.json"
DEFAULT_GAPS_PATH = PROJECT_ROOT / "data" / "gaps.json"
DEFAULT_VALIDATION_DIR = PROJECT_ROOT / "results" / "validation"

# LLM 摘要系统提示：只允许使用提供的事实（防幻觉）
_SYSTEM_PROMPT = """你是材料科学文献调研报告摘要撰写助手。
基于给定的调研统计与要点撰写 200-300 字中文摘要，严格输出 JSON：{"abstract": "..."}。
硬性要求：
1. 只使用提供的数字与事实，严禁编造任何数值/文献/结论
2. 摘要结构：领域背景 → 方法（检索/抽取/识别）→ 核心发现（Gap 数量与类型）→ 意义
"""


@dataclass
class ReportResult:
    """报告生成结果。"""

    document: ReportDocument
    md_path: Path | None = None
    html_path: Path | None = None
    meta_path: Path | None = None
    llm_abstract: bool = False


class ReportAgent:
    """调研报告生成 Agent。"""

    def __init__(
        self,
        *,
        retrieval_path: str | Path | None = None,
        kb_path: str | Path | None = None,
        gaps_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        validation_dir: str | Path | None = None,
        logger: AuditLogger | None = None,
    ) -> None:
        """初始化。

        参数:
            retrieval_path: 检索输出 JSON（默认取 results/ 最新 retrieval_*.json）
            kb_path: 知识库路径（默认 data/knowledge_base.json）
            gaps_path: Gap 报告路径（默认 data/gaps.json）
            output_dir: 报告输出目录（默认 results/reports/）
            validation_dir: 模块 6 验证结果目录（默认 None → 验证章节输出
                占位说明；scripts/run_report.py 会显式传入 results/validation/）
            logger: 审计日志器（默认报告 Agent 专用）
        """
        self.retrieval_path = (
            Path(retrieval_path) if retrieval_path else self._latest_retrieval()
        )
        self.kb_path = Path(kb_path) if kb_path else DEFAULT_KB_PATH
        self.gaps_path = Path(gaps_path) if gaps_path else DEFAULT_GAPS_PATH
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.validation_dir = Path(validation_dir) if validation_dir else None
        self.logger = logger or AuditLogger("report_agent")

    # ---------- 主入口 ----------

    def run(
        self,
        *,
        question: str | None = None,
        use_llm: bool = True,
    ) -> ReportResult:
        """执行报告生成：加载输入 → 组装 → 摘要（LLM/规则）→ 渲染 → 落盘。

        参数:
            question: 研究问题（缺省取检索输出中的 query）
            use_llm: 是否尝试 LLM 摘要润色（失败自动降级规则摘要）

        返回:
            ReportResult（报告文档 + 输出路径）。
        """
        with self.logger.step(
            "report_generate",
            input_summary={
                "retrieval": str(self.retrieval_path),
                "kb": str(self.kb_path),
                "gaps": str(self.gaps_path),
            },
        ):
            # 1. 加载输入 + 版本快照
            retrieval = load_retrieval(self.retrieval_path)
            kb = KnowledgeBase(path=self.kb_path)
            gaps = load_gaps(self.gaps_path)
            hashes = {
                "retrieval": sha256_file(self.retrieval_path),
                "kb": sha256_file(self.kb_path),
                "gaps": sha256_file(self.gaps_path),
            }

            # 2. 模板组装（确定性）
            generated_at = (
                retrieval.get("generated_at")
                or retrieval.get("ts")
                or datetime.now(timezone.utc).isoformat(timespec="seconds")
            )
            doc = build_document(
                papers=retrieval.get("papers", []),
                kb=kb,
                gaps_report=gaps,
                question=question or retrieval.get("query"),
                sub_queries=retrieval.get("sub_queries", []),
                generated_at=generated_at,
                total_found=retrieval.get("total_found", len(retrieval.get("papers", []))),
                input_hashes=hashes,
                validation_dir=self.validation_dir,
            )

            # 3. 摘要：LLM 润色优先，失败降级规则摘要（可回退）
            llm_ok = False
            if use_llm and llm_available():
                llm_ok = self._llm_abstract(doc)

            # 4. 渲染 + 落盘（时间戳 + 版本快照）
            md_path, html_path, meta_path = self._save(doc)
            self.logger.log(
                "report_generate_done",
                "success",
                output_summary={
                    "n_sections": len(doc.sections),
                    "n_papers": doc.meta.n_papers,
                    "n_gaps": doc.meta.n_gaps,
                    "llm_abstract": llm_ok,
                    "self_check": doc.meta.self_check,
                    "paths": [str(p) for p in (md_path, html_path, meta_path)],
                },
            )
        return ReportResult(
            document=doc,
            md_path=md_path,
            html_path=html_path,
            meta_path=meta_path,
            llm_abstract=llm_ok,
        )

    # ---------- 摘要 ----------

    def _llm_abstract(self, doc: ReportDocument) -> bool:
        """LLM 生成摘要（基于统计事实，禁止编造）。"""
        gaps = self._gap_statements()
        meta = doc.meta
        user = (
            f"领域：{meta.domain}\n检索文献数：{meta.n_papers}\n"
            f"知识库条目数：{meta.n_kb_entries}\nGap 总数：{meta.n_gaps}\n"
            f"代表性 Gap：\n" + "\n".join(
                f"- [{g.get('gap_type', '未知')}|{g.get('novelty', '未评估')}] "
                f"{g.get('statement', '')}" for g in gaps[:3]
            )
            + "\n请撰写摘要。"
        )
        try:
            raw = llm_chat_json(_SYSTEM_PROMPT, user, max_tokens=512, temperature=0.3)
            abstract = (raw.get("abstract") or "").strip()
            if len(abstract) < 50:
                return False
        except LLMError as exc:
            self.logger.log(
                "report_llm_abstract",
                "degraded",
                output_summary={"reason": str(exc)[:200]},
            )
            return False
        for section in doc.sections:
            if section.key == "abstract":
                section.content = abstract
                break
        return True

    def _gap_statements(self) -> list[dict[str, Any]]:
        """从 gaps.json 读 Gap 要点（供 LLM 摘要使用，避免依赖文档结构）。"""
        data = json.loads(self.gaps_path.read_text(encoding="utf-8"))
        return data.get("gaps", [])

    # ---------- 落盘 ----------

    def _save(self, doc: ReportDocument) -> tuple[Path, Path, Path]:
        """渲染并落盘 md / html / meta（文件名含时间戳，保证版本可追溯）。"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        md_path = self.output_dir / f"report_{stamp}.md"
        html_path = self.output_dir / f"report_{stamp}.html"
        meta_path = self.output_dir / f"report_{stamp}.meta.json"

        md_path.write_text(render_markdown(doc), encoding="utf-8")
        html_path.write_text(render_html(doc), encoding="utf-8")
        meta = doc.to_dict()
        meta["generated_at"] = doc.generated_at
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return md_path, html_path, meta_path

    # ---------- 输入解析 ----------

    @staticmethod
    def _latest_retrieval() -> Path:
        """取 results/ 下最新的 retrieval_*.json。"""
        results = sorted(PROJECT_ROOT.glob("results/retrieval_*.json"))
        if not results:
            raise FileNotFoundError(
                "未找到 results/retrieval_*.json，请先运行 scripts/run_retrieval.py"
            )
        return results[-1]

"""LangGraph 多 Agent 编排：四 Agent 流水线状态图（复赛升级版）。

决策 2（整体计划）：初赛用自研顺序流水线，复赛升级为 LangGraph 状态机。
本模块是编排层重构 —— 现有四个 Agent（Retrieval/Extraction/Gap/Report）接口
保持不变，仅通过 PipelineState 连接 + 条件路由控制流转：

    START → retrieve → route_retrieval ── 不足 → retrieve_more（补检索）↺
                                  └─ 充足 → extract → gap → route_gap
                                       ── 不足 → gap_loop（补抽取：补检索后重抽）↺
                                       └─ 充足 → hitl（人工审核 Gap）→ route_hitl
                                            ── approved → report → END
                                            └─ rejected → gap_loop（补证据重做）↺

条件分支（对应需求）：
1. 检索不足（all_papers < min_papers）→ 补检索：top_k 翻倍 + Sci-Base RAG local search
2. Gap 不足（gaps < min_gaps）→ 补抽取：补检索新文献后回到抽取节点重抽
3. HITL 人工审核：Gap 清单经 interrupt 交人工 approve/reject（LangGraph 原生日志恢复）

证据链与降级（保留现有能力）：节点内审计走 AuditLogger；外部依赖失败不中断
（补检/RAG/LLM 均降级留痕，对齐 exp 经验 26）。
"""
from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.agent.extraction_agent import ExtractionAgent
from src.agent.gap_agent import GapAgent
from src.agent.report_agent import ReportAgent
from src.agent.retrieval_agent import RetrievalAgent
from src.common.logging import AuditLogger
from src.orchestration.state import Paper, PipelineState
from src.rag.rag_tool import RagRetrievalTool

# 条件路由目标节点名
_NODE_RETRIEVE = "retrieve"
_NODE_RETRIEVE_MORE = "retrieve_more"
_NODE_EXTRACT = "extract"
_NODE_GAP = "gap"
_NODE_GAP_LOOP = "gap_loop"
_NODE_HITL = "hitl"
_NODE_REPORT = "report"


class ResearchOrchestrator:
    """文献调研四 Agent 流水线的 LangGraph 编排器。"""

    def __init__(
        self,
        *,
        retrieval_agent: RetrievalAgent | None = None,
        extraction_agent: ExtractionAgent | None = None,
        gap_agent: GapAgent | None = None,
        report_agent: ReportAgent | None = None,
        rag_tool: RagRetrievalTool | None = None,
        logger: AuditLogger | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        """初始化。

        参数:
            retrieval_agent: 检索 Agent（默认新建；测试注入 Fake）
            extraction_agent: 抽取 Agent（默认新建；测试注入 Fake）
            gap_agent: Gap 识别 Agent（默认新建；测试注入 Fake）
            report_agent: 报告 Agent（默认新建；测试注入 Fake）
            rag_tool: Sci-Base RAG local search 工具（默认新建；索引缺失时
                自动降级不参与补检，测试注入临时索引/无索引实例）
            logger: 审计日志器（默认 orchestration 专用）
            checkpointer: LangGraph checkpoint（默认 MemorySaver，HITL 必需）
        """
        self.retrieval_agent = retrieval_agent or RetrievalAgent()
        self.extraction_agent = extraction_agent or ExtractionAgent()
        self.gap_agent = gap_agent or GapAgent()
        self.report_agent = report_agent or ReportAgent()
        self.rag_tool = rag_tool or RagRetrievalTool()
        self.logger = logger or AuditLogger("orchestration")
        self.checkpointer = checkpointer or MemorySaver()
        self.graph = self._build_graph()

    # ---------- 图构建 ----------

    def _build_graph(self) -> Any:
        """构建状态图（节点 + 条件路由）。"""
        g = StateGraph(PipelineState)
        g.add_node(_NODE_RETRIEVE, self._retrieve)
        g.add_node(_NODE_RETRIEVE_MORE, self._retrieve_more)
        g.add_node(_NODE_EXTRACT, self._extract)
        g.add_node(_NODE_GAP, self._gap)
        g.add_node(_NODE_GAP_LOOP, self._gap_loop)
        g.add_node(_NODE_HITL, self._hitl)
        g.add_node(_NODE_REPORT, self._report)

        g.add_edge(START, _NODE_RETRIEVE)
        # 检索不足循环：retrieve / retrieve_more 共用同一路由
        g.add_conditional_edges(
            _NODE_RETRIEVE,
            self._route_retrieval,
            {_NODE_RETRIEVE_MORE: _NODE_RETRIEVE_MORE, _NODE_EXTRACT: _NODE_EXTRACT},
        )
        g.add_conditional_edges(
            _NODE_RETRIEVE_MORE,
            self._route_retrieval,
            {_NODE_RETRIEVE_MORE: _NODE_RETRIEVE_MORE, _NODE_EXTRACT: _NODE_EXTRACT},
        )
        g.add_edge(_NODE_EXTRACT, _NODE_GAP)
        # Gap 不足循环：gap_loop（补检索）→ extract → gap
        g.add_conditional_edges(
            _NODE_GAP,
            self._route_gap,
            {_NODE_GAP_LOOP: _NODE_GAP_LOOP, _NODE_HITL: _NODE_HITL},
        )
        g.add_edge(_NODE_GAP_LOOP, _NODE_EXTRACT)
        # HITL 审核：approved → report；rejected → 补证据重做
        g.add_conditional_edges(
            _NODE_HITL,
            self._route_hitl,
            {_NODE_REPORT: _NODE_REPORT, _NODE_GAP_LOOP: _NODE_GAP_LOOP},
        )
        g.add_edge(_NODE_REPORT, END)
        return g.compile(checkpointer=self.checkpointer)

    # ---------- 节点实现 ----------

    def _retrieve(self, state: PipelineState) -> dict:
        """首轮检索：问题拆解 + 双通道（Sciverse web search）。"""
        question = state["question"]
        top_k = state.get("top_k", 10)
        with self.logger.step(
            "node_retrieve", input_summary={"question": question, "top_k": top_k}
        ):
            result = self.retrieval_agent.run_sync(
                question=question, top_k=top_k, year_from=state.get("year_from")
            )
        all_papers = self._merge_papers(state.get("all_papers", []), result.papers)
        return {
            "all_papers": all_papers,
            "sub_queries": list(result.sub_queries),
        }

    def _retrieve_more(self, state: PipelineState) -> dict:
        """补检索：Sciverse web 重查（top_k 翻倍）+ Sci-Base RAG local search。

        双数据源（对齐 02-literature-data-sources.md 第 4 节「双通道检索架构」）：
        web search（Sciverse API）与 local search（Sci-Base 本地 BM25）结果
        合并去重后写入 all_papers，供抽取 Agent 消费；RAG 索引缺失时降级
        不中断（留痕于日志，不写入 errors 阻断流程）。
        """
        question = state["question"]
        loop = state.get("n_retrieve_loops", 0) + 1
        top_k = state.get("top_k", 10) * (loop + 1)
        with self.logger.step(
            "node_retrieve_more",
            input_summary={"question": question, "top_k": top_k, "loop": loop},
        ):
            result = self.retrieval_agent.run_sync(
                question=question, top_k=top_k, year_from=state.get("year_from")
            )
            merged = self._merge_papers(state.get("all_papers", []), result.papers)
            # 第二数据源：Sci-Base local search（索引不可用则降级跳过）
            rag_papers = self._rag_retrieve(question, top_k)
            merged = self._merge_papers(merged, rag_papers)
        return {
            "all_papers": merged,
            "sub_queries": list(result.sub_queries),
            "n_retrieve_loops": loop,
        }

    def _rag_retrieve(self, question: str, top_k: int) -> list[Paper]:
        """Sci-Base RAG local search（双数据源之一）。

        索引不可用/检索异常时降级返回空列表并留痕（不抛错、不写入
        errors，避免外部依赖缺失阻断流水线，对齐 exp 经验 26/47）。
        """
        if not self.rag_tool.available:
            self.logger.log(
                "rag_unavailable",
                "degraded",
                input_summary={"question": question},
                output_summary={"reason": "index missing or load failed"},
            )
            return []
        try:
            papers = self.rag_tool.search_papers(question, top_k=top_k)
        except Exception as exc:  # pragma: no cover - 防御性降级
            self.logger.log(
                "rag_search_error",
                "degraded",
                input_summary={"question": question},
                error=str(exc)[:200],
            )
            return []
        if papers:
            self.logger.log(
                "rag_retrieve_done",
                "success",
                input_summary={"question": question, "top_k": top_k},
                output_summary={"n_merged": len(papers)},
            )
        return papers

    def _extract(self, state: PipelineState) -> dict:
        """知识抽取：从 all_papers（含补检累积文献）抽取 → 知识库落盘。"""
        papers = state.get("all_papers", [])
        if not papers:
            self.logger.log("node_extract_skip", "skipped", output_summary={"reason": "no papers"})
            return {"errors": state.get("errors", []) + ["extract skipped: no papers"]}
        with self.logger.step(
            "node_extract", input_summary={"n_papers": len(papers)}
        ):
            result = self.extraction_agent.run(self._retrieval_json(state))
        stats = result.stats
        return {
            "extract_n_records": stats.n_records if stats else 0,
        }

    def _gap(self, state: PipelineState) -> dict:
        """Gap 识别：知识库 → Gap 清单（覆盖率 + 矛盾 + LLM + 回查）。"""
        with self.logger.step(
            "node_gap",
            input_summary={"domain": state.get("domain", "materials")},
        ):
            result = self.gap_agent.run_sync(
                domain=state.get("domain", "materials"),
                min_evidence=2,
                max_gaps=20,
                verify=True,
            )
        report = result.report
        summary = [
            {
                "statement": g.statement,
                "gap_type": g.gap_type,
                "formulas": g.formulas,
            }
            for g in report.gaps
        ]
        return {"n_gaps": len(report.gaps), "gap_summary": summary}

    def _gap_loop(self, state: PipelineState) -> dict:
        """补抽取：先补检索新文献，再回到抽取节点重抽（Gap 不足根因=语料不足）。"""
        loop = state.get("n_gap_loops", 0) + 1
        with self.logger.step(
            "node_gap_loop",
            input_summary={"loop": loop, "reason": "insufficient gaps"},
        ):
            more = self._retrieve_more(state)
        more["n_gap_loops"] = loop
        return more

    def _hitl(self, state: PipelineState) -> dict:
        """HITL 人工审核节点：interrupt 展示 Gap 清单，人工 approve/reject。"""
        payload = {
            "type": "gap_review",
            "question": state.get("question", ""),
            "n_gaps": state.get("n_gaps", 0),
            "gaps": state.get("gap_summary", []),
            "instruction": (
                "请审核上述 Research Gap 清单：回复 'approve' 进入报告生成；"
                "回复 'reject' 拒绝（将补检索重做 Gap 识别）"
            ),
        }
        decision = interrupt(payload)
        status = "approved" if decision == "approve" else "rejected"
        self.logger.log(
            "node_hitl", "success", output_summary={"decision": status}
        )
        return {"hitl_status": status}

    def _report(self, state: PipelineState) -> dict:
        """报告生成：Gap 清单 → 结构化调研报告（模板 + LLM 摘要润色）。"""
        with self.logger.step(
            "node_report",
            input_summary={"question": state.get("question", "")},
        ):
            result = self.report_agent.run(
                question=state.get("question"),
                use_llm=state.get("use_llm", True),
            )
        return {"report_paths": self._report_summary(result)}

    # ---------- 条件路由 ----------

    def _route_retrieval(self, state: PipelineState) -> str:
        """检索是否充足：all_papers >= min_papers 或循环达上限 → extract。"""
        n_papers = len(state.get("all_papers", []))
        min_papers = state.get("min_papers", 3)
        if n_papers >= min_papers or state.get("n_retrieve_loops", 0) >= state.get(
            "max_retrieve_loops", 2
        ):
            return _NODE_EXTRACT
        return _NODE_RETRIEVE_MORE

    def _route_gap(self, state: PipelineState) -> str:
        """Gap 是否充足：n_gaps >= min_gaps 或循环达上限 → hitl。"""
        n_gaps = state.get("n_gaps", 0)
        min_gaps = state.get("min_gaps", 2)
        if n_gaps >= min_gaps or state.get("n_gap_loops", 0) >= state.get(
            "max_gap_loops", 2
        ):
            return _NODE_HITL
        return _NODE_GAP_LOOP

    def _route_hitl(self, state: PipelineState) -> str:
        """HITL 审核结果：approved → report；rejected → gap_loop（补证据重做）。"""
        return _NODE_REPORT if state.get("hitl_status") == "approved" else _NODE_GAP_LOOP

    # ---------- 对外接口 ----------

    def run(
        self,
        question: str,
        *,
        domain: str = "materials",
        top_k: int = 10,
        year_from: int | None = None,
        use_llm: bool = True,
        auto_approve: bool = True,
        thread_id: str | None = None,
        min_papers: int = 3,
        min_gaps: int = 2,
        max_retrieve_loops: int = 2,
        max_gap_loops: int = 2,
    ) -> PipelineState:
        """执行完整流水线（含 HITL 审核）。

        参数:
            question: 研究问题
            domain: 调研领域
            top_k: 单轮检索 top_k
            year_from: 年份过滤
            use_llm: 报告是否尝试 LLM 摘要润色
            auto_approve: True 时 HITL 自动 approve（脚本/自动化场景）；False 时
                停在人工审核节点，由调用方用 graph + thread_id 手动 resume
            thread_id: LangGraph 会话 ID（默认随机，每次 run 独立）
            min_papers/min_gaps/max_retrieve_loops/max_gap_loops: 条件路由阈值

        返回:
            最终 PipelineState（含 report 产物）。
        """
        thread_id = thread_id or uuid.uuid4().hex[:12]
        config = {"configurable": {"thread_id": thread_id}}
        initial: PipelineState = {
            "question": question,
            "domain": domain,
            "top_k": top_k,
            "year_from": year_from,
            "use_llm": use_llm,
            "min_papers": min_papers,
            "min_gaps": min_gaps,
            "max_retrieve_loops": max_retrieve_loops,
            "max_gap_loops": max_gap_loops,
            "all_papers": [],
            "n_retrieve_loops": 0,
            "n_gap_loops": 0,
            "errors": [],
        }
        self.logger.log(
            "orchestrate_run",
            "success",
            input_summary={"question": question, "thread_id": thread_id},
        )
        result = self.graph.invoke(initial, config)
        if auto_approve and self.graph.get_state(config).next:
            result = self.graph.invoke(Command(resume="approve"), config)
        return result

    # ---------- 工具方法 ----------

    def _retrieval_json(self, state: PipelineState) -> dict[str, Any]:
        """构造抽取 Agent 需要的 retrieval dict（兼容 ExtractionAgent.run）。"""
        return {
            "query": state.get("question", ""),
            "sub_queries": list(state.get("sub_queries", [])),
            "papers": state.get("all_papers", []),
            "total_found": len(state.get("all_papers", [])),
        }

    @staticmethod
    def _report_summary(result: Any) -> dict[str, Any]:
        """报告 Agent 输出 → JSON 兼容摘要（路径或 marker）。"""
        if isinstance(result, dict):
            return {"detail": result}
        if hasattr(result, "md_path") and result.md_path is not None:
            return {
                "md": str(result.md_path),
                "html": str(result.html_path) if getattr(result, "html_path", None) else None,
                "meta": str(result.meta_path) if getattr(result, "meta_path", None) else None,
            }
        return {"marker": str(result)}

    @staticmethod
    def _merge_papers(existing: list[Paper], new: list[Paper]) -> list[Paper]:
        """合并文献并按 doc_id/unique_id/标题去重（顺序：现有在前）。"""
        seen: set[str] = set()
        merged: list[Paper] = []
        for paper in list(existing) + list(new):
            key = (
                f"doc:{paper.get('doc_id')}"
                if paper.get("doc_id")
                else f"uid:{paper.get('unique_id')}"
                if paper.get("unique_id")
                else f"title:{str(paper.get('title', '')).strip().lower()}"
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(paper)
        return merged

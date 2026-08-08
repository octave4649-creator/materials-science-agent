"""LangGraph 编排状态定义（四 Agent 流水线的共享结构化状态）。

对齐教程「以工作流编排为主、Agent 自主决策为辅，通过共享结构化状态连接各模块」：
四个 Agent 不直接相互调用，而是通过 PipelineState 传递产物（检索结果 → 知识库
→ Gap 报告 → 调研报告），编排层（条件路由 + HITL）控制流转。

设计约束（LangGraph checkpoint）：状态中所有值必须是 JSON/msgpack 可序列化
类型（dict/list/str/int），不存放自定义对象（KnowledgeBase/GapReport 等
由各 Agent 落盘到文件，编排层只传递其摘要/计数）。
"""
from __future__ import annotations

from typing import Any, NotRequired, TypedDict

# 统一论文结构（对齐 retrieval_agent.Paper）
Paper = dict[str, Any]


class PipelineState(TypedDict, total=False):
    """四 Agent 流水线共享状态（全 JSON 兼容）。

    字段约定：
        输入（run 时注入）：question / domain / top_k / year_from / use_llm
        阈值（可覆盖）：min_papers / min_gaps / max_retrieve_loops / max_gap_loops
        产物：all_papers / sub_queries / n_gaps / gap_summary / report_paths
        控制：n_retrieve_loops / n_gap_loops / hitl_status / errors
    """

    # ---- 输入 ----
    question: str  # 研究问题
    domain: str  # 调研领域（写入 Gap 报告，如 thermoelectric）
    top_k: int  # 单轮检索 top_k
    year_from: NotRequired[int | None]  # 年份过滤
    use_llm: NotRequired[bool]  # 报告是否尝试 LLM 摘要润色

    # ---- 阈值（条件路由判定） ----
    min_papers: NotRequired[int]  # 检索论文数下限，低于则补检索
    min_gaps: NotRequired[int]  # Gap 数下限，低于则补抽取
    max_retrieve_loops: NotRequired[int]  # 检索不足循环上限
    max_gap_loops: NotRequired[int]  # Gap 不足循环上限

    # ---- 产物（JSON 兼容） ----
    all_papers: NotRequired[list[Paper]]  # 累积去重后全部文献
    sub_queries: NotRequired[list[str]]  # 检索子问题（供抽取 Agent）
    extract_n_records: NotRequired[int]  # 抽取记录数（审计）
    n_gaps: NotRequired[int]  # Gap 数（路由判定 + HITL 展示）
    gap_summary: NotRequired[list[dict[str, Any]]]  # Gap 摘要清单（HITL 展示）
    report_paths: NotRequired[dict[str, Any] | None]  # 报告落盘路径/摘要

    # ---- 控制 ----
    n_retrieve_loops: NotRequired[int]  # 补检索已执行轮数
    n_gap_loops: NotRequired[int]  # 补抽取已执行轮数
    hitl_status: NotRequired[str | None]  # HITL 审核结果（approved/rejected）
    errors: NotRequired[list[str]]  # 全程错误留痕（降级不中断）

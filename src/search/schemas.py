"""路线 A 构效关系搜索 Schema。

对齐 `.trae/rules/05-route-a-SPR.md`：候选生成→评估→筛选→验证闭环。
候选（Candidate）携带 LLM 理由（rationale）与打分（scores），输出可解释、
带证据链的构效关系假设，供模块 6 数据库交叉验证。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# LLM 三角色标记：生成器 / 评估器 / 剪枝器
LLMRole = Literal["generator", "evaluator", "pruner"]

# 候选来源：LLM 种子 / GA 交叉 / GA 变异 / 随机
CandidateSource = Literal["llm_seed", "ga_crossover", "ga_mutation", "random"]


def _utc_now() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Candidate(BaseModel):
    """一条材料候选（掺杂/成分假设）。

    描述符对齐热电体系：母体 + 掺杂元素 + 掺杂浓度（摩尔分数 %）。
    """

    host: str = Field(description="母体化学式（如 PbTe / GeTe / Bi2Te3）")
    dopant: str = Field(description="掺杂元素符号（如 Ti / Bi / Na）")
    concentration: float = Field(description="掺杂浓度（摩尔分数 %，如 6.0 表示 6%）")
    formula: str = Field(description="名义化学式（如 Pb0.94Ti0.06Te）")
    rationale: str = Field(default="", description="LLM 生成/评估理由（科学解释）")
    source: CandidateSource = Field(default="random")
    scores: dict[str, float] = Field(
        default_factory=dict, description="评估分数：scientific / feasibility / support"
    )
    verdict: Literal["keep", "drop", "pending"] = Field(default="pending")

    def score_avg(self) -> float:
        """平均评估分（无分数时返回 0）。"""
        vals = [v for v in self.scores.values() if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化（pydantic model_dump）。"""
        return self.model_dump()


class SearchStep(BaseModel):
    """一次搜索迭代的审计记录（发现日志，对齐 Automat idea.md 模式）。"""

    generation: int = Field(description="代数")
    action: str = Field(description="动作：evaluate / crossover / mutate / prune / seed")
    n_candidates: int = Field(description="该步候选数")
    llm_role: LLMRole | None = Field(default=None, description="参与的 LLM 角色")
    detail: str = Field(default="", description="决策摘要（如淘汰 3 条：原因 xxx）")
    ts: str = Field(default_factory=_utc_now)


class SearchLog(BaseModel):
    """搜索过程完整审计日志。"""

    steps: list[SearchStep] = Field(default_factory=list)
    llm_calls: int = Field(default=0, description="LLM 调用次数（可审计/成本核算）")
    llm_failures: int = Field(default=0, description="LLM 失败降级次数")
    used_llm: bool = Field(default=False, description="本次搜索是否使用 LLM")

    def add(self, **kw: Any) -> None:
        """追加一条搜索记录。"""
        self.steps.append(SearchStep(**kw))


class SPRFinding(BaseModel):
    """构效关系发现（最终输出）：陈述 + 证据链 + 新知/已知 + 机制解释。"""

    relation: str = Field(description="构效关系陈述（如：PbTe 中 Ti 掺杂增大带隙且提升 zT）")
    hypothesis: str = Field(description="新材料设计假设（可证伪）")
    top_candidates: list[Candidate] = Field(default_factory=list)
    gap_statement: str = Field(default="", description="触发本次搜索的 Gap 陈述")
    evidence_ids: list[str] = Field(default_factory=list, description="证据链（Gap 证据 doc_id）")
    novelty: Literal["新知", "已知", "部分争议", "待验证"] = Field(default="待验证")
    mechanism: str = Field(default="", description="物理/化学机制解释（非黑箱）")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    search_log: SearchLog = Field(default_factory=SearchLog)
    generated_at: str = Field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """序列化（含候选与日志）。"""
        return self.model_dump()

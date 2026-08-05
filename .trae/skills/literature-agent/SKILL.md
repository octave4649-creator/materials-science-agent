---
name: "literature-agent"
description: "提供文献调研 Agent（基本任务）的架构与实现方法：四 Agent 流水线设计、知识抽取 Schema、Research Gap 识别四方法、调研报告生成。当开发文献检索/知识抽取/Gap 识别/报告生成模块时调用。"
---

# 文献调研 Agent（基本任务）

## 1. 任务定位

必做项，占材料方向评分 50%。四项能力：文献检索与筛选、知识抽取、Research Gap 识别、调研报告生成。产出物是进阶路线的输入。

## 2. 架构：四 Agent 流水线

```
检索 Agent → 抽取 Agent → 分析 Agent(Gap 识别) → 报告 Agent
    │              │               │
Sciverse 双通道  MinerU+LLM      知识库+向量检索
```

- 复赛用 LangGraph 状态机编排，支持条件路由 + HITL 人工审核
- 每个 Agent 输出结构化 JSON 日志 + 工具调用序列（审计）

## 3. 知识抽取 Schema（材料知识四元组）

```json
{
  "material": {"formula": "string", "composition": "string", "structure": {"space_group": "string", "lattice": "string", "phase": "string"}},
  "properties": [{"name": "string", "value": "number", "unit": "string", "condition": "string"}],
  "methods": [{"type": "DFT|MD|ML|EXPERIMENT", "software": "string", "key_params": "string"}],
  "synthesis": {"precursors": "string", "temperature": "string", "atmosphere": "string", "duration": "string"},
  "source": {"doi": "string", "page": "string", "paragraph": "string"}
}
```

策略：MinerU 预处理 PDF → LLM 按 schema 抽取 → 回查原文防幻觉 → 归一化去重。

## 4. Research Gap 识别（四种方法）

| 方法 | 原理 | 适用 |
|------|------|------|
| 覆盖率分析 | 成分×结构×性能矩阵找空白 | 未探索方向 |
| 矛盾检测 | 同体系多文献数值对比 | 矛盾结论 |
| 连接发现 | 知识图谱/共现弱关联 | 缺失知识连接 |
| LLM 推理+验证 | LLM 提假设，Sciverse 回查 | 全部 |

**评估**：Gap 需附证据链、区分新颖性、说明可操作性（能否转路线 A 搜索种子）。

## 5. 报告结构

研究问题与范围 → 检索策略与数据来源 → 知识抽取结果 → Research Gap 清单（带证据链+交叉引用）→ 文献综述 → 结论建议 → 附录文献清单。

## 6. 证据链数据模型

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class EvidenceItem:
    source: str          # sciverse / mp / oqmd / mineru
    doc_id: str          # DOI / material_id
    page: str | None = None
    text: str = ""
    fetched_at: datetime = field(default_factory=datetime.now)

@dataclass
class EvidenceChain:
    conclusion: str
    items: list[EvidenceItem]
    validated: bool = False
```

---

> 详细设计见 `.trae/rules/04-literature-agent.md`；评测指标见 `DEVELOPMENT-GUIDE.md` 第 6 节。

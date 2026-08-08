# 材料文献驱动的科学发现智能体 —— 项目一页纸

## 一句话简介

一个「从文献出发、可验证的科学发现智能体」：检索-抽取-Gap-搜索-验证全链路自动运转，在热电材料掺杂空间中发现可解释、可验证的构效关系。

## 科学问题

热电优值 zT = S²σT/κ 受电热输运强耦合制约，掺杂 × 浓度组合空间巨大，理性设计长期依赖试错实验。能否用「文献证据驱动 + 搜索算法 × LLM 深度融合」自动发现热电材料中可解释、可验证的掺杂构效关系？

## 方法与创新点

1. **文献调研四 Agent 闭环 + 证据链强制**：检索（Sciverse 双通道）→ 抽取（LLM+schema，MinerU 兜底）→ Gap 识别（覆盖率/矛盾/LLM 推理 + Sciverse 回查）→ 报告；每个结论强制携带可回溯证据链（doc_id/DOI/页码）。
2. **搜索算法 × LLM 三角色深度融合**：GA/MCTS/BO/SR 四算法统一契约，LLM 以「假设种子生成器 / 科学合理性评估器 / 搜索空间引导器」三角色进入搜索循环本身（而非仅写搜索代码）；SR 输出显式解析公式 + R²，非黑箱。
3. **数据库交叉验证 + 搜索-验证负反馈闭环**：OQMD/MP 交叉验证区分「新知/已知/反例」，A/B 位拆分纯母体解析解决分数掺杂直查失败，反例母体自动回喂剪枝器。

## 核心结果（全部量化，产物可复现）

| 评测项 | 数值 | 产物 |
|--------|------|------|
| 知识抽取字段级 F1（LLM vs 人工 gold，热电 5 条） | LLM micro 0.68 / macro 0.66（formula 1.0 / composition 0.67 / properties 0.57）；规则式 micro 0.28 / macro 0.17 | `results/eval/extraction_f1_20260808T163821.json` |
| Research Gap 识别 | 29 条（新知 15 / 部分已知 14），29/29 Sciverse 回查留痕 | `data/gaps.json` |
| 已知关系召回率 · LLM 模式（16 条全量） | GA recall@5=1.0 / cov=1.0 最优；SR recall@3=0.688 | `results/eval/recall_matrix_20260808T173730.json` |
| 三臂消融（Oracle 真值评分） | full 0.806 / rule 0.885 / llm 0.785；GA 演化增益 +2.65% | `results/ablation/ablation_report.json` |
| 数据库交叉验证 | OQMD 主 + MP 增强；oracle 真值表 220 条 / 15 母体体系；38 项验证失败 A/B 位拆分重验后归零 | `results/validation/` |
| 证据链可审计性 | 回填后 Gap 29/29 可回溯（回填前 1/29，六通道）；审计五项全链路留痕 | `results/audit/evidence_report_20260808T091510.md` |
| 四算法输出融合投票 | 29 Gap / 348 候选，Borda rank 加权（规则模式 0 共识，如实记录） | `results/ensemble/ensemble_20260808T093952.md` |

## 团队与开源仓库

- 赛道三 · 方向三（材料科学文献驱动的科学发现智能体）｜基本任务 + 路线 A（构效关系发现）
- 开源仓库：参赛提交后开放（MIT License，代码 + 数据 + 复现说明完整）
- 全量回归：pytest 399/399 全绿，ruff 零 error；固定随机种子，命令级复现见 `docs/experiment-report.md`

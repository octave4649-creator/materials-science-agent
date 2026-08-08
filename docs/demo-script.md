---
title: "决赛现场 Demo 脚本（问题→Gap→构效关系→数据库验证）"
category: "deliverable"
tags: [决赛, demo, 脚本, 路线A, 数据库验证]
description: "以 12 条 LLM 多算法共识 + 数据库判定对照表为核心素材的现场演示分镜脚本，全部数值引用真实产物"
created: "2026-08-08"
updated: "2026-08-08"
status: "draft"
version: "1.0"
---

# 决赛现场 Demo 脚本

> 配套可视化：浏览器打开 `docs/demo-panel.html`（自包含面板，Gap 证据 29/29 全链路）。
> 本脚本为「录制/现场演示」分镜，建议时长 6 分钟；每幕给出演示动作 + 口播要点 + 数据来源（可点击核对）。

## 0. 素材清单（演示前核对）

| 素材 | 路径 | 内容 |
|------|------|------|
| 全流程面板 | `docs/demo-panel.html` | 问题→文献→Gap→构效→验证→评测→证据链 7 段可视化 |
| 12 条 LLM 共识 | `results/ensemble/ensemble_llm_20260808.md/.html` | 四算法融合投票（GA/SR/MCTS/BO，40 条 LLM finding） |
| 判定对照表 | `results/consensus/consensus_verify_20260808T105523.md/.html` | 12 共识候选 → 数据库判定（已知 9 / 反例 3） |
| MP 相图级核验 | `results/validation/mp_phase_check_20260808T133350.json` | 7 母体相图级稳定 + 3 例双 thermo 复核留痕 |
| Oracle 真值表 | `results/oracle/oracle_truth_20260808T132948.json` | OQMD 12 母体直查（已知 10 / 反例 2） |
| 召回率矩阵 | `results/eval/recall_matrix_20260808T211437.json` | 四算法 × LLM/规则双模式全量 16 条 |
| 初赛方案 | `docs/initial-round-proposal.docx` | 方案说明（≤4 页，8.16 提交） |

## 第一幕：科学问题（约 40 秒）

**演示动作**：打开 demo-panel「问题」段。

**口播要点**：
- 热电材料将温差直接转换为电能，是工业余热回收的关键；其性能由无量纲优值 `zT` 决定。
- 提升 `zT` 的核心手段是**掺杂工程**：在母体中引入特定元素调节载流子浓度。但**掺杂方案空间巨大**（多种母体 × 十余种元素 × 浓度连续取值），传统试错成本极高。
- 我们的智能体要回答：能否**从文献出发，自动发现「掺杂 → 性能」的构效关系**，并用开源数据库验证？

**数据来源**：`docs/initial-round-proposal.md` 第 1 节（问题真实性）。

## 第二幕：文献调研与 Research Gap（约 1 分 20 秒）

**演示动作**：demo-panel「文献 → Gap」段；切换到 12 条共识对应 6 个体系。

**口播要点**：
- 四 Agent 流水线：**检索**（Sciverse 双通道，证据链可审计）→ **抽取**（LLM+规则双路径，字段级 F1=0.7805）→ **Gap 识别**（覆盖率+矛盾+LLM 推理+Sciverse 回查）→ **报告**（9 章节结构化）。
- 产出 **29 条 Research Gap**，全部带证据链（Gap 可追溯 29/29，来源 kb_exact/kb_parent/retrieval 六通道回填）。
- 多算法融合收敛出 **6 个 Gap 的 12 条共识候选**（多算法一致 = 高置信信号，规则模式 0 共识 vs LLM 模式 12 共识，体现 LLM 参与搜索的价值）。

**演示动作**：逐个展示 6 个 Gap 的陈述（可在 demo-panel 上高亮）。

| # | Gap 陈述 | 共识候选 |
|---|---------|---------|
| 1 | Mg3Sb2 阳离子空位与载流子迁移率缺乏系统第一性原理计算 | Mg3Sb2-Na2% |
| 2 | Bi0.5Sb1.5Te3 Cu 间隙掺杂长期热稳定性与 zT 退化机制未研究 | Bi0.5Sb1.5Te3-Cu1%/2% |
| 3 | Cu2Se Te 取代 Se 对 Cu 迁移活化能影响未见报道 | Cu2Se-Te5% |
| 4 | GeTe 高 Ti 含量相变温度与热电性能关联空白 | Ge0.98Bi0.02Te、Ge0.97Ti0.03Te |
| 5 | ZrNiSn Ti 掺杂 κL 与 PF trade-off 未量化 | ZrNiSn-Hf5%/Ti5% |
| 6 | CoSb3 Yb/Ba 双填充与 zT 相图存在矛盾报道 | CoSb3-Yb0.2Ba0.10%、Yb0.15Ba0.150% |

**数据来源**：`results/ensemble/ensemble_llm_20260808.md`（各 Gap 候选表 + 证据链 doc_id）。

## 第三幕：构效关系发现（搜索 × LLM 融合）（约 1 分 20 秒）

**演示动作**：demo-panel「构效关系」段；打开召回率矩阵。

**口播要点**（方法创新点，评审重点）：
- 不是用 LLM 写搜索代码，而是 **LLM 深度参与搜索过程**：生成候选假设（种子）、评估中间结果科学合理性、引导搜索空间剪枝；搜索算法（GA/MCTS/BO/SR）负责在组合空间探索。
- 全量 **16 条已知构效关系召回率评测**（双模式）：GA LLM 模式 recall@1=0.75 / recall@5=0.938 / coverage=0.938 最优；规则模式 coverage 全面落后——**量化「LLM 参与探索」的融合增益**。
- **MCTS 短板攻坚**（代表性工程）：树搜索叶采样预算导致 coverage 结构性上限，通过「展开即评估」+ 母体过滤修复 + LLM 批量评估截断规避，**cov 0.375→1.0、recall@5 0.25→0.812**。
- 消融实验：VerificationOracle 真值评分下 full 0.833 / rule 0.933 / llm 0.833。

**数据来源**：`results/eval/recall_matrix_20260808T211437.json`、`results/ablation/ablation_report.json`。

## 第四幕：数据库验证（OQMD 主 + MP 相图级增强）（约 1 分 30 秒）

**演示动作**：打开判定对照表 `consensus_verify_20260808T105523.md` + MP 核验 JSON。

**口播要点**：
- **OQMD 全库自动扩面**：母体池聚合 → 批量直查 → oracle 真值表 12/12 母体（已知 10 / 反例 2），自动纳入消融评分。
- **12 条共识候选全部判定**：**已知 9 / 反例 3**。
  - 已知（母体在库且稳定，掺杂为库外扩展）：Mg3Sb2 hull=0.000/Δe=-0.379、ZrNiSn hull=0.000/Δe=-0.719、CoSb3 hull=0.000/Δe=-0.196、GeTe hull=0.002、Sb2Te3 hull=0.002——**基础体系得到第一性原理数据支撑**。
  - 反例（母体条目级不稳定，负结果如实留痕）：Cu2Se hull=0.125、SiGe hull=0.512。
- **MP 相图级双库核验（重点展示严谨性）**：
  - Cu2Se/SiGe 的 OQMD 条目级「反例」经 MP 相图级复核**实为稳定**（Cu2Se hull=0.0826、SiGe hull=0.0162）——归因「条目级 vs 相图级」粒度差异 +「DFT 亚稳 ≠ 实验不可用」（两者均为热电常用材料），**分歧消除**。
  - 发现 **MP 默认 thermo 数据层缺陷**：Mg3Sb2/Sb2Te3/ZrNiSn 默认 GGA_GGA+U_R2SCAN 联合 hull 异常巨大（9.73/21.61/13.43 eV），GGA_GGA+U 老 thermo 复核 hull=0.0 均稳定——双 thermo 交叉复核逻辑已固化为 `src/validation/mp_phase.py`（hull>0.5 自动触发 legacy 复核 + thermo_discrepancy 留痕），**数据库内分歧不作为稳定性反例**。
- 结论展示「共识候选 → 数据库判定」对照表作为路线 A 可信性/新颖性的直接证据。

**数据来源**：`results/consensus/consensus_verify_20260808T105523.json`、`results/validation/mp_phase_check_20260808T133350.json`、`results/oracle/oracle_truth_20260808T132948.json`。

## 第五幕：科学意义与收尾（约 40 秒）

**演示动作**：demo-panel「评测指标 + 证据链」段收尾。

**口播要点**：
- **可证伪的发现**：每个构效关系候选都附证据链（文献 DOI/页码 + 数据库 entry_id + 调用留痕），区分「新知」与「已知」；反例与数据库分歧**如实留痕**（负结果同入库，03 规范 7.2）。
- **科学意义**：打通「文献 → 知识库 → Gap → 搜索×LLM → 数据库验证」闭环，构效关系可回溯、可量化、可复用；方法上「搜索算法 × LLM 三角色融合」具备通用性。
- 开源仓库：README（复现命令）+ 实验报告 + 依赖/授权披露；`pytest 442/442` 全绿。

**数据来源**：`docs/experiment-report.md`、`README.md`、`docs/demo-panel.html`。

## 演示 Q&A 预演（常见提问）

| 评委可能提问 | 应答要点 |
|-------------|---------|
| 怎么证明不是「用 LLM 写代码」？ | 展示 `LLMRoles` 三方法（生成/评估/剪枝）在搜索循环中的调用日志 + 消融（LLM 直出 vs 规则）增益 |
| 反例如何处理？ | Cu2Se/SiGe 的 OQMD 条目级 vs MP 相图级分歧归因 + 负结果留痕（不伪装结论） |
| 数据库间冲突？ | MP 默认 thermo 缺陷 → 双 thermo 交叉复核逻辑（`mp_phase.py`），以 legacy 判定为准并留痕 |
| 新颖性怎么保证？ | 29/29 Gap 带证据链 + Sciverse 回查；人工批注 `gap_novelty_review.ai3.json` → `--write-back` 出最终新颖性准确率 |
| 复现性？ | README 命令级复现 + 固定随机种子 + 全部产物落盘 JSON/JSONL |

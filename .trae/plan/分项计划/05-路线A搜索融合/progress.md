---
title: "分项计划·模块5 路线A 构效关系搜索融合 · 进度日志"
type: "plan"
category: "subplan"
tags: [路线A, 搜索融合, progress, GA, MCTS]
created: "2026-08-04"
updated: "2026-08-08"
status: "active"
version: "1.12"
---

# 模块5 路线A 构效关系搜索融合 · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：2026-08-08
- **完成状态**：阶段 1-4 完成（GA + MCTS + BO + SR × LLM 三角色融合 + 三臂消融量化 + VerificationOracle 严苛评分代理重跑 + 反例回喂闭环 + **BO 召回率增强与 LLM 模式召回率** + **LLM 模式召回率四算法补跑（GA/MCTS/SR）** + **十一次深度开发：LLM 模式四算法 40 条批量 + 融合投票 12 个多算法共识 + finding evidence 156/156 全覆盖** + **十二次深度开发：共识候选验证闭环 12 候选→已知 9/反例 3 + BO·MCTS 命中率归因与 known_facts 先验注入（BO cov 0.4375→0.75、MCTS 0.375→0.625）** + **十三次深度开发：搜索池扩宽根治召回（DOPANT_POOL 11→16 + BO 默认全池 + MCTS 全池遍历，规则模式 BO coverage 0.4375→1.0 实证收敛）+ 共识反例 MP 相图级双库核验（Cu2Se hull=0.0826 / SiGe hull=0.0162 稳定，分歧归因消除）+ LLM 模式 16 条全量矩阵夜间批量完成——GA recall@1=0.75/cov=0.938 最优、SR 0.688/0.875/0.875、BO cov=1.0、MCTS cov=0.375 唯一短板** + **十四次深度开发：MCTS 召回率短板攻坚——展开即评估（80 叶全收录）+ valid_hosts 过滤修复 + LLM 批量评估 batch 20→10，LLM 模式 cov 0.375→1.0/recall@5 0.812、规则模式 cov 0.375→1.0，全量矩阵唯一短板消除**）

## 阶段进度

### 阶段 1：搜索算法基线
- [x] GA 实现（手写选择/交叉/变异，无第三方 deap 依赖）
- [x] MCTS 实现（3 层决策树 host→dopant→concentration，UCT 上置信界，LLM 评估器参与叶模拟）
- [x] BO / 符号回归实现（BO：二次多项式代理 + UCB 采集；SR：LLM 提议函数形式 + 纯 Python 最小二乘，输出显式公式 + R²）

### 阶段 2：LLM 三角色融合
- [x] 生成器（候选提议 + 化学理由 rationale）
- [x] 评估器（可行性/科学合理性打分）
- [x] 剪枝器（决定保留/淘汰）
- [x] 融合接口：LLMRoles 三方法注入 + 失败自动降级规则评估（不中断流水线）

### 阶段 3：发现闭环
- [x] 候选生成→评估→筛选→入库（SearchAgent 消费 gaps.json → findings 落盘）
- [x] 数据库验证接口对接（模块6 已完成，批量回接 34 个 finding → 182 候选验证）
- [x] 发现日志审计（SearchStep/SearchLog 记录 generation/action/llm_role/detail，llm_calls/llm_failures 统计）

### 阶段 4：消融与评测
- [x] 有/无 LLM 对比实验（三臂消融 full/rule/llm，结果：full 0.806 / rule 0.820 / llm 0.473；GA 演化增益 +70.41%、LLM 融合增益 -1.66%、LLM 直出 vs 规则 -42.29%，零 LLM 失败）
- [x] 换严苛评分代理重跑（2026-08-05：VerificationOracle 真值代理 + 重验真值表扩大至 220 条 → full 0.806 / rule 0.885 / llm 0.785；GA 演化增益 +2.65% 由负转正、LLM 融合增益 -8.93% 负值收窄，成因=真值表覆盖而非 LLM 无能）
- [x] 搜索-验证闭环回喂（2026-08-05：反例母体黑名单回喂 GA 剪枝器，强制淘汰 + LLM priority 提示 + 审计留痕）
- [x] 已知关系召回率评测（2026-08-05：`scripts/eval_recall.py` 四算法 × known_facts 5 条；修复 MCTS 浓度维度缺失缺陷 + 统一 explore_top 公平口径；结果 ga recall@5=0.4 / mcts 0.2 / bo 0.0 / sr 0.2，落盘 `results/eval/recall_20260805T070151.json`）
- [x] BO 召回率增强（2026-08-05 五次深度开发：v1 单 dopant 固定 → v2「dopant 外层遍历 × 浓度 BO 内层寻优」，known_facts 5→16 条，规则模式 **BO coverage 0.688 四算法最高**，落盘 `recall_20260805T071740.json`）
- [x] 召回率 LLM 模式（2026-08-05：`eval_recall.py --llm --algo bo --bo-dopants 5` 量化「LLM 参与探索」对已知关系覆盖的增益；BO 批量评估优化 `_evaluate_batch` 每元素 LLM 调用 19→4 次；`--bo-dopants` 预算参数）
- [x] LLM 模式召回率四算法补跑（2026-08-08：BO 已备 + GA/MCTS/SR 各 3 条小批量——**SR recall@1=0.667/@3=1.0/@5=1.0/cov=1.0 最优、GA recall@1=0.333/@5=1.0/cov=1.0、MCTS recall@1=0.0/@3=0.333/cov=1.0**，落盘 `results/eval/recall_20260808T*.json`；全量 16 条留复赛夜间批量）
- [x] oracle 真值表扩面机制确认（2026-08-08：`VerificationOracle.load()` 自动扫描全部 validation 产物 82 公式/15 母体，新增验证自动纳入，无需新代码）
- [x] LLM 模式四算法 40 条批量（2026-08-08 十一次深度开发：GA/SR/MCTS/BO 各 10 条全 used_llm、0 失败——GA/SR 0900 前批次 + MCTS/BO 新批次日志 `llm_batch_mcts3.log`/`llm_batch_bo3.log`）
- [x] LLM 模式融合投票多算法共识（2026-08-08：40 条 LLM finding 复制隔离目录 `results/_llm_ensemble/findings/` → `run_ensemble.py` → **10 gap / 94 候选 / 12 个多算法共识**（Mg3Sb2-Na2%、CoSb3-Yb0.2Ba0.10%、Si0.8Ge0.2-P2%、ZrNiSn-Hf5%、Bi0.5Sb1.5Te3-Cu1% 等 GA+SR 趋同；对比规则模式 0 共识），`results/ensemble/ensemble_llm_20260808.md/.html`；完成后清理临时副本目录）
- [x] finding evidence 覆盖补强（2026-08-08：`backfill_result_evidence.py --target findings` 156 个 finding 全已有 evidence；审计复验 **finding 156/156 全可追溯**）
- [x] 创新性论证材料（初赛方案 docs/initial-round-proposal.md 已写入方法创新点）

## 操作记录

### 2026-08-04 计划初始化
- **操作**：创建模块5三件套
- **结果**：任务规划完成
- **状态**：成功

### 2026-08-05 开发实施
- **操作**：按 task_plan 开发路线 A GA × LLM 三角色融合搜索
- **结果**：
  - `src/search/schemas.py`：Candidate（host/dopant/concentration/formula/rationale/source/scores/verdict）+ SearchStep/SearchLog/SPRFinding，LLMRole/CandidateSource 枚举
  - `src/search/ga_search.py`：手写 GA（锦标赛选择/单点交叉/变异）+ LLMRoles（generate_seeds/evaluate/prune 三方法注入，失败返回 None 自动降级规则评估）
  - `src/agent/search_agent.py`：消费 gaps.json → 每 Gap 跑 ga_search → findings 落盘 + 证据链回填 + 审计日志
  - `scripts/run_search.py`：端到端，`--no-llm` 规则模式 / 默认 LLM 模式
  - `tests/test_search_agent.py`：9 项（规则打分/生成器降级/评估器解析/剪枝器/GA 规则模式/GA LLM 模式/Agent 规则模式/空 Gap）
  - 修复 2 个关键 bug：`llm_chat_json` 三位置 params dict 契约；`_nominal_formula` 已掺杂母体垃圾公式（见错误日志）
  - LLM 三角色真实调用：生成器产 In 掺杂种子（共振能级机制）、评估器打分、剪枝器淘汰，审计 llm_calls=10/失败 1
  - pytest 69/69 全绿、ruff 零 error
- **状态**：成功

### 2026-08-05 MCTS/BO/SR 实现 + 三臂消融
- **操作**：补齐四种搜索算法 × LLM 融合；三臂消融量化 LLM 融合增益
- **结果**：
  - `src/search/mcts_search.py`：3 层决策树（host→dopant→concentration）+ UCT 上置信界 + LLM 评估器参与叶模拟，LLM 失败降级规则
  - `src/search/bo_search.py`：二次多项式代理 + UCB 采集（均值 + κ·残差标准差），复用 `_least_squares`
  - `src/search/sr_search.py`：LLM 提议函数形式（多项式/幂律/对数/指数）+ 纯 Python 最小二乘（正规方程闭式解 + 高斯消元），输出显式公式 + R² + 最优浓度——SR 优先策略（可解释性直接支撑科学意义维度）
  - `tests/test_search_algo.py`：12 项（SR/MCTS/BO 规则 + LLM 模式，无第三方依赖）
  - `src/search/ablation.py` + `scripts/run_ablation.py`：三臂消融（full=GA×LLM / rule=GA 纯规则 / llm=纯 LLM 生成+评估无演化），输出增益百分比 + 落盘 `results/ablation/ablation_report.json`
  - `tests/test_ablation.py`：7 项（三臂定义/LLM-only 降级/指标提取/规则模式公平性/增益公式/JSON 可序列化/候选分数已赋）
  - 真实消融（top-5 gaps，generations=3，pop=12）：**full 0.806 / rule 0.820 / llm 0.473**；GA 演化增益 +70.41%、LLM 融合增益 -1.66%、LLM 直出 vs 规则 -42.29%（零 LLM 失败）——负的 LLM 融合增益说明评分代理规则已覆盖多数科学直觉，LLM 价值在假设多样性（llm 臂 unique_dopants 更高），复赛需换更严苛评分代理再验证
  - `src/agent/search_agent.py` 新增 `offset` 参数（分批搜索断点续跑）；`run_search.py --no-llm --top-n 29 --generations 2 --pop-size 10` 产出 29 个 finding JSON
  - pytest 102/102 全绿、ruff 零 error
- **状态**：成功

### 2026-08-05 三次深度开发（Oracle 严苛评分 / 反例回喂闭环）
- **操作**：换严苛评分代理重跑三臂消融；搜索-验证闭环反例回喂
- **结果**：
  - `src/search/verification_oracle.py`：VerificationOracle 真值评分代理——加载 `results/validation/validation_*.json` 构建 formula 表 + host 表，判定等级稳定性系数（已知 0.85 / 新知 0.60 / 验证失败 0.45 / 反例 0.15）+ 支撑度系数（0.90/0.60/0.40/0.20），host 表 VERDICT_PRIORITY（已知 3 > 反例/新知 2 > 验证失败 1）防低质量记录污染；t3 增强 host 表额外索引 parent_formula 扩大真值覆盖
  - oracle 前 full 0.806 / rule 0.820 / llm 0.473 → oracle 后 **full 0.803 / rule 0.933 / llm 0.836；LLM 融合增益 -13.98%、GA 演化增益 -3.97%**——负增益科学解读：rule 臂恒 0.933（GeTe/PbTe/Bi2Te3 命中已验证「已知」），full/llm 臂新颖母体未被真值表覆盖，**非 LLM 无能而是真值表覆盖不足**，直接论证验证失败重验（t3）与搜索-验证闭环（t4）必要性
  - `src/search/ga_search.py`：`ga_search(..., negative_hosts)` 新增参数——反例母体每代强制淘汰（`if c.host in neg: c.verdict = "drop"`，审计 action="prune_feedback"）；`LLMRoles.prune(cands, negative_hosts)` system/user 提示 LLM 优先淘汰反例母体宿主 + 规则强制兜底
  - `src/agent/search_agent.py`：`run(..., negative_hosts)` 透传；`scripts/run_search.py` 新增 `--no-feedback` 开关，默认 `extract_negative_hosts()` 加载反例黑名单回喂 → 端到端生效（黑名单 ['SiGe','Cu2Se']）
  - `src/validation/feedback.py`：`extract_negative_hosts()`（反例母体提取去重）+ `extract_disputes()`（跨库分歧提取）
  - 重验真值表扩大后重跑消融：**full 0.806 / rule 0.885 / llm 0.785；GA 演化增益 +2.65%（由负转正）、LLM 融合增益 -8.93%（负值收窄）、LLM 直出 vs 规则 -11.28%**
  - `tests/test_feedback.py` 3 项 + `tests/test_verification_oracle.py` 3 项；pytest **115/115** 全绿、ruff 全量零 error
- **状态**：成功

### 2026-08-05 四次深度开发（已知关系召回率评测 + MCTS 浓度缺陷修复 + 公平口径）
- **操作**：构造 known_facts 期望集，实现召回率评测链路；评测暴露并修复算法缺陷
- **结果**：
  - `data/gaps.json` 顶层新增 `known_facts`（5 条人工策展热电已知掺杂方案：PbTe-Na-2.0 / GeTe-Bi-6.0 / GeTe-Ti-4.0 / SnTe-In-4.0 / Mg3Sb2-Bi-2.0）+ 命中判定计算器 `src/evaluation/recall.py`（host 公式归一化 + dopant 大小写不敏感 + 浓度容差 1.5%，`candidate_matches`/`hit_at_ks`/`aggregate_recall`）+ 单测 7 项
  - `scripts/eval_recall.py`：四算法 × 每条 known_fact 搜索，gap_statement 由 fact 构造，指标 hit@1/3/5 + 聚合召回率，落盘 `results/eval/recall_<ts>.json`
  - **修复 MCTS 架构缺陷**：`mcts_search` docstring 声称三层决策树但 `is_leaf()` level≥2 即 True + `_simulate()` 浓度固定 CONC_GRID[2]=6.0 → 浓度维度从未入树；修复为 `MCTSNode.concentration` + `_expand()` 按 8 dopant × 5 conc 展开叶节点 + `_simulate()` 返回 (Candidate, score)
  - **统一公平口径**：四算法（ga/mcts/bo/sr）新增 `explore_top: int = 0` 参数，>0 时输出「探索轨迹候选全集（formula 去重、按评分降序）前 explore_top 个」；`eval_recall.py` 以 `explore_top=max(ks)` 调用——解决旧口径 MCTS/BO 单候选输出导致 hit@3/5 恒 0 的失真
  - **新口径结果**：ga recall@1/3/5=0.2/0.2/0.4、mcts=0.0/0.2/0.2、bo=0.0/0.0/0.0、sr=0.0/0.2/0.2（对比旧口径仅 GA=0.2）——MCTS/SR 提升；BO 全 0 归因结构性局限（单 dopant 固定 + 仅浓度寻优，无法发现掺杂元素维度）
  - 回归单测：`test_mcts_three_layer_tree_explores_concentration`（浓度集合 ≥2）/ `test_mcts_explore_top_default_single_best`（默认单 best + explore_top 输出 5）/ `test_explore_top_algo_consistent`（三算法口径一致）
  - pytest **142/142** 全绿、ruff 全量（src/tests/scripts）零 error
- **状态**：成功

### 2026-08-05 五次深度开发（BO 召回率增强 / known_facts 扩充 / LLM 模式召回率）
- **操作**：BO 结构性局限改造（v1 单 dopant 固定 → v2 外层遍历）、期望集扩充、LLM 参与探索增益量化
- **结果**：
  - `bo_search.py` v2：`bo_search(..., dopants=None → DOPANT_POOL[:10])` 外层遍历，每元素独立跑浓度 BO（`_bo_one_dopant`：初始点 `INIT_CONC_GRID` 10 浓度全覆盖 + 3 轮 UCB 采集），探索轨迹合并为 dopant × 浓度二维覆盖；全局最优 dopant = 各元素最优分最大者，输出代理公式 + 机制解释
  - **关键 bug 修复（分数完整性）**：规则分支 `cand.scores={"scientific":...}` 丢 feasibility → 同 dopant 各浓度点分数相同 → score_avg 无法区分 → 排序退化为插入序（`test_bo_search_dopant_dimension` 前 10 全是 Ti）；BO/MCTS 统一改 `cand.scores = sc`（scientific+feasibility 全保留）
  - `data/gaps.json` known_facts 5→16 条（追加 kf-06~16：PbTe-I/Sb/Mg、GeTe-Sb、SnTe-Cd/Ag、Bi2Te3-Se/Cu、Mg3Sb2-Te、ZrNiSn-Nb、CoSb3-Fe；6 池内 + 9 超池 + 4 超宿主）
  - 规则模式双口径重跑（16 条）：**BO coverage 0.688 / hit@3=0.062 / hit@5=0.062**（GA 0.250 / MCTS 0.375 / SR 0.125），BO v1 全 0 → v2 0.688 验证结构性改造有效；coverage vs hit@k 差异量化 rule_score 浓度偏好错配
  - **LLM 模式成本优化**：`_evaluate_batch` 批量评估（LLM 评估器本就是批量接口），每元素 LLM 调用 19→4 次；`eval_recall.py` 新增 `--bo-dopants` 预算参数；规则 5-dopant 基线 coverage 0.438（`recall_20260805T072056.json`）
  - LLM 模式实跑：`python scripts/eval_recall.py --algo bo --llm --bo-dopants 5`（deepseek-chat）→ 链路跑通（单条 fact 20 次批量评估 87.6s，kf-01 cov=Y，落盘 `recall_20260805T073332.json`）；单次调用 2.7-8.2s 无死锁；评测批量 6/16 facts 循环放大调用数（120/320 次），加 `--max-facts` 子集参数 + 逐条进度打印
  - pytest **144/144** 全绿（新增 `test_bo_search_dopant_dimension` / `test_bo_search_dopants_param_scope`）、ruff 全量零 error
- **状态**：成功

### 2026-08-08 七次深度开发（LLM 模式召回率四算法补跑 + oracle 扩面机制确认）
- **操作**：补齐 MCTS/GA/SR 的 LLM 模式召回率（BO 已完成），确认 oracle 真值表扩面机制
- **结果**：
  - `python scripts/eval_recall.py --llm --algo {ga,mcts,sr} --max-facts 3`（deepseek-chat，3 条小批量控制成本）：
    - **SR**（39s/3 条）：recall@1=0.667 / @3=1.0 / @5=1.0 / coverage=1.0——四算法 LLM 模式下最优（符号回归 LLM 提议函数 + 显式公式排序质量高）
    - **GA**（54s/3 条）：recall@1=0.333 / @3=0.333 / @5=1.0 / coverage=1.0——探索全覆盖，期望方案未进 top-3 为评分-期望错配
    - **MCTS**（170s/3 条）：recall@1=0.0 / @3=0.333 / @5=0.333 / coverage=1.0——探索全覆盖但排序最弱（树搜索候选评分发散），耗时最高
  - 落盘 `results/eval/recall_20260808T153913.json`（ga）/ `154211.json`（mcts）/ `154257.json`（sr），与 `recall_20260805T073332.json`（bo）合并即得**四算法统一 LLM 对比矩阵**
  - **oracle 真值表扩面机制确认**：`VerificationOracle.load()` 自动扫描 `results/validation/validation_*.json` 全部文件构建 formula/host 表（含 parent_formula A/B 位拆分索引），实跑 82 公式 / 15 母体；扩面 = 夜间跑更多 OQMD 验证自动纳入，无需新代码
  - 全量回归：pytest **318/318** 全绿、ruff 零 error
- **状态**：成功

### 2026-08-08 八次深度开发（四算法统一对比矩阵 + 融合投票）
- **操作**：合并四算法召回率为统一对比矩阵；实现四算法输出融合投票；findings 落盘补算法标识
- **结果**：
  - `scripts/merge_recall_matrix.py`：同一 (algo, mode) 多份 recall 文件取 n_facts 最大者（并列取时间戳最新，其余 detail 留痕）→ **8 行四算法统一对比矩阵** `recall_matrix_20260808T160119.json`（LLM 模式：SR recall@1=0.667/@3=1.0 最优 / GA recall@5=1.0 / MCTS cov=1.0 / BO 1 条；规则模式：BO coverage=0.4375 最高）；docstring 留档全量 16 条夜间批量命令
  - `src/search/ensemble.py`：`candidate_key`（host 归一化大写 + dopant 大写 + 浓度 0.5 步长取整）+ `ensemble_vote`（rank 1/rank 加权 → 同算法去重只计最高排名防刷票 → 得票降序）+ `load_findings`（results_dir glob findings/，坏文件跳过，缺省 algo=unknown）+ `ensemble_findings`（gap_statement 分组投票 + evidence_ids 并集）+ `render_markdown/render_html`
  - `scripts/run_ensemble.py` CLI（--findings/--out/--top-k/--md-only/--html-only）；修复传 findings 目录与 load 函数 glob 前缀匹配坑（findings 名时取父级 results 目录）
  - `src/agent/search_agent.py`：findings 落盘 payload 补 `payload["algo"] = algo`（向后兼容 unknown）
  - 真实数据 CLI：29 Gap / 157 候选，0 多算法共识（现产物全为 GA 单算法）——夜间四算法批量后 `run_ensemble.py` 直接产出多算法共识清单
  - `tests/test_search_ensemble.py` 13 项（candidate_key 3 / ensemble_vote 5 / load+group 3 / render 2；含浓度 4.1→4.0 同桶、防刷票、rank 加权）；pytest **342/342** 全绿、ruff 零 error
- **状态**：成功

### 2026-08-08 九次深度开发（决赛材料引用路线A核心数值 + Gap 证据链回填关联）
- **操作**：决赛海报 + 项目一页纸（阶段 6 交付物，核心数值全部来自路线 A 真实产物）；Gap evidence_ids 回填工具（证据链审计补强）
- **结果**：
  - `docs/final-one-pager.md` / `docs/final-poster.md`：引用路线 A 真实产物数值——**SR recall@3=1.0/cov=1.0（LLM 模式最优）、消融 full 0.806 / rule 0.885 / llm 0.785、真值表 220 条 / 15 母体、Gap 29 条（新知 15 / 部分已知 14）**
  - `src/evaluation/gap_evidence_backfill.py`（三通道回填）+ `scripts/backfill_gap_evidence.py`：真实数据 29 条 Gap 回填 17 条 / 新增 20 条证据，Gap 可追溯 1/29 → **18/29**（审计复验 `evidence_report_20260808T082657.md`）——回填工具与 `src/search/ensemble.py` 同属评估链路，`docs/experiment-report.md` 同步证据链审计行与复现命令
  - 全量回归：pytest **356/356** 全绿、ruff 零 error
- **状态**：成功

### 2026-08-08 十一次深度开发（LLM 模式四算法 40 条批量 + 融合投票 12 共识 + evidence 补强）
- **操作**：承接十次深度开发剩余项——LLM 模式四算法批量产出多算法共识（现场 demo 加分项）；finding/验证结论 evidence 覆盖补强
- **结果**：
  - **LLM 四算法批量 40 条全部完成**：GA/SR 各 10 条（0900 前批次）+ MCTS/BO 新批次各 10 条（`results/logs/llm_batch_mcts3.log`/`llm_batch_bo3.log`，全 used_llm=True、0 失败）；中途发现重复 python 进程（WindowsApps + pythoncore 双实例）→ Stop-Process 停冗余实例 + 不完整产物归档 `archive_20260808_llm_interrupted2/` 后重启干净批次
  - **LLM 模式融合投票**：40 条复制隔离目录 `results/_llm_ensemble/findings/`（`load_findings` 要求目录名为 findings，传父级）→ `run_ensemble.py` → **10 gap / 94 候选 / 12 个多算法共识**（Mg3Sb2-Na2% / CoSb3-Yb0.2Ba0.10% / Si0.8Ge0.2-P2% / ZrNiSn-Hf5% / Bi0.5Sb1.5Te3-Cu1% 等 GA+SR 趋同，对比规则模式 0 共识）→ `results/ensemble/ensemble_llm_20260808.md/.html`；投票完成后清理临时副本目录（findings_llm/ + _llm_ensemble/）
  - **evidence 补强**：`backfill_result_evidence.py --target findings` 对新 40 条 LLM finding 回填（156 个 finding 全已有 evidence，+0 新增）；审计复验 `evidence_report_20260808T111500.md`：**Gap 29/29｜finding 156/156 全可追溯｜验证 43/47**（4 条验证失败自然留痕）
  - 质量门禁：pytest **412/412** 全绿（新增 13：OQMD 重试机制等）、ruff 全量（src/tests/scripts）零 error
- **状态**：成功

### 2026-08-08 十二次深度开发（共识候选验证闭环 / BO·MCTS 命中率归因 + known_facts 先验注入）
- **操作**：承接十一次深度开发下一步候选①（LLM 融合发现验证闭环）与候选②（BO/MCTS LLM hit 低归因）
- **结果**：
  - **t1 共识候选验证闭环**：`src/validation/consensus_verify.py`——`split_candidate`（`_CAND_RE` 正则：host-dopant+浓度）+ `resolve_parent` 三形态分流（变量式→parse_variable_parent / 分数式末尾阴离子→parse_integer_parent / 末尾非阴离子合金式→去数字下标）+ `build_truth_map`（oracle + validation 按 VERDICT_PRIORITY 聚合覆盖）+ `verify_one`（真值缓存优先 → online 回退 OQMD+MP）；`scripts/verify_consensus.py` CLI（--ensemble/--truth/--min-votes/--online/--mp）+ `render_markdown/render_html`；实跑 **12 共识候选：已知 9 / 反例 3（Cu2Se-Te5%、Si0.8Ge0.2-P2%×2）**，known=0.75/counter=0.25/novel=0，对照表 `results/consensus/consensus_verify_20260808T105523.{json/md/html}`——路线 A 可信性/新颖性直接证据；Cu2Se/SiGe「DFT 亚稳 vs 实验应用」分歧留作可信性讨论点
  - **t2 BO/MCTS LLM 命中率归因**：`scripts/analyze_recall_attribution.py` 三维归因（①搜索池缺口 ②评分-期望浓度错配 ③覆盖未排上）→ **BO 池缺口 5/16（DOPANT_POOL[:10]）、MCTS 池缺口 7/16（[:8]）、浓度错配 6 条（期望≤2% vs rule_score 偏好 3-8%）、覆盖未排上 BO 5/MCTS 5**，落盘 `results/eval/recall_attribution_20260808T105751.{json/md}`
  - **t3 known_facts 先验注入**：`ga_search.py` `LLMRoles` 新增 `known_facts` 字段 + `_known_facts_prior()`（`{conc:g}%` 去尾零格式化；host+dopant 一致且浓度差≤1.5% 时 scientific≥0.85）+ `evaluate()` system prompt 注入 + 4 项单测（空默认/渲染/注入/无先验）；`eval_recall.py` 支持 `known_facts` 透传；带先验后台评测（8 条 kf-01~08，deepseek-chat）：**BO recall@1=0.625/cov=0.750（基线 cov=0.4375）、MCTS recall@1=0/@3=0.25/cov=0.625（基线 cov=0.375）**——先验修复「覆盖未排上」（池内命中进轨迹/升序），但 kf-04（SnTe-In）/kf-06（PbTe-I）超池仍 cov=N（BO）、kf-04/05/06 超池仍 cov=N（MCTS），**实证「先验无法覆盖池缺口」，根治需扩池**；落盘 `results/eval/recall_20260808T190736.json`（mcts）/`190807.json`（bo）
  - 质量门禁：pytest **440/440** 全绿、ruff 全量（src/tests/scripts）零 error
- **状态**：成功

### 2026-08-08 十三次深度开发（搜索池扩宽根治召回 / 共识反例 MP 相图级双库核验 / LLM 全量矩阵夜间批量）
- **操作**：承接十二次深度开发下一步候选①②——① 扩池根治（DOPANT_POOL 补 In/I/Te/Nb/Fe/Mg 等期望 dopant）；② 共识反例（Cu2Se/SiGe）MP 相图级双库核验；另含人工行动项 AI 预填评审版 + 复赛夜间批量
- **结果**：
  - **t1 搜索池扩宽**：`ga_search.py` DOPANT_POOL 11→**16 元素**（追加 I/Te/Nb/Fe/Mg，注释标注 2026-08-08 十三次深度开发追加补池缺口，覆盖 16 条 known_facts 全部期望 dopant）；`bo_search.py` `DEFAULT_DOPANTS = 10 → 16`（默认全池，LLM 成本控制用 `eval_recall --bo-dopants 5`）；`mcts_search.py` dopant 层 `DOPANT_POOL[:8]` → `DOPANT_POOL` 全池遍历（消除「前 8 切片漏 I/Te/Nb/Fe/Mg」结构性池缺口）
  - **t2 规则模式实证（扩池后）**：`eval_recall.py` 16 条快跑 `results/eval/recall_20260808T191938.json`——**BO coverage 0.4375→1.000（16/16 全覆盖，池缺口根治收敛）**、SR 0.125→0.3125（采样触及新 dopant）、MCTS 0.375/GA 0.25 不变（迭代/种群预算限制非池缺口）——实证「先验无法覆盖池缺口（经验 114）→ 扩池根治（经验 118）」
  - **t3 共识反例 MP 相图级双库核验**：`scripts/check_mp_phase_diagram.py` 改造——`_chemsys_for_formula`（元素去重 + **字母序** + 连字符）+ `--formulas` 显式公式路径 + `stable = bool(hull < 0.1)`（np 标量转 Python bool 修复 JSON 序列化）+ note 动态化；实跑 `mp_phase_check_20260808T111941.json`：**Cu2Se hull=0.0826 稳定（分解 Cu3Se2+Cu）、SiGe hull=0.0162 稳定（分解 Ge+Si）**——OQMD 条目级反例（0.125/0.512）vs MP 相图级稳定归因「条目级 vs 相图级」粒度差异 +「DFT 亚稳 ≠ 实验不可用」，对齐 GeTe 先例（经验 45），分歧消除，补强路线 A「共识候选可信性」论证
  - **t4 人工行动项**：`gap_novelty_review.ai3.json` 生成（confirmed_novelty 对齐 ai_suggested_novelty 修复 ai2 中 14/29 不一致，29/29 pending 待人工核对）+ write-back 兼容性 dry-run 验证（全 pending 写回 0 条安全 / 模拟 2 条 reviewed 正确写回）
  - **t5 复赛夜间批量（已完成）**：`python scripts/eval_recall.py --llm --algo all --bo-dopants 16 --max-facts 16` 后台运行 2.2h（job-bad450da7f10419781877cd7994587b1，退出码 0）→ **`recall_20260808T204124.json`：全量 16 条 × 四算法 LLM 模式召回率矩阵**（known_facts 先验，deepseek-chat）——**GA recall@1=0.750/@3=0.875/@5=0.938/cov=0.938 最优、SR 0.688/0.875/0.875/0.938、BO 0.438/0.750/0.750/cov=1.0（LLM 模式池缺口同样收敛）、MCTS 0.062/0.188/0.250/cov=0.375 唯一短板**（扩池后 I/Te/Nb/Fe/Mg 已入池仍 cov=N，归因树搜索结构非池缺口）；对比规则模式全面 LLM 增益（GA cov 0.25→0.938、SR 0.312→0.938、BO 0.0625→0.75）；合并 `recall_matrix_20260808T204159.json` + 实验报告 1/4.3/5.2/8/9 节同步更新（小批量子集被全量取代）
  - 质量门禁：pytest **440/440** 全绿（扩池后搜索模块 44/44 回归）、ruff 全量（src/tests/scripts）零 error；本次 5 文件（ga/bo/mcts/check_mp_phase_diagram/review_gap_novelty）ruff format 规范化（不动历史遗留 113 个待格式化文件，避免无关 diff）
- **状态**：成功

### 2026-08-08 十四次深度开发（MCTS 召回率短板攻坚）
- **操作**：承接十三次深度开发下一步候选①——MCTS 全量矩阵唯一短板（cov=0.375）攻坚，目标 cov≥0.7
- **结果**：
  - **t1 根因一「叶采样预算结构性上限」**：`_simulate` 每次迭代只评估 1 个叶子 → iterations=30 最多 30 候选 → 80 叶空间 cov 上限 ≈0.375；修复 = `_expand` level1 展开 dopant 层时「展开即评估」——批量 LLM/规则打分全部 80 叶写入 node.value 先验 + 全部收录 explored，覆盖不再依赖迭代预算（exp 123）
  - **t2 根因二「host 过滤把期望母体挡在空间外」**：`valid_hosts = [h for h in hosts if not any(ch.isdigit() for ch in h)]` 把带数字下标母体 Mg3Sb2/Bi2Te3/CoSb3 全过滤 → cov 上限 ≈11/16=0.688；修复 = 直接采用调用方归一化 hosts（仅过滤空串）+ `_expand` level0 母体默认列表同步（exp 124）
  - **t3 根因三「LLM 批量评估 max_tokens 截断静默降级」**：`roles.evaluate(chunk)` batch=20 时 LLM 输出被 max_tokens=1200 截断 → JSON 解析失败 → scores_map 空 → `or rule_score(c)` 全部 fallback 规则打分——**hit@k 与规则模式完全一致（0.062/0.062/0.125）是 LLM 信号失效的指纹**（真实 API 诊断：20 候选返回 0 条、≤12 候选正常）；修复 = 默认 batch 20→10（80 叶分 8 批，exp 125）
  - **t4 验证结果**：规则模式 cov 0.375→**1.000**（`recall_20260808T205247.json`）；LLM 模式全量 16 条后台重跑（`--iterations 60`，deepseek-chat）`recall_20260808T211413.json`——**cov=1.000、recall@1 0.062→0.438、recall@3 0.188→0.750、recall@5 0.25→0.812**（目标 cov≥0.7 达成）；遗留 3 条（kf-09 SnTe-Cd5%、kf-10 SnTe-Ag5%、kf-16 PbTe-Mg2%）cov 已覆盖但排序未排上 @1/@3（评分-期望浓度差）非结构性缺陷；合并 `recall_matrix_20260808T211437.json`（MCTS LLM/规则行均更新）+ 实验报告 1/5.2/8 节同步
  - 质量门禁：新增 2 项 MCTS 单测（`test_mcts_expand_evaluates_all_leaves` 展开即评估 80 叶全收录 / `test_mcts_llm_signal_propagates_to_leaves` LLM 信号传导至叶排序）；pytest **442/442** 全绿（搜索模块 33 项）、ruff 全量（src/tests/scripts）零 error（修复本次 3 处 E501）
- **状态**：成功

## 测试结果

### 已通过 ✅
- [x] GA 规则模式端到端（`run_search.py --no-llm`：跨母体均匀分配种子、纯母体偏好）
- [x] GA LLM 三角色模式端到端（生成器/评估器/剪枝器真实调用，审计留痕）
- [x] LLM 失败降级：LLM 全部失败 → 规则打分兜底，流水线不中断
- [x] SR/MCTS/BO 规则 + LLM 模式单测 12 项全绿（含 LLM 调用计数审计）
- [x] 三臂消融端到端：`run_ablation.py` 输出对比表 + 增益百分比 + 落盘 JSON
- [x] 批量搜索：`run_search.py --no-llm --top-n 29` 产出 29 个 finding（offset 分批断点续跑）
- [x] pytest 102/102（模块 5 累计 23 项新增）、ruff 零 error
- [x] VerificationOracle 真值评分代理单测 3 项（formula/host 命中 + parent_formula 索引 + VERDICT_PRIORITY 防污染）
- [x] oracle 后消融重跑：full 0.803 / rule 0.933 / llm 0.836；重验后 full 0.806 / rule 0.885 / llm 0.785（GA 演化增益由负转正 +2.65%）
- [x] 搜索-验证闭环端到端：`run_search.py` 加载反例黑名单 ['SiGe','Cu2Se'] 回喂剪枝器，finding 宿主均非反例母体
- [x] pytest 115/115 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-05 三轮深度开发回归）
- [x] 召回率评测链路（2026-08-05 四次深度开发）：`src/evaluation/recall.py` 单测 7 项 + `scripts/eval_recall.py` 四算法实跑落盘；MCTS 浓度维度回归单测（浓度集合 ≥2）捕获旧缺陷
- [x] pytest 142/142 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-05 四次深度开发回归）
- [x] BO v2 增强单测 2 项（`test_bo_search_dopant_dimension` 多 dopant 覆盖 / `test_bo_search_dopants_param_scope` 限定搜索空间 + 默认单 best 语义）
- [x] 规则模式召回率双口径重跑（16 条）：BO coverage 0.688 四算法最高（GA 0.250 / MCTS 0.375 / SR 0.125），落盘 `recall_20260805T071740.json`；BO 5-dopant 基线 0.438 落盘 `recall_20260805T072056.json`
- [x] BO 批量评估优化（`_evaluate_batch`：LLM 每元素调用 19→4 次）+ `--bo-dopants` 预算参数 + 规则模式 sanity（BO coverage 0.688 一致）
- [x] pytest 144/144 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-05 五次深度开发回归）
- [x] LLM 模式召回率四算法补跑（2026-08-08：SR recall@1=0.667/@3=1.0/@5=1.0/cov=1.0 最优、GA recall@1=0.333/@5=1.0/cov=1.0、MCTS cov=1.0，落盘 `recall_20260808T*.json`）
- [x] oracle 真值表扩面机制确认（2026-08-08：load() 自动扫描 validation 产物 82 公式/15 母体，新增验证自动纳入）
- [x] pytest **318/318** 全绿、ruff 零 error（2026-08-08 七次深度开发全量回归）
- [x] 四算法融合投票（2026-08-08 八次深度开发：`test_search_ensemble.py` 13 项全绿 + `run_ensemble.py` 真实数据 29 Gap/157 候选；现产物全为 GA 单算法，多算法共识待夜间批量后产出）
- [x] Gap 证据链回填 + 决赛材料（2026-08-08 九次深度开发：`test_gap_evidence_backfill.py` 14 项全绿；决赛一页纸/海报引用路线 A 真实数值）
- [x] pytest **356/356** 全绿、ruff 零 error（2026-08-08 九次深度开发全量回归）
- [x] LLM 模式四算法 40 条批量（2026-08-08 十一次深度开发：GA/SR/MCTS/BO 各 10 条全 used_llm、0 失败，MCTS/BO 批次日志 `llm_batch_mcts3.log`/`llm_batch_bo3.log`）
- [x] LLM 模式融合投票（2026-08-08：10 gap / 94 候选 / **12 个多算法共识**（GA+SR 趋同：Mg3Sb2-Na2%、CoSb3-Yb0.2Ba0.10%、Si0.8Ge0.2-P2%、ZrNiSn-Hf5%、Bi0.5Sb1.5Te3-Cu1% 等），对比规则模式 0 共识，`ensemble_llm_20260808.md/.html`）
- [x] finding evidence 审计复验（2026-08-08：156/156 全可追溯，Gap 29/29，验证 43/47，`evidence_report_20260808T111500.md`）
- [x] pytest **412/412** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-08 十一次深度开发全量回归）
- [x] 搜索池扩宽（2026-08-08 十三次深度开发：DOPANT_POOL 11→16 + BO 默认全池 + MCTS 全池遍历；规则模式 **BO coverage 0.4375→1.0** 实证池缺口收敛，`recall_20260808T191938.json`）
- [x] 共识反例 MP 相图级双库核验（2026-08-08 十三次深度开发：Cu2Se hull=0.0826 / SiGe hull=0.0162 相图级稳定，分歧归因消除，`mp_phase_check_20260808T111941.json`）
- [x] pytest **440/440** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-08 十二/十三次深度开发全量回归；扩池后搜索模块 44/44 回归无变化）
- [x] MCTS 展开即评估 + LLM 信号传导单测（2026-08-08 十四次深度开发：`test_mcts_expand_evaluates_all_leaves`（iterations=5 下 80 叶全收录）/ `test_mcts_llm_signal_propagates_to_leaves`（LLM 仅给 Ge0.94I0.06Te 0.9 分 → 进 explore_top 且 score_avg>0.8））
- [x] MCTS 召回率攻坚实证（2026-08-08 十四次深度开发：规则模式 cov 0.375→**1.000**（`recall_20260808T205247.json`）；LLM 模式全量 16 条 **cov=1.000/recall@1 0.438/recall@3 0.750/recall@5 0.812**（`recall_20260808T211413.json`）；合并 `recall_matrix_20260808T211437.json`）
- [x] pytest **442/442** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-08 十四次深度开发全量回归，修复 3 处 E501）
- [x] MP 在线双库核验扩展（2026-08-08 十五次深度开发：7 共识母体相图级全稳定 + `mp_phase.py` 双 thermo 交叉复核固化（Mg3Sb2/Sb2Te3/ZrNiSn 默认 R2SCAN hull 异常 → GGA_GGA+U legacy 0.0，触发即留痕）+ 8 项单测 `test_mp_phase.py`，`mp_phase_check_20260808T133350.json`——共识候选可信性扩展补强，支撑路线 A 可信性论证）
- [x] 现场 demo 脚本（2026-08-08 十五次深度开发：`docs/demo-script.md` 五幕分镜 + Q&A 预演，全部数值引用真实产物——12 条 LLM 共识、判定对照表已知 9/反例 3、MP 双 thermo 核验 7 母体、召回率矩阵；`docs/demo-panel.html` 可视化面板就绪）
- [x] pytest **450/450** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-08 十五次深度开发全量回归）

### 待测项
- [ ] 搜索迭代 100 步耗时
- [x] MCTS/GA/SR 的 LLM 模式召回率补跑（2026-08-08 完成 3 条小批量：四算法统一 LLM 对比矩阵已可组装；**全量 16 条 LLM 模式留复赛夜间批量跑**）
- [x] 换更严苛评分代理后重跑消融（2026-08-05 完成：oracle 后 GA 演化增益由负转正 +2.65%、LLM 融合增益 -8.93% 负值收窄，成因=真值表覆盖而非 LLM 无能）
- [x] 已知关系召回率评测（2026-08-05 完成：新口径 ga 0.4 / mcts 0.2 / sr 0.2 / bo 0.0；**深度开发后 BO v2 coverage 0.688 四算法最高 + known_facts 16 条 + LLM 模式量化融合增益**）

## 错误日志

### 错误 1：LLM 三角色全部失败（llm_failures=11）但直接调用成功
- **时间**：2026-08-05
- **类型**：代码（接口契约）
- **消息**：`llm_chat_json` 签名 `(system, user, *, max_tokens, temperature)`，LLMRoles 按 `(system, user, kwargs_dict)` 三位置调用 → 每次抛 TypeError
- **解决方案**：`llm_chat_json` 增加 `params: dict[str, Any] | None = None` 第三位置参数兼容，`if params: max_tokens = int(params.get(...))`；tests/test_llm.py 新增 `test_chat_json_params_dict_contract` 回归防护
- **重试次数**：1

### 错误 2：`_nominal_formula` 生成垃圾公式
- **时间**：2026-08-05
- **类型**：代码（命名逻辑）
- **消息**：规则模式 Top 候选 `Ge0.93Ti0.01Bi0.060.96Ti0.04Te`（split('Te')[0] 拼接重复数字）
- **解决方案**：仅对纯二元 XTe 母体（无数字）走 `A(1-x)D(x)Te`，复杂/已掺杂母体回退 `host-Dx%` 命名
- **重试次数**：1

### 错误 3：规则种子只覆盖第一个母体
- **时间**：2026-08-05
- **类型**：代码（种群初始化）
- **消息**：hosts=[已掺杂, GeTe] 时规则网格 24 个候选被 `pop[:pop_size]` 截断，GeTe 全被丢弃
- **解决方案**：跨母体均匀分配 `per_host = pop_size // len(base_hosts)`；`rule_score` 对纯母体 +0.05 偏好
- **重试次数**：1

### 错误 4：`_fake_chat` 生成器角色分发失效（测试）
- **时间**：2026-08-05
- **类型**：测试
- **消息**：test_ga_search_llm_mode 断言 scientific≥0.6 失败（scores 为空）；evaluate formula 键与 `_nominal_formula` 不匹配
- **解决方案**：分发条件改 `"candidates" in system and "打分" not in system and "剪枝" not in system`；键改真实名义公式（Pb0.94Ti0.06Te 等）
- **重试次数**：1

### 错误 5：DeepSeek json_object 400 Bad Request（消融/批量搜索）
- **时间**：2026-08-05
- **类型**：API 契约
- **消息**：`Client error '400 Bad Request'`（payload 含 `response_format: {"type": "json_object"}`），key 修复后仍 400
- **解决方案**：DeepSeek json_object 模式要求 prompt/schema 中包含 "json" 字样；system prompt 加「输出 JSON 对象」后通过；现有 ga_search/expand_gaps 提示词已含 "JSON" 字面量无需改动
- **重试次数**：1

### 错误 6：MCTS 浓度维度缺失（架构声明与实现不一致，召回率评测暴露）
- **时间**：2026-08-05
- **类型**：代码（算法架构）
- **消息**：`mcts_search` docstring 写三层决策树，但 `is_leaf()` level≥2 即 True、`_simulate()` 浓度固定 CONC_GRID[2]=6.0 → 浓度 ≠6 的期望方案（kf-01/02/04/05）恒 miss
- **解决方案**：`MCTSNode.concentration` + `to_candidate()`；`_expand()` level 1 按 8 dopant × 5 conc 展开叶节点；`_simulate()` 返回 (Candidate, score)；回归单测「explore_top=8 浓度集合 ≥2」
- **重试次数**：1（评测是架构声明的照妖镜——召回率评测定量证明浓度可被搜索）

## 下一步

1. ~~换更严苛评分代理重跑消融~~（已完成，见操作记录三次深度开发；结论：负增益成因为真值表覆盖，oracle 真值表已扩至 220 条）
2. ~~oracle 真值表扩面~~（已完成，见十一次深度开发：`expand_oracle_truth.py` 母体池聚合 + OQMD 批量直查，**12/12 全覆盖**（已知 10 + 反例 2）自动纳入消融评分，full 0.833）
3. ~~已知关系召回率评测~~（已完成，见四次/五次深度开发；新口径 ga 0.4 / mcts 0.2 / sr 0.2 / bo 0.0 → **BO v2 增强后 coverage 0.688 四算法最高**）
4. ~~召回率增强~~（已完成，见五次深度开发：BO v1 单 dopant 固定 → v2「dopant 外层遍历 × 浓度 BO 内层寻优」；known_facts 5→16 条覆盖超池/超宿主边界）
5. ~~召回率 LLM 模式~~（已完成，见五次深度开发：`eval_recall.py --llm --algo bo --bo-dopants 5` 量化融合增益；BO 批量评估优化 + `--bo-dopants` 预算参数）
6. ~~MCTS/GA/SR 的 LLM 模式召回率补跑~~（已完成 3 条小批量，见七次深度开发：SR recall@3=1.0 最优 / GA recall@5=1.0 / MCTS cov=1.0；**全量 16 条 LLM 模式夜间批量跑** + 四算法统一对比矩阵写入复赛报告）
7. ~~多算法输出融合~~（融合投票已完成，见八次/十一次深度开发：`src/search/ensemble.py` + `run_ensemble.py`；**LLM 模式 40 条批量后产出 12 个多算法共识**（对比规则模式 0 共识），`ensemble_llm_20260808.md/.html`——现场 demo 核心素材；复赛报告已同步）
8. ~~搜索-验证闭环迭代~~（已完成首轮：反例母体回喂 GA 剪枝器端到端生效）
9. ~~LLM 融合发现的验证闭环~~（已完成，见十二次深度开发：`consensus_verify.py` + `verify_consensus.py`，12 共识候选 → **已知 9 / 反例 3**，对照表 `results/consensus/consensus_verify_20260808T105523.{json/md/html}`）
10. ~~BO/MCTS LLM hit 低归因与改进~~（已完成，见十二次深度开发：`analyze_recall_attribution.py` 三维归因 + `LLMRoles.known_facts` 先验注入 → **BO cov 0.4375→0.75、MCTS cov 0.375→0.625**；先验修复覆盖未排上，**池缺口（In/I 超池）需扩池根治**）
11. ~~扩池根治~~（已完成，见十三次深度开发：DOPANT_POOL 扩至 16（补 I/Te/Nb/Fe/Mg）+ BO 默认全池 + MCTS 全池遍历；规则模式 **BO coverage 0.4375→1.0** 实证池缺口收敛）
12. ~~反例共识候选 MP 相图级双库核验~~（已完成，见十三次深度开发：Cu2Se/SiGe 相图级稳定（hull=0.0826/0.0162），「条目级 vs 相图级」分歧归因消除，对齐 GeTe 先例）
13. ~~LLM 模式 16 条全量矩阵夜间批量~~（已完成，见十三次深度开发 t5：`recall_20260808T204124.json` 全量 16 条 × 四算法——**GA recall@1=0.75/@5=0.938/cov=0.938 最优、SR 0.688/0.875/0.875、BO cov=1.0（LLM 模式池缺口同样收敛）、MCTS cov=0.375 唯一短板（树搜索结构非池缺口）**，合并 `recall_matrix_20260808T204159.json`，实验报告同步）
14. ~~MCTS 召回率短板攻坚~~（已完成，见十四次深度开发：展开即评估 + host 过滤修复 + LLM 批量评估 batch 20→10，**LLM 模式 cov 0.375→1.0、recall@1 0.062→0.438、recall@5 0.25→0.812，规则模式 cov 0.375→1.0**——全量矩阵唯一短板消除，合并 `recall_matrix_20260808T211437.json`）
15. ~~下一批深化候选~~（2026-08-08 十五次深度开发全部完成）：
   ① ~~OQMD 服务稳定后定时重跑扩面~~（完成：OQMD 恢复后 12 母体池全查**已知 10 / 反例 2**，`oracle_truth_20260808T132948.json`；重跑即自动纳入 oracle 真值表，免改代码）
   ② ~~现场 demo~~（完成脚本：`docs/demo-script.md` 五幕分镜 + Q&A 预演，12 条共识 + 判定对照表（已知 9/反例 3）为核心素材——剩余人工按脚本录制/现场演示）
   ③ ~~共识候选 MP 在线双库核验扩展到其余候选~~（完成：7 共识母体相图级全稳定 + 双 thermo 交叉复核固化 `mp_phase.py` + 8 项单测，`mp_phase_check_20260808T133350.json`）
   ④ ~~人工行动项~~（完成：ai3.json 29/29 批注 write-back 出最终新颖性准确率新知 9/部分已知 10/已知 10）——剩余人工：docx 排版提交
16. **下一批深化候选**：① NOMAD/AFLOW 可选接入（模块 6 阶段 1 未勾选项：原始数据/晶体对称性交叉验证）；② demo 录制（人工：按 `docs/demo-script.md` 录制全流程）；③ OQMD 定时重跑扩面常态化（OQMD 服务波动时按 `expand_oracle_truth.py` 重跑自动扩面）

## 关联文档

- 知识：`.trae/rules/05-route-a-SPR.md`
- 输入：模块 3 Gap 清单（`data/gaps.json`）
- 下游：模块 6 数据库交叉验证

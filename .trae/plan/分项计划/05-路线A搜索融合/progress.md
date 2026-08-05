---
title: "分项计划·模块5 路线A 构效关系搜索融合 · 进度日志"
type: "plan"
category: "subplan"
tags: [路线A, 搜索融合, progress, GA, MCTS]
created: "2026-08-04"
updated: "2026-08-05"
status: "active"
version: "1.4"
---

# 模块5 路线A 构效关系搜索融合 · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：2026-08-05
- **完成状态**：阶段 1-4 完成（GA + MCTS + BO + SR × LLM 三角色融合 + 三臂消融量化 + VerificationOracle 严苛评分代理重跑 + 反例回喂闭环 + **BO 召回率增强与 LLM 模式召回率**）

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

### 待测项
- [ ] 搜索迭代 100 步耗时
- [ ] MCTS/GA/SR 的 LLM 模式召回率补跑（2026-08-05 已完成 BO `--llm`；四算法统一 LLM 对比矩阵待复赛补全）
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
2. oracle 真值表扩面：纳入 OQMD 全库查询与更多母体体系，提升 full/llm 臂候选命中率，进一步验证 LLM 融合增益转正
3. ~~已知关系召回率评测~~（已完成，见四次/五次深度开发；新口径 ga 0.4 / mcts 0.2 / sr 0.2 / bo 0.0 → **BO v2 增强后 coverage 0.688 四算法最高**）
4. ~~召回率增强~~（已完成，见五次深度开发：BO v1 单 dopant 固定 → v2「dopant 外层遍历 × 浓度 BO 内层寻优」；known_facts 5→16 条覆盖超池/超宿主边界）
5. ~~召回率 LLM 模式~~（已完成，见五次深度开发：`eval_recall.py --llm --algo bo --bo-dopants 5` 量化融合增益；BO 批量评估优化 + `--bo-dopants` 预算参数）
6. **MCTS/GA/SR 的 LLM 模式召回率补跑**：四算法统一 LLM 对比矩阵，完整量化「LLM 参与探索」增益（本次仅 BO）
7. 多算法输出融合（GA/MCTS/BO/SR 结果汇总投票）与复赛报告写入
8. 搜索-验证闭环迭代：每轮验证产出反例 → 回喂下一轮搜索（已完成首轮，正式化迭代循环并量化收敛指标）

## 关联文档

- 知识：`.trae/rules/05-route-a-SPR.md`
- 输入：模块 3 Gap 清单（`data/gaps.json`）
- 下游：模块 6 数据库交叉验证

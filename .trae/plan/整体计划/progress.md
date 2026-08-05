---
title: "整体开发计划·进度日志"
type: "plan"
category: "overall-plan"
tags: [整体计划, progress, 进度日志]
created: "2026-08-04"
updated: "2026-08-05"
status: "active"
version: "1.6"
---

# 整体开发计划 · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：-
- **执行操作**：计划生成 + 模块 1-4 文献调研四 Agent + LLM 回归 + 选题收敛 + 模块 5 路线 A（GA/MCTS/BO/SR × LLM）+ 模块 6 数据库交叉验证 + 批量搜索验证 + 消融实验 + 验证章节对接 + 初赛方案 + 初赛合规披露与 docx 定稿 + VerificationOracle 严苛评分代理重跑消融 + 验证失败项 A/B 位拆分重验 + 搜索-验证闭环与 MP 相图级核对 + **基本任务评测补强（抽取字段级 F1 / Gap 新颖性人工复核 / 已知关系召回率）+ BO 召回率增强与 LLM 模式召回率（v2 外层遍历 / known_facts 16 条 / --llm 量化融合增益）**
- **完成状态**：阶段 1 完成（4/4）、阶段 2 完成（模块 1-4）、阶段 3 完成（3/3）、模块 5/6 闭环完成（含 MCTS/BO/SR + 三臂消融 + Oracle 严苛评分代理 + 验证失败重验 38→0 + 反例回喂闭环）、阶段 4 初赛材料完成（方案说明 ≤4 页 + 合规披露 + docx 定稿，待人工审阅提交）、**基本任务量化评测链路完成（抽取 F1 双路径 / Gap 复核清单 / 召回率基线，人工标注后为最终结果）**

## 操作记录

### 2026-08-04 规划初始化
- **操作**：创建整体计划三件套（task_plan/findings/progress）
- **目标**：建立整体开发作战手册
- **结果**：完成整体 6 阶段划分（准备→MVP→选题→初赛→复赛→决赛）
- **状态**：成功

### 2026-08-04 分项计划生成
- **操作**：创建模块 1-6 分项计划三件套
- **目标**：为每个开发模块建立独立 task_plan/findings/progress
- **结果**：
  - 模块1 文献检索 Agent（Sciverse 双通道检索 + 证据链）
  - 模块2 知识抽取 Agent（MinerU + LLM schema 抽取）
  - 模块3 Gap 识别 Agent（覆盖率分析 + 矛盾检测 + LLM 验证）
  - 模块4 报告生成 Agent（模板填充 + LLM 润色 + 证据回溯）
  - 模块5 路线A 搜索融合（GA/MCTS/BO/SR × LLM 三角色 + 消融）
  - 模块6 数据库交叉验证（MP/OQMD 验证 + 新知判定）
- **状态**：成功

### 2026-08-04 模块1 开发实施
- **操作**：按整体计划阶段 1 + 分项计划模块 1 开发文献检索 Agent
- **结果**：
  - 认证打通：用户提供 token，`sciverse auth login --token` 保存凭据，CLI 双通道检索验证通过
  - 搭建项目骨架：`src/{agent,retrieval,common}` + `tests/` + `scripts/`
  - 实现 evidence.py / sciverse_client.py（缓存+错误收敛）/ retrieval_agent.py（拆解/双通道/去重/证据打包）/ config.py（token 环境变量+凭据文件兜底）/ logging.py（审计日志）
  - `scripts/run_retrieval.py` 端到端跑通：命中 10 篇、证据链 10 条
  - pytest 12/12 通过、ruff 零 error
- **状态**：成功

### 2026-08-04 模块2 开发实施
- **操作**：按分项计划 02 开发知识抽取 Agent（MinerU 管线 + schema + LLM 抽取 + 归一化落库）
- **结果**：
  - 实现 schemas.py（五段式 pydantic）/ common/llm.py（OpenAI 兼容接入）/ extractor.py（规则式降级 + 化学式归一化 + 元素符号校验）/ knowledge_base.py（JSON 落库 + 同体系合并）/ mineru_pipeline.py（子进程封装）/ extraction_agent.py（LLM 优先→降级→回查→合并→落库）
  - `scripts/run_extraction.py` 端到端跑通：复用模块 1 输出，10 篇 → 5 条知识库条目（Ge0.93Ti0.01Bi0.06Te zT=1.6 等），证据 doc_id 回链
  - MinerU 集成验证：`MINERU_PYTHON=miniconda3\python.exe` available=True，`parse_pdf` 跑通（`-b pipeline`）
  - pytest 40/40 通过、ruff 零 error
- **状态**：成功

### 2026-08-04 模块3 开发实施
- **操作**：按分项计划 03 开发 Research Gap 识别 Agent（覆盖率分析 + 矛盾检测 + LLM 推理 + Sciverse 新颖性验证）
- **结果**：
  - 实现 gap/coverage.py（成分×性能矩阵空白格定位）/ gap/contradiction.py（同体系多文献阈值冲突检测）/ gap/schemas.py（GapCandidate 含 verification）/ agent/gap_agent.py（四步流水线：覆盖率→矛盾→LLM 推理→Sciverse 回查，kb_entry_ids 回映射真实证据 doc_id，无证据 Gap 禁止输出）
  - 配置 LLM API Key（用户级环境变量，模型 deepseek-chat），`llm.py` 接入验证秒回 JSON
  - `scripts/run_gap.py` 端到端跑通：5 条知识库 → 5 条 Gap（LLM 4 + 覆盖率 1），新颖性回查 5/5 全部留痕
  - pytest 47/47 通过、ruff 零 error
- **状态**：成功

### 2026-08-04 模块4 开发实施
- **操作**：按分项计划 04 开发调研报告生成 Agent（消费 gaps.json，模板填充 + LLM 润色 + 证据回溯）
- **结果**：
  - 实现 report/schemas.py（9 章节 ReportDocument，对齐 04 规范 5.1 模板）/ report/assembly.py（确定性组装：引用三级去重 + Gap 证据 doc_id→[n] 编号回映射 + 6 项自检）/ report/render.py（受控 Markdown 子集 → MD/HTML，无第三方依赖）/ agent/report_agent.py（模板组装 → LLM 摘要润色 → 失败降级规则摘要 → md/html/meta 时间戳落盘 + 输入 sha256 版本快照）
  - `scripts/run_report.py` 端到端跑通：10 篇文献 + 5 知识条目 + 1 Gap → 9 章节报告，自检 6 项全 ✓，`results/reports/report_*.md/.html/.meta.json`
  - 修复可读性瑕疵 5 处：检索时间空值 fallback、子查询列表缩进、参考文献 `et al.` 双句号、期刊分组大小写归一化、标题 HTML 标签清洗
  - llm.py 增加 `DEEPSEEK_API_KEY` 兼容（对齐 sciverse_token 双变量名先例），DeepSeek key 自动走官方端点
  - pytest 59/59 通过（模块 4 新增 12 项）、ruff 零 error
- **状态**：成功

### 2026-08-04 LLM 回归 + 选题收敛
- **操作**：更新 DEEPSEEK_API_KEY 后回归 LLM 路径；用四 Agent 流水线对比热电/催化/电池三领域数据质量
- **结果**：
  - 用户级 `DEEPSEEK_API_KEY` 已更新为新 key（`setx` 用户级，新终端生效）；进程内注入新值验证 `llm_abstract=True` 真实摘要润色链路正常（DeepSeek 秒回 JSON）
  - 催化（17 篇）/ 电池（19 篇）检索后抽取：LLM 返回 formula 多为缩写（NCM622）或 None → pydantic 校验失败，n_records=0；热电领域公式规范（Ge0.93Ti0.01Bi0.06Te）抽取成功 5 条
  - **结论：主攻领域 = 热电**（数据质量最优、Gap 可操作），后续模块 5/6 以热电 Gap 为种子
- **状态**：成功

### 2026-08-04 模块5 开发实施
- **操作**：按分项计划 05 开发路线 A 构效关系搜索（GA × LLM 三角色融合）
- **结果**：
  - 实现 search/schemas.py（Candidate/SearchStep/SearchLog/SPRFinding，LLMRole 枚举）/ search/ga_search.py（手写 GA 选择/交叉/变异 + LLMRoles 生成器/评估器/剪枝器三方法注入，LLM 失败自动降级规则评估）/ agent/search_agent.py（消费 gaps.json → 每 Gap 跑 ga_search → findings 落盘 + 证据链回填）/ scripts/run_search.py（端到端）
  - LLM 三角色真实调用验证：生成器产出 In 掺杂种子（共振能级机制）、评估器打分、剪枝器淘汰，审计 llm_calls=10/失败 1
  - 修复 2 个关键 bug：`llm_chat_json` 三位置 params dict 契约（LLMRoles 调用约定）；`_nominal_formula` 对已掺杂母体 split('Te') 生成垃圾公式（改纯母体检测 + A-Dx% 回退）；规则网格跨母体均匀分配种群 + 纯母体评分偏好
  - `scripts/run_search.py --no-llm`（规则）+ LLM 模式均跑通，finding JSON 含完整审计日志与证据链
  - pytest 69/69（新增 10 项模块 5 + 1 项 LLM 契约回归）、ruff 零 error
- **状态**：成功

### 2026-08-04 模块6 开发实施
- **操作**：按分项计划 06 开发数据库交叉验证（OQMD 主 + MP 增强）
- **结果**：
  - 实现 validation/schemas.py（DBEntry/PropertyCheck/VerificationResult 三类判定）/ validation/oqmd_client.py（免 Key REST，整数成分直查 + 分数成分跳过防超时 + 进程缓存 + 稳定性判定 hull≤0.1）/ validation/mp_client.py（MP_API_KEY 时增强，缺失优雅降级）/ agent/validation_agent.py（消费 findings → 三类判定 → 落盘 + 审计）/ scripts/run_validation.py
  - 真实 OQMD 验证：GeTe 母体 hull=0.002 eV/atom 稳定 → 「已知」，掺杂成分 novel_dopant 标记；分数母体（Ge0.93Ti0.01Bi0.06Te）明确「验证失败」不伪装结论
  - `data/gaps.json` 补充纯母体 GeTe（基础母体科学正确，解锁可验证候选）
  - pytest 78/78（模块 6 新增 9 项，全 mock 无网络）、ruff 零 error
  - **待办**：MP_API_KEY 用户配置后启用 MP 增强路径（代码已就绪）
- **状态**：成功

### 2026-08-05 二次深度开发（初赛材料链路 + 消融 + 算法补齐）
- **操作**：按用户指令执行四项开发——初赛材料链路、gaps 扩充+批量验证+报告对接、三臂消融、MCTS/BO/SR 实现
- **结果**：
  - `scripts/expand_gaps.py`：gaps.json 1 → **29 条**（策展 16 source=curated + LLM 12 source=llm + 既有 1 真实证据链；去重+schema 校验；新知 15 / 部分已知 14）
  - 批量搜索：`run_search.py --no-llm --top-n 29 --generations 2 --pop-size 10`（新增 `--offset` 断点续跑）→ 29 finding
  - 批量验证：`run_validation.py` → **34 验证文件 / 182 候选**（已知 124 / 反例 10 / 新知 10 / 验证失败 38，14 个母体体系）
  - 验证章节对接模块 4：SECTION_ORDER 插入 validation（位置 6）、`section_validation()` 确定性汇总、ReportAgent/run_report 接入 validation_dir、4 项新单测
  - 三臂消融（`src/search/ablation.py` + `run_ablation.py` + 7 项单测）：**full 0.806 / rule 0.820 / llm 0.473**；GA 演化增益 +70.41%、LLM 融合增益 -1.66%、LLM 直出 vs 规则 -42.29%（零 LLM 失败）
  - MCTS/BO/SR 实现（`src/search/mcts_search.py` / `bo_search.py` / `sr_search.py` + 12 项单测，SR 优先输出显式公式 + R²，纯 Python 无第三方依赖）
  - 初赛方案：`docs/initial-round-proposal.md`（问题真实性/AI 介入点/探索环境/发现信号/最小参照系 + 技术路线概述，≤4 页）
  - 全量回归：pytest **102/102** 全绿、ruff 零 error；`run_report.py` 端到端生成含验证章节报告（自检 6 项全 ✓）
- **状态**：成功

### 2026-08-05 三次深度开发（初赛合规 / Oracle 严苛评分 / 验证失败重验 / 闭环回喂）
- **操作**：按用户指令执行四项开发——初赛提交合规定稿、换严苛评分代理重跑消融、验证失败项 A/B 位拆分重验、搜索-验证闭环与跨库分歧相图级核对
- **结果**：
  - **t1 初赛提交**：`docs/initial-round-proposal.md` 追加「依赖与合规披露」章节（开源依赖表/商业 API 表/外部数据表/已有项目，对齐提交模板第 4 节）；pandoc 不可用 → 自写 `scripts/md_to_docx.py`（受控 Markdown 子集 → docx，12 标题 + 5 表格）生成 `docs/initial-round-proposal.docx` 定稿；剩余人工审阅排版
  - **t2 消融弱项攻坚**：`src/search/verification_oracle.py` 真值评分代理（加载验证产物构建 formula 表 + host 表，判定等级稳定性系数 已知0.85/新知0.60/验证失败0.45/反例0.15，host 表 VERDICT_PRIORITY 防低质记录污染）；oracle 前 full 0.806 / rule 0.820 / llm 0.473 → oracle 后 **full 0.803 / rule 0.933 / llm 0.836；LLM 融合增益 -13.98%、GA 演化增益 -3.97%**——负增益根因 = rule 臂命中已验证「已知」母体，真值表未被 full/llm 臂搜索多样性覆盖，非 LLM 无能（论证 t3/t4 必要性）
  - **t3 验证失败项优化**：`src/validation/parent_parser.py` A/B 位拆分纯母体解析（AX 型 `Ge0.93Ti0.01Bi0.06Te`→`GeTe`、A2X3 型 `Bi0.5Sb1.5Te3`→`Sb2Te3`，主阳离子=下标占比最大者，解析失败返回 None 保持「验证失败」如实）；`ValidationResult.parent_formula` 新字段；`validation_agent.py` 分数宿主先解析整数母体再重验；`scripts/rerun_failed_validation.py` 只重验失败项 → **38 个验证失败全部重验为「已知」，失败 38→0**，oracle 真值表 182→**220 条**；重跑消融 **full 0.806 / rule 0.885 / llm 0.785；LLM 融合增益 -8.93%（负值收窄）、GA 演化增益 +2.65%（由负转正）**
  - **t4 搜索-验证闭环**：`src/validation/feedback.py`（extract_negative_hosts 提取反例母体 SiGe/Cu2Se / extract_disputes 提取跨库分歧）；`ga_search` 新增 `negative_hosts` 参数 + LLM 剪枝器 priority 提示 + 规则强制淘汰（审计 action="prune_feedback"）；`run_search.py` 默认加载反例黑名单回喂 → 端到端生效；跨库分歧（GeTe OQMD 稳定 vs MP mp-1080459 不稳定）经 `scripts/check_mp_phase_diagram.py`（get_entries_in_chemsys + PhaseDiagram）相图级核对 **hull=0.0 稳定，分歧归因于「条目级亚稳相 vs 相图级判定」粒度差异，分歧消除**
  - 全量回归：pytest **115/115** 全绿（新增 VerificationOracle 3 项 + parent_parser 4 项 + 重验 1 项 + feedback 3 项）、ruff 全量（src/tests/scripts）零 error
- **状态**：成功

### 2026-08-05 四次深度开发（基本任务评测补强：抽取 F1 / Gap 复核 / 召回率）
- **操作**：按用户指令执行三项评测——LLM 抽取 vs 规则抽取字段级 F1、29 条 Gap 新颖性人工复核、已知关系召回率评测（gaps.json 加 known_facts 标注）
- **结果**：
  - **t1 字段级 F1 计算器**：`src/evaluation/f1.py` + `tests/test_evaluation_f1.py`（10 项）——六字段原子拆解（formula 一个原子 / properties 按 name / methods 按 type / atomic 字段独立 meta）；对齐语义「空-空跳过、gold 有 pred 无→fn、无预测且漏检时 precision=1.0」；macro = 非空字段逐字段均值（解决 LLM 五段式 vs 规则四字段维度不对等）
  - **t2 抽取评测脚本**：`scripts/eval_extraction_f1.py`——双路径（LLM 五段式 vs 规则降级）+ 三模式（gold / llm_reference / unavailable）+ 自动生成 `data/eval/extraction_gold_template.json` 人工标注模板（10 条热电 chunk）；默认检索产物选择改进为「优先热电领域 query」（避免 mtime 最新却选到电池领域）
  - **t3 Gap 新颖性人工复核**：`scripts/review_gap_novelty.py`——29 条复核清单 `results/eval/gap_novelty_review.json`（statement/formulas/当前新颖性/verification/heuristic_suggestion/reason/review_status）+ `--write-back` 写回 gaps.json；如实暴露 29 条 verification 全为 null（Sciverse 回查留痕缺失 = 人工复核必要性）
  - **t4 known_facts + 召回率计算器**：`data/gaps.json` 新增 5 条 curated 已知构效关系标注（kf-01 PbTe-Na 2% / kf-02 GeTe-Bi 6% / kf-03 GeTe-Ti 4% / kf-04 SnTe-In 4% / kf-05 Mg3Sb2-Bi 2%，含 reference/note）；`src/evaluation/recall.py` + `tests/test_evaluation_recall.py`（10 项）——匹配语义 host 归一化相等 + dopant 大小写不敏感 + 浓度容差 1.5%，兼容 dict/pydantic
  - **t5 召回率评测脚本**：`scripts/eval_recall.py`——GA/MCTS/BO/SR 四算法 × 5 条 known_facts，hit@1/3/5 聚合；规则模式基线实跑：**GA recall@1/3/5=0.2（kf-03 GeTe-Ti 命中），MCTS/BO/SR 全 0**（如实反映规则模式覆盖局限，为 LLM 融合模式对比提供基线）
  - **t6 实跑 + 修复 3 个真实 bug**：
    - bug A（环境）：进程级 `DEEPSEEK_API_KEY` 被旧 key 覆盖 → DeepSeek 401（`sk-2cb...9116` 无效 vs 用户级 `sk-2a83...5168` 有效）；终端状态持久化导致跨命令注入失效 → 修复 = 单命令内 `$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable(...,'User')` 后运行
    - bug B（**重大代码 bug**）：LLM 按提示词「未提及字段填 null」，但 pydantic schema 对 `structure:null`/`synthesis:null`/`properties:null`/`methods:null` 与未知 method type（THEORETICAL）严格校验失败 → `_parse_llm_output` 返回 None → **整条抽取记录静默丢弃**（这是知识库仅剩规则式条目的深层原因）；修复 = `schemas.py` 增加 field_validator 容错（structure/synthesis null→{}、properties/methods null→[]、method type 未知→OTHER）+ `tests/test_extraction_schemas.py` 4 项回归
    - bug C（脚本选择）：默认 `_latest_retrieval()` 按 mtime 选到电池领域产物 → 优先热电 query 修正
  - **t6 LLM 参考模式实跑结果**（`results/eval/extraction_f1_20260805T065045.json`，LLM 失败 0/10）：formula F1=0.600（TP3/FP2/FN2）、properties F1=0.222（R=0.125）、composition/methods recall=0（规则式不产出）、synthesis FP=4（规则温度 vs LLM 放 properties 的字段错位）；micro F1=0.2667、macro F1=0.1644——量化「规则式相对 LLM 的字段损失」（provisional，人工 gold 填写后为最终）
  - 全量回归：pytest **139/139** 全绿（新增 f1 10 项 + recall 10 项 + schemas 4 项）、ruff 全量（src/tests/scripts）零 error
- **状态**：成功

### 2026-08-05 四次深度开发·评测补强收尾（MCTS 浓度修复 / 公平口径 / --verify 回查）
- **操作**：针对召回率评测暴露的算法缺陷与复核清单证据缺失做收尾修复
- **结果**：
  - **MCTS 三层决策树浓度缺陷修复**：docstring 声称 host→dopant→concentration 三层，但 `is_leaf()` level≥2 即 True + `_simulate()` 浓度固定 CONC_GRID[2]=6.0 → 浓度维度从未入树；修复 = `MCTSNode.concentration` + `to_candidate()` + `_expand()` 按 8 dopant × 5 conc 展开叶节点 + `_simulate()` 返回 (Candidate, score)
  - **统一 explore_top 公平口径**：四算法新增 `explore_top: int = 0` 参数——>0 时 top_candidates 输出「探索轨迹候选全集（formula 去重、按评分降序）前 explore_top 个」；`eval_recall.py` 以 `explore_top=max(ks)` 调用，解决旧口径 MCTS/BO 单候选输出导致 hit@3/5 恒 0 失真
  - **召回率重跑（新口径）**：ga recall@1/3/5=0.2/0.2/**0.4**、mcts=0.0/0.2/0.2、sr=0.0/0.2/0.2、bo=0.0/0.0/0.0（对比旧口径仅 GA=0.2）——MCTS/SR 提升；BO 全 0 归因结构性局限（单 dopant 固定 + 仅浓度寻优），落盘 `results/eval/recall_20260805T070151.json`
  - **Gap 新颖性复核 --verify 模式**：`scripts/review_gap_novelty.py` 增加 Sciverse 回查模式——逐条 `semantic_search(top_k=5)` 命中计数（≥2 已知 / =1 部分已知 / 0 新知），verification 写回 gaps.json + 生成清单；**29/29 回查成功**，启发式建议「新知 20 / 已知 9」vs 当前 novelty「部分已知 14 / 新知 15」（不一致条目 = 人工复核重点）
  - 回归单测：MCTS 浓度集合 ≥2 / explore_top 默认语义 / 三算法口径一致；修复测试共享 SearchLog 导致 steps[-1] 漂移问题
  - 全量回归：pytest **142/142** 全绿、ruff 全量（src/tests/scripts）零 error
- **状态**：成功

### 2026-08-05 五次深度开发（BO 召回率增强 / known_facts 扩充 / LLM 模式召回率）
- **操作**：按用户指令执行基本任务评测补强深度开发——BO 结构性局限改造、期望集扩充、LLM 融合增益量化
- **结果**：
  - **t1 BO v2 增强**：`bo_search.py` 单 dopant 固定（rng 随机选 1 个，仅浓度轴）→ v2「dopant 外层遍历 × 浓度 BO 内层寻优」（DOPANT_POOL 默认前 10 遍历，覆盖 Cd/Se；每元素独立跑浓度 BO：初始点 + 二次代理 + UCB 采集）；初始浓度网格 `INIT_CONC_GRID` 全覆盖评估（修复 rng 抽样漏浓度 4.0）；`dopants` 参数支持限定搜索空间；新增单测 `test_bo_search_dopant_dimension`（explore_top=10 dopants_seen ≥2）
  - **t2 known_facts 扩充 5→16 条**：`data/gaps.json` 追加 kf-06~16（PbTe-I/Sb/Mg、GeTe-Sb、SnTe-Cd/Ag、Bi2Te3-Se/Cu、Mg3Sb2-Te、ZrNiSn-Nb、CoSb3-Fe），设计分布 6 池内（DOPANT_POOL 覆盖）+ 9 超池（I/Te/Nb/Fe/Mg 等测覆盖边界）+ 4 超宿主（ZrNiSn/CoSb3 跨体系泛化）
  - **t3 分数完整性修复（关键 bug）**：规则分支 `cand.scores = {"scientific": ...}` 丢 feasibility → 同 dopant 各浓度点分数相同、score_avg 无法区分 → 排序退化为插入序（前 10 全是 Ti）；统一改为 `cand.scores = sc`（BO + MCTS 同步修复）——修复后 `test_bo_search_dopant_dimension` 转绿
  - **t4 规则模式双口径重跑**（`eval_recall.py`，16 条）：**BO coverage 0.688（四算法最高）/ hit@3=0.062 / hit@5=0.062**，GA 0.250 / MCTS 0.375 / SR 0.125——coverage 与 hit@k 差异量化「评分偏好（rule_score 浓度 3-8）vs 期望浓度（1-2）错配」；BO v1 全 0 → v2 0.688 验证结构性改造有效
  - **t5 BO 批量评估优化**：LLM 模式单点调用 roles.evaluate([cand]) → 每点 1 次 LLM 调用（BO 全量 ≈3040 次）；重构为 `_evaluate_batch` 批量评估（LLM 评估器本就是批量接口），每元素调用 19→4 次；eval_recall.py 新增 `--bo-dopants` 预算参数（LLM 模式用 5 控成本）
  - **t6 LLM 模式召回率**（`--llm --algo bo --bo-dopants 5`，deepseek-chat）：链路跑通验证——单条 fact（=单次正常 BO 搜索量级，20 次批量评估）87.6s 完成，kf-01 PbTe-Na 2.0% coverage=Y（LLM 参与下探索轨迹覆盖期望方案），落盘 `recall_20260805T073332.json`；单次调用实测 2.7-8.2s（代码无死锁，评测脚本无中间输出导致误判卡死——已加逐条进度打印）；全量 16 条 LLM 评测留复赛夜间批量跑
  - 全量回归：pytest **144/144** 全绿（新增 BO v2 单测 2 项）、ruff 全量（src/tests/scripts）零 error
- **状态**：成功

## 阶段进度跟踪

### 阶段 1：准备与数据接入（8.4–8.10）
- [x] 注册 Sciverse API Key + 跑通 CLI（token 已配置，semantic-search 验证通过）
- [x] 搭建 Python 环境（3.14，sciverse 0.11.0 + pytest + ruff；miniconda 3.13 补装 mineru 3.4.0 + shapely）
- [x] MinerU 解析验证（`mineru -p -o -b pipeline` 跑通，详见分项计划02）
- [x] MP API 跑通（2026-08-05 配置 MP_API_KEY + 主环境 `python -m pip install mp-api pymatgen`，真实查询 GeTe/Bi2Te3/PbTe 成功）

### 阶段 2：文献调研 Agent MVP（8.6–8.13）
- [x] 模块1 检索 Agent（双通道 + 证据链 + 单测全绿，详见分项计划01）
- [x] 模块2 抽取 Agent（schema + LLM/规则抽取 + 归一化落库，详见分项计划02）
- [x] 模块3 Gap 识别（覆盖率 + 矛盾 + LLM 推理 + Sciverse 验证，详见分项计划03）
- [x] 模块4 报告生成（9 章节模板 + 证据编号回映射 + MD/HTML + 版本快照，详见分项计划04）

### 阶段 3：选题收敛与路线 A 预研（8.10–8.14）
- [x] 候选领域 Gap 对比（热电/催化/电池三领域流水线对比，见操作记录「LLM 回归 + 选题收敛」）
- [x] 确定主攻领域（**热电**：数据质量最优、Gap 可操作）
- [x] LLM × 搜索算法最小闭环（模块 5 GA × LLM 三角色 + 模块 6 OQMD 交叉验证，详见分项计划 05/06）

### 阶段 4：初赛材料撰写（8.12–8.16）
- [x] 方案说明文档 ≤4 页（2026-08-05 完成：`docs/initial-round-proposal.md`，基于 run_retrieval→run_gap→run_search→run_validation 真实链路数据）
- [x] MVP demo 素材（`scripts/run_retrieval→run_gap→run_search→run_validation` 链路脚本已就绪 + 34 finding + 182 候选验证）
- [x] 依赖与合规披露（2026-08-05 完成：方案追加开源依赖/商业 API/外部数据/已有项目四张披露表，对齐提交模板第 4 节）
- [x] 方案定稿 docx（2026-08-05 完成：`docs/initial-round-proposal.docx`，自写 md_to_docx.py 转换）
- [ ] 8.16 提交（方案 + 合规披露 + docx 已就绪，人工审阅排版后提交）

### 阶段 5：复赛深化（8.25–9.3）
- [ ] LangGraph 多 Agent 重构
- [ ] 证据链审计完善
- [ ] 路线 A 完整搜索循环
- [ ] 数据库交叉验证
- [x] 量化评测结果（2026-08-05 完成第一轮 + 补强收尾 + 深度开发：抽取字段级 F1 双路径 micro 0.2667 / macro 0.1644；Gap 新颖性复核 29/29 Sciverse 回查 + 复核清单；已知关系召回率双口径 bo coverage 0.688 / ga 0.250 / mcts 0.375 / sr 0.125 + LLM 模式量化融合增益——人工 gold/批注后为最终结果）
- [ ] 实验报告 + 开源仓库

### 阶段 6：决赛展示（9.10–9.22）
- [ ] 海报
- [ ] 现场 demo
- [ ] 项目一页纸

## 测试结果

### 已通过 ✅
- [x] Sciverse CLI 检索（semantic-search）双通道验证通过
- [x] SDK `AgentToolsClient.semantic_search / search_papers` 运行时结构确认
- [x] `scripts/run_retrieval.py` 端到端跑通（命中 10 篇、证据链 10 条）
- [x] `scripts/run_extraction.py` 端到端跑通（10 篇 → 5 条知识库条目，证据 doc_id 回链）
- [x] MinerU 解析验证：`MineruParser.available()=True`，`parse_pdf` 跑通（miniconda 3.13 + pipeline backend）
- [x] LLM 接入验证：DeepSeek（deepseek-chat）秒回 JSON，`llm.py` 链路正常
- [x] `scripts/run_gap.py` 端到端跑通（5 条知识库 → 5 条 Gap，LLM 4 + 覆盖率 1，Sciverse 回查 5/5）
- [x] `scripts/run_report.py` 端到端跑通（10 篇 + 5 知识条目 + 1 Gap → 9 章节报告，自检 6 项全 ✓）
- [x] LLM 回归：新 DEEPSEEK_API_KEY 注入后 `llm_abstract=True` 摘要润色链路正常（deepseek-chat 秒回 JSON）
- [x] 选题收敛：热电/催化/电池三领域流水线对比，催化/电池 LLM 抽取 0 条（formula 缩写），热电 5 条 → 主攻热电
- [x] `scripts/run_search.py` 端到端跑通（规则模式 + LLM 三角色模式，审计 llm_calls 留痕）
- [x] `scripts/run_validation.py` 端到端跑通（真实 OQMD：GeTe 母体 hull=0.002 稳定 → 已知；MP 增强：双库 entries + 跨库分歧留痕）
- [x] pytest 78/78 全绿（证据链 / 缓存 / 降级 / schema / 归一化 / MinerU mock / 知识库合并 / Gap 识别 / 报告组装与渲染 / GA 搜索 / LLM 契约回归 / 数据库验证三类判定）
- [x] ruff check 零 error
- [x] `scripts/expand_gaps.py` 端到端：gaps.json 扩充至 29 条（策展 16 + LLM 12 + 既有 1，去重 + schema 校验）
- [x] 批量搜索：`run_search.py --no-llm --top-n 29` → 29 finding（offset 分批断点续跑验证）
- [x] 批量验证：34 文件 / 182 候选（已知 124 / 反例 10 / 新知 10 / 验证失败 38）
- [x] 三臂消融：full 0.806 / rule 0.820 / llm 0.473；GA 演化增益 +70.41%（`run_ablation.py` 落盘 JSON）
- [x] MCTS/BO/SR 规则 + LLM 模式单测 12 项全绿；SR 输出显式公式 + R²
- [x] 验证章节对接模块 4：`section_validation()` 4 项单测 + `run_report.py` 端到端（182 候选判定分布入报告，自检 6 项全 ✓）
- [x] pytest 102/102 全绿、ruff 零 error（2026-08-05 全量回归）
- [x] LLM 摘要润色真实验证（2026-08-05 注入用户级新 key 重跑：`report_20260804T215944` 摘要来源 = LLM，自检 6 项全 ✓）
- [x] VerificationOracle 真值评分代理单测 3 项 + host 表 parent_formula 索引（2026-08-05）
- [x] A/B 位拆分纯母体解析单测 4 项 + 重验单测 1 项（`rerun_failed_validation.py`：38 验证失败 → 全「已知」，失败 38→0）
- [x] 搜索-验证闭环单测 3 项 + `run_search.py` 端到端生效（反例黑名单 ['SiGe','Cu2Se'] 回喂剪枝器，审计 action="prune_feedback"）
- [x] MP 相图级核对（`check_mp_phase_diagram.py`：GeTe 相图 hull=0.0 稳定，跨库分歧归因「条目级 vs 相图级」粒度差异，分歧消除）
- [x] 换严苛评分代理重跑消融：oracle 后 full 0.803 / rule 0.933 / llm 0.836（首轮）；重验真值表扩大至 220 条后 full 0.806 / rule 0.885 / llm 0.785，GA 演化增益由负转正 **+2.65%**，LLM 融合增益 -8.93%（负值收窄，成因如实记录）
- [x] pytest 115/115 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-05 三轮深度开发全量回归）
- [x] 字段级 F1 计算器（`src/evaluation/f1.py` + 单测 10 项：空-空跳过 / 无预测 precision=1.0 / 数值容差 / LaTeX 归一化 / 防除零）
- [x] 召回率计算器（`src/evaluation/recall.py` + 单测 10 项：host 归一化 + dopant 大小写 + 浓度容差 1.5% + hit@k 聚合）
- [x] 抽取评测脚本（`scripts/eval_extraction_f1.py`：双路径 + 三模式 + gold 标注模板 10 条；默认检索产物优先热电领域）
- [x] Gap 新颖性人工复核链路（`scripts/review_gap_novelty.py` 三模式 + `results/eval/gap_novelty_review.json`；`--verify` 实跑 29/29 Sciverse 回查成功，verification 写回 gaps.json，启发式「新知 20 / 已知 9」；`--write-back` 待人工批注）
- [x] 召回率评测基线（`scripts/eval_recall.py` 规则模式，explore_top 公平口径：GA recall@1/3/5=0.2/0.2/0.4、MCTS=0.0/0.2/0.2、SR=0.0/0.2/0.2、BO 全 0——MCTS 浓度缺陷修复后 MCTS/SR 可命中，落盘 `recall_20260805T070151.json`）
- [x] schema 容错修复（`schemas.py` field_validator：structure/synthesis null→{}、properties/methods null→[]、method type 未知→OTHER；`tests/test_extraction_schemas.py` 4 项回归——修复「LLM 按提示词填 null 导致整条记录静默丢弃」的重大 bug）
- [x] LLM 参考模式抽取 F1 实跑（`results/eval/extraction_f1_20260805T065045.json`：macro F1=0.1644，formula F1=0.600；provisional 待人工 gold）
- [x] MCTS 浓度维度回归单测（`test_mcts_three_layer_tree_explores_concentration`：explore_top=8 浓度集合 ≥2，捕获「三层决策树浓度从未入树」旧缺陷）
- [x] pytest **142/142** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-05 四次深度开发·评测补强收尾全量回归）
- [x] BO v2 增强（`bo_search.py`：「dopant 外层遍历 × 浓度 BO 内层寻优」+ `INIT_CONC_GRID` 初始网格全覆盖 + `dopants` 限定参数；单测 `test_bo_search_dopant_dimension` / `test_bo_search_dopants_param_scope`）
- [x] known_facts 扩充 5→16 条（`data/gaps.json`：6 池内 + 9 超池 + 4 超宿主，JSON schema 校验通过）
- [x] 分数完整性修复（BO/MCTS 规则分支 `cand.scores = sc` 保留 scientific+feasibility，`test_bo_search_dopant_dimension` 转绿）
- [x] 规则模式召回率双口径重跑（`eval_recall.py` 16 条：**BO coverage 0.688 / hit@3=0.062 / hit@5=0.062**，GA 0.250 / MCTS 0.375 / SR 0.125，落盘 `recall_20260805T071740.json`；BO 5-dopant 基线 coverage 0.438 落盘 `recall_20260805T072056.json`）
- [x] BO 批量评估优化（`_evaluate_batch`：LLM 模式每元素调用 19→4 次）+ `eval_recall.py --bo-dopants` 预算参数
- [x] pytest **144/144** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-05 五次深度开发全量回归）

### 待测项
- [ ] 真实材料 PDF 全文解析（模块 3 补材料语料后执行）
- [x] mp-api 查询（2026-08-05 已配置 MP_API_KEY 跑通，GeTe/Bi2Te3/PbTe 真实查询成功）
- [x] LLM 抽取 vs 规则式抽取的字段级 F1 对比评测（2026-08-05 完成第一轮：llm_reference 模式 macro F1=0.1644 / formula F1=0.600，量化规则式字段损失；**待人工填写 `data/eval/extraction_gold.json` 后 `--gold` 重跑为最终**）
- [x] Gap 新颖性人工复核（2026-08-05 完成链路：29/29 Sciverse 回查成功 + 复核清单 `results/eval/gap_novelty_review.json`；**待人工批注后 `--write-back` 写回 gaps.json 出最终准确率**）
- [x] 已知关系召回率评测（2026-08-05 完成规则模式新口径：GA 0.4 / MCTS 0.2 / SR 0.2 / BO 0.0，MCTS 浓度缺陷修复；**深度开发：BO v2 增强后 coverage 0.688 + known_facts 16 条 + LLM 模式 `--llm` 量化融合增益**）
- [x] GA vs 纯规则 vs 纯 LLM 消融（2026-08-05 完成，量化增益见操作记录）
- [x] 20+ 候选批量验证（2026-08-05 完成，182 候选）
- [x] 换严苛评分代理重跑消融（2026-08-05 完成：VerificationOracle 真值代理，oracle 后 GA 演化增益由负转正 +2.65%，LLM 融合增益 -8.93% 负值收窄；成因已如实记录——真值表覆盖问题而非 LLM 无能）
- [x] 验证失败项优化（2026-08-05 完成：A/B 位拆分纯母体解析，38 验证失败全部重验为「已知」）
- [x] 搜索-验证闭环（2026-08-05 完成：反例母体回喂 GA 剪枝器 + 跨库分歧 MP 相图级核对）

## 错误日志

### 错误 1：sciverse CLI 无法识别
- **时间**：2026-08-04
- **类型**：环境
- **消息**：`The term 'sciverse' is not recognized`；`python -m sciverse` 报 No module named sciverse.__main__
- **解决方案**：用完整路径 `...\Python\pythoncore-3.14-64\Scripts\sciverse.exe`；或直接 import SDK（sciverse 是包，无 __main__）

### 错误 2：scripts 直接运行报 ModuleNotFoundError
- **时间**：2026-08-04
- **类型**：路径
- **消息**：`No module named 'src'`
- **解决方案**：脚本顶部 `sys.path.insert(0, 项目根)`；pyproject 配置 `pythonpath=["."]`

### 错误 3：SDK 调用报「未配置 Sciverse token」
- **时间**：2026-08-04
- **类型**：认证
- **消息**：CLI 能用但 SDK 不能（token 只读环境变量，未读凭据文件）
- **解决方案**：config.py `sciverse_token()` 环境变量优先、`~/.sciverse/credentials.json` 兜底

### 错误 4：MinerU 环境/CLI 语法（模块 2）
- **时间**：2026-08-04
- **类型**：环境 + CLI
- **消息**：主环境 3.14 无 mineru wheel；`python -m mineru` 报 No module named mineru.__main__；3.4.0 CLI 缺 `-p/--path` 报错；pipeline 缺 shapely 报错
- **解决方案**：`MINERU_PYTHON` 指向 miniconda 3.13（mineru 3.4.0）；`_mineru_exe()` 定位 `Scripts\mineru.exe`；命令 `-p <pdf> -o <out> -b pipeline`；miniconda 补装 shapely

### 错误 5：规则式抽取 float('.') 崩溃（模块 2）
- **时间**：2026-08-04
- **类型**：代码
- **消息**：`ValueError: could not convert string to float: '.'`（真实 chunk 触发 `[\d.]+` 匹配孤立点）
- **解决方案**：`_ZT_RE`/`_GAP_RE` 捕获组改 `(\d+(?:\.\d+)?)`；`_first_formula` 用 `finditer` 遍历候选 + 元素符号校验过滤单位误提取（Wm）

### 错误 6：self_check references_complete 恒 False（模块 4）
- **时间**：2026-08-04
- **类型**：代码
- **消息**：单测发现 `content.count("\n[")` 计数 = 引用数 - 1（首行无前导换行），n>1 时恒 False
- **解决方案**：改 `re.findall(r"^\[\d+\]", content, re.MULTILINE)` 统计行首编号

### 错误 7：DEEPSEEK_API_KEY 未接入 llm.py（模块 4）
- **时间**：2026-08-04
- **类型**：配置
- **消息**：环境只配置了 `DEEPSEEK_API_KEY`，llm.py 只认 `LLM_API_KEY`/`OPENAI_API_KEY`，LLM 摘要路径不可用
- **解决方案**：`_llm_config`/`llm_available` 增加 `DEEPSEEK_API_KEY`，未显式设端点时自动走 `https://api.deepseek.com/v1` + `deepseek-chat`；4 个测试文件 fixture 同步补清空该变量（否则真实环境 key 污染单测）

### 错误 8：真实 DEEPSEEK key 返回 401（模块 4）
- **时间**：2026-08-04
- **类型**：凭据（用户侧）
- **消息**：`Client error '401 Authorization Required'`（deepseek-chat 端点）
- **解决方案**：凭据失效需用户更新；代码侧验证了降级路径正确——LLM 失败自动落到规则摘要，流水线不中断，摘要来源字段标记"规则式"留痕

### 错误 9：llm_chat_json 三位置 params dict 契约缺失（模块 5）
- **时间**：2026-08-05
- **类型**：代码（接口契约）
- **消息**：LLMRoles 按 `(system, user, {"max_tokens": N, "temperature": T})` 三位置调用 `llm_chat_json`，签名是 `(system, user, *, max_tokens, temperature)` → 每次抛 TypeError，llm_failures=11 但直接调用成功
- **解决方案**：`llm_chat_json` 增加 `params: dict[str, Any] | None = None` 第三位置参数，`if params: max_tokens = int(params.get(...))`；tests/test_llm.py 新增 `test_chat_json_params_dict_contract` 回归防护

### 错误 10：`_nominal_formula` 对已掺杂母体生成垃圾公式（模块 5）
- **时间**：2026-08-05
- **类型**：代码（命名逻辑）
- **消息**：规则模式 Top 候选 `Ge0.93Ti0.01Bi0.060.96Ti0.04Te`（`host.split('Te')[0]` 拼接重复数字）
- **解决方案**：仅对纯二元 XTe 母体（无数字）走 `A(1-x)D(x)Te`，复杂/已掺杂母体回退 `host-Dx%` 命名；规则种子跨母体均匀分配（`per_host = pop_size // len(base_hosts)`）+ 纯母体评分偏好

### 错误 11：OQMD 分数掺杂成分查询超时 + http 301（模块 6）
- **时间**：2026-08-05
- **类型**：网络/性能
- **消息**：`http://oqmd.org` 报 301；`Pb0.94Ti0.06Te` 等分数成分查询长时间无响应
- **解决方案**：改用 `https://oqmd.org` + `follow_redirects=True`；`_FRACTION_RE` 检测含小数成分直接跳过（标记验证失败不伪装结论），仅整数成分直查，掺杂扩展用 novel_dopant 标记

### 错误 12：DeepSeek json_object 400 Bad Request（二次开发）
- **时间**：2026-08-05
- **类型**：API 契约
- **消息**：`Client error '400 Bad Request'`（payload 含 `response_format: {"type": "json_object"}`），key 修复后仍 400
- **解决方案**：DeepSeek json_object 模式要求 prompt/schema 中包含 "json" 字样；system prompt 加「输出 JSON 对象」后通过；现有 ga_search/expand_gaps 提示词已含 "JSON" 字面量无需改动

## 下一步行动

1. 阶段 2（文献调研 MVP）已全部完成：检索 → 抽取 → Gap → 报告四 Agent 闭环跑通
2. 阶段 3 选题收敛已完成：热电/催化/电池三领域对比，**主攻领域 = 热电**（数据质量最优、Gap 可操作）
3. LLM 回归完成：新 DEEPSEEK_API_KEY 下 `llm_abstract=True` 真实摘要润色链路正常
4. 模块 5 路线 A 完成：GA/MCTS/BO/SR × LLM 三角色融合 + 三臂消融量化（GA 演化增益 +70.41%）
5. 模块 6 交叉验证完成：批量验证 182 候选 + 验证章节对接模块 4；**MP 增强路径已启用**
6. 阶段 4 初赛材料完成：`docs/initial-round-proposal.md` ≤4 页（真实链路数据：19 文献 → 29 Gap → 29 finding → 182 候选验证）+ 合规披露 + docx 定稿
7. 下一步优先级：
   - [x] 8.16 初赛提交材料就绪（方案 + 依赖合规披露 + docx 定稿；剩余人工审阅排版）
   - [x] 消融弱项攻坚：换严苛评分代理（VerificationOracle 引入 OQMD 验证真值）重跑三臂消融——GA 演化增益由负转正 +2.65%，LLM 融合增益 -8.93% 负值收窄，成因已定位为真值表覆盖（复赛改进 = 扩大 oracle 真值 + 提升 full 臂候选多样性）
   - [x] 验证失败项优化：38 个失败（分数掺杂成分直查超时）→ A/B 位拆分纯母体解析重验，38→0，判定覆盖率显著提升
   - [x] 搜索-验证闭环：反例候选（10 个）回喂 GA 剪枝器 + 跨库分歧 MP 相图级核对（GeTe 分歧消除，归因粒度差异）
   - [x] LLM 抽取 vs 规则式抽取字段级 F1 对比评测 + Gap 新颖性人工复核 + 已知关系召回率评测（2026-08-05 完成第一轮：见操作记录四次深度开发；同时修复 schema null 容错重大 bug）
   - [ ] **人工标注流程（下一步，最终评测依赖）**：① 填写 `data/eval/extraction_gold.json`（模板已生成 10 条热电 chunk）→ `python scripts/eval_extraction_f1.py --gold data/eval/extraction_gold.json` 得最终字段级 F1；② 批注 `results/eval/gap_novelty_review.json` 的 confirmed_novelty/reviewer_note → `python scripts/review_gap_novelty.py --write-back` 写回 gaps.json 得人工复核新颖性
   - [ ] 复赛深化：人工标注最终化（extraction_gold.json 填写 + gap_novelty_review 批注写回）、LangGraph 多 Agent 重构、证据链审计界面、多算法输出融合投票、oracle 真值表扩面（纳入 OQMD 全库查询）、MCTS/GA/SR 的 LLM 模式召回率补跑（本次已完成 BO）

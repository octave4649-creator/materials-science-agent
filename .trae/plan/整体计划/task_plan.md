---
title: "整体开发计划·任务规划"
type: "plan"
category: "overall-plan"
tags: [整体计划, task_plan, GOAI, 赛道三, 材料文献智能体]
created: "2026-08-04"
updated: "2026-08-05"
status: "active"
version: "1.2"
---

# 整体开发计划 · 任务规划（task_plan）

## 任务目标

构建「方向三：材料科学文献驱动的科学发现智能体」参赛系统：文献调研 Agent（基本任务，必做）+ 路线 A 构效关系发现（进阶路线），全程证据链可审计，支撑初赛（8.16）/复赛（9.3）/决赛（9.22）三阶段提交。

## 约束条件

- 初赛 8.16 截止：方案说明文档 ≤4 页，不强制代码
- 评分：技术性能 45%（基本 50% + 路线 50%）、科学意义 30%、方法创新性 20%、开源贡献 5%
- 证据链可审计是通吃红线；搜索算法须与 LLM 深度融合
- 依赖资源：Sciverse API（`SCIVERSE_API_KEY`）、Materials Project（`MP_API_KEY`）、Sci-Base、MinerU
- 遵循 `.trae/rules/00-project-rules.md` 开发规范

## 阶段划分

### 阶段 1：准备与数据接入（8.4–8.10）
- [ ] 注册 Sciverse API Key，跑通 `sciverse auth login` + `sciverse semantic-search` CLI
- [x] 搭建 Python 3.10+ 环境，安装 sciverse/langgraph/pymatgen/mp-api/mineru
- [x] MinerU 解析 PDF 验证管线（模块 2 已跑通：`mineru -p -o -b pipeline`，miniconda 3.13）
- [ ] 注册 Materials Project API，跑通 mp-api 查询

### 阶段 2：文献调研 Agent MVP（8.6–8.13）
- [x] 模块1 检索 Agent：Sciverse 双通道检索（semantic_search + search_papers）+ 证据链记录
- [x] 模块2 抽取 Agent：LLM + schema 抽取成分/结构/性能/方法/条件
- [x] 模块3 Gap 识别：覆盖率分析 + 矛盾检测 + LLM 推理初版
- [x] 模块4 报告生成：结构化 Markdown 报告模板
- [x] 基本任务评测补强（2026-08-05）：字段级 F1（LLM vs 规则）+ 29 条 Gap 新颖性人工复核材料（Sciverse 回查写回）+ 已知关系召回率评测（GA/MCTS/BO/SR 四算法、explore_top 公平口径）——三项评测链路全部落盘 `results/eval/`，待人工 gold 标注与人工新颖性复核收尾
- [x] 基本任务评测补强·深度开发（2026-08-05）：BO 召回率增强（单 dopant 固定 → v2「dopant 外层遍历 × 浓度 BO 内层寻优」+ 初始浓度网格全覆盖 + 分数完整性修复）——规则模式 BO coverage 0.688（四算法最高，v1 全 0）；known_facts 5→16 条（6 池内 + 6 超池 + 4 超宿主，测覆盖边界）；召回率 LLM 模式（`--llm`）链路跑通（单条 fact 20 次批量评估 87.6s，kf-01 cov=Y），量化「LLM 参与探索」增益方向——BO 批量评估优化（每元素 LLM 调用 19→4 次）+ `--max-facts` 子集参数 + 进度打印；全量 16 条 LLM 评测留复赛夜间批量跑

### 阶段 3：选题收敛与路线 A 预研（8.10–8.14）
- [ ] 用调研 Agent 跑 2-3 个候选领域，比较 Gap 质量
- [ ] 确定主攻细分领域（热电/催化/电池/固态电解质）
- [ ] 验证 LLM × 搜索算法最小闭环（候选生成→评估→筛选）

### 阶段 4：初赛材料撰写（8.12–8.16）
- [ ] 撰写方案说明文档（≤4 页）
- [ ] 附 MVP demo / 检索示例 / 初步结果
- [ ] 8.16 提交初赛材料

### 阶段 5：复赛深化（8.25–9.3）
- [ ] LangGraph 多 Agent 状态机重构（含 HITL 审核节点）
- [ ] 完善证据链审计与统一日志
- [x] 路线 A 完整搜索循环（GA/MCTS/BO/SR × LLM 三角色融合 + 三臂消融 + 召回率评测）
- [ ] 数据库交叉验证（MP/OQMD/NOMAD）
- [ ] 完成 benchmark/自建评测集量化结果（字段级 F1 待人工 gold、召回率规则+LLM 双模式已落盘、新颖性待人工复核）
- [ ] 撰写实验报告、依赖披露、开源仓库整理

### 阶段 6：决赛展示（9.10–9.22）
- [ ] 海报：问题→方法→结果→科学意义四段式
- [ ] 现场 demo：问题→Gap→构效关系→数据库验证全流程
- [ ] 项目一页纸

## 技术决策

### 决策 1：进阶路线选择
- **背景**：三条路线任选其一，占评分 50%
- **选项**：路线 A（构效关系）/ 路线 B（模拟方法）/ 路线 C（合成路线）
- **选择**：路线 A 构效关系发现
- **理由**：与基本任务共享「文献→知识库→数据库」链路，无需实验/算力硬件，与「搜索×LLM 融合」「科学意义」高分维度天然契合

### 决策 2：Agent 编排框架
- **背景**：初赛需快速 MVP，复赛需多 Agent 编排
- **选项**：LangGraph / 自研流水线 / CrewAI
- **选择**：初赛简单流水线 → 复赛 LangGraph 状态机
- **理由**：LangGraph 支持状态图/条件路由/循环/HITL/checkpoint（arXiv:2607.19297），生产级首选

### 决策 3：文献检索接入
- **背景**：官方推荐 Sciverse，证据链可审计
- **选项**：MCP Server / Python SDK
- **选择**：Python SDK（`AgentToolsClient`）+ CLI 双通道
- **理由**：SDK 支持 `semantic_search`/`search_papers`/`read_content`/`list_catalog`/`get_resource` 五工具，异步客户端适合 Agent 运行时；CLI 便于快速验证

### 决策 4：细分领域选题
- **背景**：科学意义占 30%，须避免空泛
- **选项**：热电 / 催化 / 电池 / 固态电解质
- **选择**：待阶段 3 用调研 Agent 实测 Gap 质量后确定
- **理由**：数据驱动决策，先跑 2-3 个候选比较再收敛

## 里程碑

| 里程碑 | 时间 | 验收标准 |
|--------|------|---------|
| M1 数据链路打通 | 8.10 | Sciverse 检索 + MinerU 解析跑通 |
| M2 调研 Agent MVP | 8.13 | 检索→抽取→Gap→报告全链路可运行 |
| M3 选题确定 | 8.14 | 主攻领域确定且有 Gap 证据链 |
| M4 初赛提交 | 8.16 | 方案文档 ≤4 页提交成功 |
| M5 复赛系统 | 9.3 | 完整代码仓库 + 实验报告 + 依赖披露 |
| M6 决赛展示 | 9.22 | 海报 + demo + 一页纸 |

## 错误记录

### 错误 1：MinerU 环境与 CLI 语法踩坑
- **时间**：2026-08-04
- **原因**：主环境 Python 3.14 无 mineru wheel（官方 ≤3.13）；mineru 3.4.0 CLI 语法为 `-p/-o/-b`（文档写的 `parse -i -o --format` 已过时）；`python -m mineru` 不可用（包无 `__main__`）
- **解决方案**：`MINERU_PYTHON` 指向 miniconda 3.13；`MineruParser` 子进程定位 `Scripts\mineru.exe` 调用；backend 用 `pipeline`（纯 CPU）；缺 `shapely` 依赖已补装
- **重试次数**：4

## 关联文档

- 开发指导：`DEVELOPMENT-GUIDE.md`
- 项目规范：`.trae/rules/00-project-rules.md`
- 分项计划：`.trae/plan/分项计划/01-06/*`

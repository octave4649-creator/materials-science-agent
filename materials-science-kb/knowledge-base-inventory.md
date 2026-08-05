---
title: "材料科学文献智能体赛题 · 知识库清单"
category: "inventory"
tags: [知识库清单, 材料科学, 文献Agent, GOAI, 赛道三, 规划]
description: "面向「材料科学文献驱动的科学发现智能体」赛题的知识库建设清单，按四层架构列出全部知识条目、来源、用途、优先级与状态，作为备赛知识沉淀的施工蓝图"
created: "2026-08-04"
updated: "2026-08-04"
status: "review"
version: "1.0"
author: "参赛团队"
---

# 材料科学文献智能体赛题 · 知识库清单

## 概述

本清单是「材料科学文献驱动的科学发现智能体」赛题（GOAI 赛道三·方向三）的知识库施工蓝图。知识库按「采集层 → 结构化层 → 检索层 → 产出层」四层架构组织，每条目均标注来源、用途、优先级与状态，供团队按优先级逐步填充，确保知识可直接被 AI Agent 检索与产出。

## 一、赛题关键信息速览（来自赛题官方文档）

| 项目 | 内容 |
|------|------|
| 赛题名称 | 方向三：材料科学文献驱动的科学发现智能体 |
| 赛题结构 | 一个基本任务（文献调研 Agent，必做）+ 三条进阶路线（A 构效关系发现 / B 模拟方法创新 / C 合成路线与工艺设计）任选其一 |
| 评估体系 | 材料方向内部：基本任务 50% + 进阶路线 50% |
| 基本任务能力 | 文献检索与筛选、知识抽取、Research Gap 识别、调研报告生成 |
| 路线A要求 | 搜索/优化算法（遗传算法、MCTS、贝叶斯优化、符号回归等）与 LLM 深度融合，产出带证据链的构效关系 |
| 推荐数据资源 | Sci-Base、Sciverse API、MinerU、Materials Project、OQMD、NOMAD |
| 关键评分 | 技术性能 45%、科学意义 30%、方法创新性 20%、开源贡献 5% |

## 二、知识库四层架构

| 层级 | 作用 | 对应目录 |
|------|------|---------|
| 采集层 | 收拢散落知识（数据源、工具、论文） | `02-`、`03-`、`08-` |
| 结构化层 | 让 AI 可解析（分类、元数据、模板） | `01-`、`04-`、`05-`、`06-`、`07-`、`09-` |
| 检索层 | 知识可发现（_index 导航、标签体系） | `_index.md`、各目录 `_index.md` |
| 产出层 | 知识可产出（提交物模板） | `10-` |

## 三、知识条目清单

### 模块 1：赛题规则与要求（结构化层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 1.1 | 01-track-overview.md 赛道概览 | 赛道定位、背景、适合团队、奖项与资源支持 | 赛题手册 `赛道三：前沿探索AIforResearch.md` | 高 | 可复用赛题文档 |
| 1.2 | 02-direction-3-requirements.md 方向三赛题要求 | 基本任务+三路线详细要求、数据与工具资源、评估要点、提交物 | 赛题手册 | 高 | 可复用赛题文档 |
| 1.3 | 03-evaluation-criteria.md 评审标准 | 四维度权重、材料方向内评估口径（基本50%+路线50%）、开源合规 | 赛题手册 | 高 | 可复用赛题文档 |

> 说明：模块 1 内容已从赛题 docx 提取完毕，直接复制赛题手册对应章节即可，几乎无二次加工成本。

### 模块 2：文献数据资源（采集层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 2.1 | 01-sciverse-api.md Sciverse API 使用手册 | 4.66 亿学术元数据、2832 万+ AI-Ready OA 全文；六大核心 API（agentic-search / meta-search / meta-catalog / meta-paper-relations / content / resource）；MCP/Skills/CLI/SDK 四种接入方式；认证与配额 | [Sciverse 官方文档](https://sciverse.opendatalab.com/docs)、[Sciverse-Agent-Tools](https://github.com/opendatalab/Sciverse-Agent-Tools) | 高 | 待填充 |
| 2.2 | 02-sci-base.md Sci-Base 数据集 | 2500 万+ OA 文献、6000 亿+ tokens；Hugging Face `opendatalab/Sci-Base`；paper 3.61M 行 + textbook 22.7k 行；字段：abstract/author/content_list/doi/title 等；material 学科标签；CC-BY-4.0 | [Sci-Base HF 页面](https://huggingface.co/datasets/opendatalab/Sci-Base) | 高 | 待填充 |
| 2.3 | 03-mineru-parser.md MinerU 文档解析 | 开源文档解析引擎，PDF/DOCX/PPTX/XLSX/图片→Markdown/JSON；公式转 LaTeX、表格转 HTML、OCR 109 语言；pipeline/vlm/hybrid 三后端；Apache 2.0 自定义许可证 | [MinerU GitHub](https://github.com/opendatalab/MinerU) | 中 | 待填充 |
| 2.4 | 04-literature-retrieval-guide.md 文献检索策略 | 关键词/语义检索组合策略、Sciverse agentic-search 证据片段用法、meta-search 结构化筛选、引用反查 | 搜索整理 | 高 | 待填充 |

### 模块 3：材料数据库（采集层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 3.1 | 01-materials-project.md Materials Project | 14 万+ 材料 DFT 数据；带隙、生成能、能带、相图；API：`mp-api` + `MPRester`，需 MP_API_KEY；pymatgen 生态 | [MP 文档](https://docs.materialsproject.org) | 高 | 待填充 |
| 3.2 | 02-oqmd.md OQMD | 100 万+ 材料生成能与相图；开放 API | [OQMD](http://oqmd.org) | 中 | 待填充 |
| 3.3 | 03-nomad.md NOMAD | 计算材料科学数据仓库，注重共享与可复现；OPTIMADE 标准 | [NOMAD](https://nomad-lab.eu) | 中 | 待填充 |
| 3.4 | 04-aflow-jarvis.md AFLOW / JARVIS | AFLOW 350 万+ 结构（晶体对称、热力学）；JARVIS-DFT（光学性质、2D 材料） | 搜索整理 | 低 | 待填充 |
| 3.5 | 05-database-comparison.md 数据库对比与选型 | MP/AFLOW/OQMD/NOMAD/JARVIS 能力对比、适用场景、API 接入方式、授权 | 搜索整理 | 中 | 待填充 |

### 模块 4：基础任务·文献调研 Agent（结构化层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 4.1 | 01-agent-architecture.md Agent 架构设计 | 单 Agent vs 多 Agent；检索-抽取-分析-报告流水线；Sciverse MCP 接入；证据链审计设计 | 前沿论文+工程实践 | 高 | 待填充 |
| 4.2 | 02-knowledge-extraction.md 知识抽取方案 | 材料成分/结构/性能/模拟方法/合成条件抽取；LLM 结构化输出 schema；与 MinerU 解析结果联动 | 前沿论文 | 高 | 待填充 |
| 4.3 | 03-research-gap-identification.md Research Gap 识别 | 未被充分探索方向、矛盾结论、缺失知识连接识别方法；准确率与新颖性评估 | 前沿论文 | 高 | 待填充 |
| 4.4 | 04-report-generation.md 调研报告生成 | 结构化报告模板、文献交叉引用、Gap 证据链呈现、可读性控制 | 前沿论文 | 中 | 待填充 |

### 模块 5：路线A·构效关系发现（结构化层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 5.1 | 01-SPR-mining-methods.md 构效关系挖掘方法 | 材料_性质关联发现；LLM 生成候选假设作为搜索种子；科学合理性评估 | [dZiner](https://arxiv.org/abs/2410.03963)、[MatAgent](https://arxiv.org/abs/2504.00741) | 高 | 待填充 |
| 5.2 | 02-search-optimization.md 搜索优化算法 | 遗传算法、MCTS、贝叶斯优化、符号回归与 LLM 深度融合；搜索空间剪枝 | [CheMatAgent](https://arxiv.org/abs/2506.07551) | 高 | 待填充 |
| 5.3 | 03-database-cross-validation.md 数据库交叉验证 | Materials Project / OQMD / NOMAD 数据验证流程；区分「新知」与「已知」 | 搜索整理 | 中 | 待填充 |

### 模块 6：路线B·模拟方法创新（结构化层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 6.1 | 01-ml-potential-benchmarks.md ML 势函数与 Benchmark | MACE、NequIP、CHGNet 等；MD17、QM9、Materials Project 轨迹；DFT 加速、蒙特卡洛改进 | 前沿论文 | 中 | 待填充 |

### 模块 7：路线C·合成路线与工艺设计（结构化层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 7.1 | 01-retrosynthesis-methods.md 逆向合成方法 | 逆向合成分析（Retrosynthesis）与 LLM 推理结合；合成路线生成与工艺优化；文献依据支撑 | [ChemCrow](https://arxiv.org/abs/2304.05376)、搜索整理 | 中 | 待填充 |

### 模块 8：前沿研究与基准（采集层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 8.1 | 01-material-agent-papers.md 材料智能体论文库 | 代表性系统：CheMatAgent（137 工具+HE-MCTS）、dZiner（逆向设计）、ChatMat（多智能体）、ChemCrow、MatAgent、MOOSE-Chem、VASPilot、PhysAgent | 搜索整理 | 高 | 待填充 |
| 8.2 | 02-llm-materials-review.md LLM 材料综述 | Agentic Material Science（JMI 2026）；LLM in Materials Science（Digital Discovery 2026）；多智能体物理材料计算综述（物理学报 2026） | 搜索整理 | 高 | 待填充 |
| 8.3 | 03-benchmarks.md 评测基准 | 材料智能体评估：工具选择准确率、参数填充、发现任务成功率、ChemToolBench 等 | 搜索整理 | 中 | 待填充 |

### 模块 9：工具链（结构化层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 9.1 | 01-python-libs.md Python 工具库 | pymatgen、mp-api、RDKit、ASE、matplotlib；材料表示（CIF/分子描述符/图结构） | 搜索整理 | 高 | 待填充 |
| 9.2 | 02-simulation-software.md 模拟软件 | VASP、Quantum ESPRESSO、LAMMPS、Gaussian；DFT/MD 工作流自动化 | 搜索整理 | 中 | 待填充 |
| 9.3 | 03-llm-tool-integration.md LLM 工具集成 | MCP 协议、Function Calling、Sciverse MCP/Skill 接入；工具规划（Tool Planning）与执行 | 搜索整理 | 高 | 待填充 |

### 模块 10：提交材料模板（产出层）

| # | 条目 | 内容要点 | 来源 | 优先级 | 状态 |
|---|------|---------|------|--------|------|
| 10.1 | 01-problem-definition.md 问题定义文档模板 | 初赛问题定义文档（≤4 页）：问题真实性、AI 介入点、探索环境、发现信号、最小参照系 | 赛题手册 | 高 | 待填充 |
| 10.2 | 02-research-report.md 调研报告模板 | 文献调研报告：Research Gap 清单 + 文献交叉引用 + 证据链 + 系统说明 | 赛题手册 | 高 | 待填充 |
| 10.3 | 03-code-repo-checklist.md 代码仓库清单 | README、环境配置、运行说明、依赖/授权披露、复现说明、随机种子 | 赛题手册 | 高 | 待填充 |

## 四、检索层设计

### 标签体系

- `#赛题规则` `#文献数据源` `#材料数据库` `#文献Agent` `#构效关系` `#模拟方法` `#合成设计` `#前沿研究` `#工具链` `#提交模板`
- `#MCP` `#RAG` `#证据链` `#ResearchGap` `#逆合成` `#ML势函数` `#LLM`

### 关联引用规范

- 跨模块引用使用 `[[条目名]]` 形式，例如 `[[Sciverse API 使用手册]]`、`[[Research Gap 识别]]`
- 材料数据库条目互相引用：`[[Materials Project]]` ↔ `[[OQMD]]` ↔ `[[NOMAD]]`

## 五、产出层说明

本知识库配合赛题三阶段提交使用：

| 阶段 | 交付物 | 依赖知识模块 |
|------|--------|-------------|
| 初赛（7.16-8.16） | 问题定义文档（探索赛）或初步方案（算法赛） | 模块 1、4、8 |
| 复赛（8.25-9.3） | 可运行代码仓库 + 实验结果报告 | 模块 2、3、4、5/6/7、9 |
| 决赛（9.22） | 海报/路演、最终代码仓库、项目一页纸 | 全部模块 |

## 六、优先级与施工顺序建议

1. **第一优先级（本周完成）**：模块 1（直接复用赛题文档）+ 模块 2（Sciverse/Sci-Base/MinerU 接入验证）
2. **第二优先级（初赛前）**：模块 4（文献调研 Agent 设计与 demo）+ 模块 8（前沿论文对标）
3. **第三优先级（复赛前）**：模块 3（材料数据库验证）+ 模块 5/6/7（所选路线深化）+ 模块 9（工具链）
4. **贯穿全程**：模块 10（提交模板随阶段产出）

## 七、质量检查清单

- [x] 根目录 `_index.md` 导航文件已创建
- [x] 知识库清单含完整 YAML frontmatter
- [x] 标签分类体系已定义
- [x] 条目均标注来源、用途、优先级、状态
- [x] 四层架构（采集/结构化/检索/产出）映射清晰
- [ ] 各模块条目文件逐步填充（待施工）
- [ ] 各子目录 `_index.md` 待创建

---

> 相关文档：[[材料科学文献智能体赛题 · 知识库导航]]

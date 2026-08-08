---
alwaysApply: true
---
# 前沿研究与基准

## 1. 材料智能体论文库

### 1.1 代表性系统

| 系统 | 核心方法 | 适用路线 | 链接 |
|------|---------|---------|------|
| ChemCrow | LLM + 18 种化学工具；GPT-4 低幻觉推理 | 路线C | [arXiv:2304.05376](https://arxiv.org/abs/2304.05376) |
| dZiner | LLM 智能体逆向设计 + 代理模型迭代评估 | 路线A | [arXiv:2410.03963](https://arxiv.org/abs/2410.03963) |
| MOOSE-Chem | 假设生成 + 自动化实验 | 路线A/C | [arXiv:2410.07076](https://arxiv.org/abs/2410.07076) |
| MatAgent | 生成式 AI 智能体无机材料设计 | 路线A | [arXiv:2504.00741](https://arxiv.org/abs/2504.00741) |
| CheMatAgent | 137 工具 + 分层进化 MCTS（HE-MCTS） | 路线A/C | [arXiv:2506.07551](https://arxiv.org/abs/2506.07551) |
| ChatMat | 多智能体化学家（Manager + 4 角色） | 路线B | Digital Discovery 2026 |
| MOSAIC | 模块化合成 AI，复杂分子逆向合成 | 路线C | 耶鲁/勃林格殷格翰 |
| Aitomia | ML 驱动化学计算 Agent，较 DFT 快 10-100 倍 | 路线B | 厦门大学 |
| MolAid | 30 亿+ 分子、8000 万+ 反应数据平台 | 路线C | 化学合成辅助 |

### 1.2 各系统对赛题的关键启示

- **CheMatAgent**：HE-MCTS 框架——高层策略模型选工具、低层策略模型执行任务，是「搜索与 LLM 深度融合」的直接参考
- **dZiner**：逆向设计循环 + 合成可行性评估，路线A「搜索空间引导」的参考
- **ChatMat**：多智能体分工模式（属性存储/计算设计/DFT 操作/ML 势函数），路线B 编排参考
- **ChemCrow / MOSAIC**：合成路线生成与工具集成，路线C 参考

## 2. LLM 材料综述（2026 年更新）

| 综述 | 内容 | 参考价值 |
|------|------|---------|
| Agentic Material Science（J. Mater. Inf. 2026, 6, 10） | 材料科学中的智能体研究系统综述 | 全局方法版图、系统分类 |
| LLM in Materials Science（Digital Discovery 2026, d5dd00499c） | 文献挖掘、预测建模、多智能体实验 | 文献挖掘方法深度解析 |
| 多智能体在物理材料计算领域的应用（物理学报 2026） | 计算材料学多智能体框架 | VASPilot、PhysAgent 等介绍 |

### 综述核心结论（供对标）

- 材料智能体主流范式：LLM 作为「大脑」+ 专业工具/数据库作为「手脚」
- 三大应用：文献挖掘（抽取-组织-发现）、性质预测（模型+数据）、实验/模拟自动化
- 共同挑战：证据链可靠性、幻觉控制、工具调用准确性

## 3. 评测基准

### 3.1 材料智能体评估维度

| 维度 | 指标 | 适用 |
|------|------|------|
| 工具选择 | 工具选择准确率 | 全部 |
| 参数填充 | 工具参数正确性 | 全部 |
| 发现任务 | 发现任务成功率 | 路线A |
| 文献挖掘 | 知识抽取 F1、Gap 新颖性 | 基本任务 |

### 3.2 现有 Benchmark

- **ChemToolBench**：化学工具调用基准（CheMatAgent 配套）
- **MD17 / QM9 / Materials Project 轨迹**：模拟方法精度基准（路线B）
- **Sci-Review-Bench**：Sciverse 配套的综述生成评测基准（含快速评测）
- 材料智能体评测体系（如 MatAgent 相关评测）：无机材料设计成功率

## 4. 方法论趋势（2026）

1. **搜索 × LLM 深度融合**：搜索算法为骨架、LLM 为智能扩展器/评估器（路线A 核心趋势）
2. **多智能体协作**：角色分工取代单一巨型 Prompt（路线B 趋势）
3. **证据链可审计**：AI 决策可回溯成为硬性要求（贯穿所有路线）
4. **多模态文献理解**：图表知识纳入文献挖掘（配合 Sciverse resource API + MinerU）

## 5. 生物材料/蛋白质组学 AI 前沿（新增）

### 5.1 蛋白质组学 + AI 代表性进展

| 进展 | 方法 | 数据/应用 | 参考价值 |
|------|------|----------|---------|
| AlphaFold 系列 | 深度强化学习 | 蛋白结构预测 | 蛋白3D结构→功能关联 |
| Evo 系列 (ProteinMPNN) | 生成式模型 | 蛋白质设计 | 新功能蛋白生成 |
| RFDiffusion | 扩散模型 | 蛋白结构生成 | 生物材料设计 |
| Chronos (protein) | 基础模型 | 零样本蛋白预测 | 跨任务迁移学习 |
| ProtGPT2 | 语言模型 | 蛋白序列生成 | 功能蛋白发现 |

### 5.2 酵母蛋白质组学 AI 研究热点

1. **菌株-条件-蛋白关联挖掘**：利用大规模扰动数据构建基因调控网络
2. **代谢通路的 AI 重构**：从蛋白表达数据预测代谢流分布
3. **温度响应的分子机制**：AI 辅助热休克蛋白的功能注释
4. **碳源代谢切换的基因表达重编程**：AI 模拟葡萄糖→半乳糖的代谢转换
5. **化学扰动的离线筛选**：AI 预测新化学物质对酵母的扰动效应

### 5.3 WAYB/WAYC 数据集相关研究线索

- WAYB (Yeast Whole-genome Ablation Barcode) / WAYC (Yeast Whole-genome Conditional) 是酵母全基因组扰动数据集
- 关联研究：**Yeast Proteome Atlas** 构建了酵母在多种条件下的蛋白表达图谱
- 关键文献方向：酵母热休克响应、代谢工程、蛋白组学质量控制
- 可检索关键词："yeast proteome atlas"、"Saccharomyces cerevisiae perturbation"、"yeast temperature response proteomics"

### 5.4 生物材料 AI 评估基准

- **ProteomeBench**：蛋白质组学预测基准
- **ProteinGym**：蛋白结构预测基准
- **YeastNet**：酵母基因调控网络推断基准
- 本项目可基于 WAYB/WAYC 构建**生物材料构效关系评测基准**

## 6. 跟踪渠道

- arXiv：`cs.AI`、`cs.CL`、`cond-mat.mtrl-sci`、`physics.chem-ph`、`q-bio.QM`（量化生物学）分类
- 关注组：OpenDataLab、Datawhale、AI4Science 社区、Yeast Proteome Atlas
- 关键词：`materials agent`、`scientific discovery agent`、`LLM materials science`、`yeast proteomics`、`protein structure prediction`、`gene expression AI`

---

> 相关文档：[[基础任务·文献调研 Agent]]、[[路线A·构效关系发现]]、[[路线B·模拟方法创新]]、[[路线C·合成路线与工艺设计]]

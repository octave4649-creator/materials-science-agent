---
name: "frontier-research"
description: "提供材料科学 AI 智能体的前沿研究与评测基准：代表性系统（ChemCrow/dZiner/CheMatAgent/ChatMat/MOSAIC/Aitomia）、2026 年 LLM 材料综述、评测维度与 benchmark。当需要对标前沿方法、参考论文、设计评测时调用。"
---

# 前沿研究与基准

## 1. 代表性系统

| 系统 | 核心方法 | 适用路线 | 链接 |
|------|---------|---------|------|
| ChemCrow | LLM + 18 种化学工具 | 路线C | arXiv:2304.05376 |
| dZiner | LLM 逆向设计 + 代理模型 | 路线A | arXiv:2410.03963 |
| MOOSE-Chem | 假设生成 + 自动化实验 | 路线A/C | arXiv:2410.07076 |
| MatAgent | 生成式 AI 无机材料设计 | 路线A | arXiv:2504.00741 |
| CheMatAgent | 137 工具 + HE-MCTS | 路线A/C | arXiv:2506.07551 |
| ChatMat | 多智能体化学家（Manager+4 角色） | 路线B | Digital Discovery 2026 |
| MOSAIC | 复杂分子逆向合成 | 路线C | 耶鲁/BI |
| Aitomia | ML 化学计算 Agent，比 DFT 快 10-100 倍 | 路线B | 厦大 |
| MolAid | 30 亿+ 分子、8000 万+ 反应数据 | 路线C | 化学合成 |

## 2. 对赛题的关键启示

- **CheMatAgent**：HE-MCTS——高层选工具、低层执行，是「搜索×LLM 深度融合」直接参考
- **dZiner**：逆向设计循环 + 合成可行性评估
- **ChatMat**：多智能体分工（属性/计算设计/DFT/ML 势函数）
- **ChemCrow / MOSAIC**：合成路线生成与工具集成

## 3. 2026 年综述

| 综述 | 参考价值 |
|------|---------|
| Agentic Material Science（J. Mater. Inf. 2026, 6, 10） | 全局方法版图 |
| LLM in Materials Science（Digital Discovery 2026） | 文献挖掘方法深度解析 |
| 多智能体物理材料计算综述（物理学报 2026） | VASPilot、PhysAgent 等 |

**共同结论**：材料智能体主流范式 = LLM 大脑 + 专业工具/数据库手脚；挑战 = 证据链可靠性、幻觉控制、工具调用准确性。

## 4. 评测基准

| 维度 | 指标 | 适用 |
|------|------|------|
| 工具选择 | 工具选择准确率 | 全部 |
| 参数填充 | 工具参数正确性 | 全部 |
| 发现任务 | 发现任务成功率 | 路线A |
| 文献挖掘 | 抽取 F1、Gap 新颖性 | 基本任务 |

Benchmark：ChemToolBench、MD17、QM9、MP 轨迹、Sci-Review-Bench。

## 5. 方法论趋势

1. 搜索 × LLM 深度融合（路线 A 核心趋势）
2. 多智能体协作取代单一巨型 Prompt
3. 证据链可审计成为硬性要求
4. 多模态文献理解（图表知识 + resource API + MinerU）

---

> 详细见 `.trae/rules/08-frontier-research.md`；评测体系见 `DEVELOPMENT-GUIDE.md` 第 6 节。

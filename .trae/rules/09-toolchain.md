---
alwaysApply: true
---
# 工具链

## 1. Python 工具库

### 1.1 材料计算核心库

| 库 | 功能 | 用途 |
|----|------|------|
| pymatgen | 晶体结构分析、相图、电子结构；MP 官方配套 | 结构处理、特征计算 |
| mp-api | Materials Project API 客户端（MPRester） | 数据库查询 |
| ASE | 原子模拟环境：结构、计算器、工作流 | MD/DFT 工作流、结构操作 |
| RDKit | 化学信息学：分子表示、描述符、反应处理 | 分子/材料描述符、路线C |
| jarvis-tools | NIST JARVIS 数据访问与机器学习工具 | 2D 材料、光学性质 |

### 1.2 材料表示与描述符

| 表示方法 | 说明 | 适用 |
|---------|------|------|
| CIF 结构 | 晶体学信息文件 | 结构输入输出 |
| 分子描述符 | 组成、拓扑、电子描述符 | 性质预测特征 |
| 图结构表示 | 晶体图/分子图 | GNN 模型输入 |
| 成分向量 | 元素比例编码（如 Magpie 特征） | 高通量筛选 |
| 结构描述符 | 配位数、键长分布、局部有序 | 构效关系（路线A） |

### 1.3 数据与可视化

- pandas / polars：结构化数据处理
- numpy / scipy：数值计算
- matplotlib / plotly：可视化
- datasets（Hugging Face）：加载 Sci-Base 等数据集

## 2. 模拟软件

| 软件 | 类型 | 用途 |
|------|------|------|
| VASP | DFT | 电子结构、几何优化（MP 数据来源） |
| Quantum ESPRESSO | DFT | 开源 DFT，脚本化工作流 |
| LAMMPS | 分子动力学 | 大规模 MD 模拟 |
| Gaussian | 量子化学 | 分子性质计算 |

> 说明：路线 B（模拟方法创新）可基于上述软件做加速/自动化封装，配合 ML 势函数（MACE、NequIP、CHGNet）使用。

## 3. LLM 工具集成

### 3.1 MCP（Model Context Protocol）

- **Sciverse MCP**：`sciverse-mcp-server`，npx 启动，暴露六类文献 API
- **MatRouter**：本地优先 MCP server，聚合 MP/AFLOW/OQMD/NOMAD 材料数据路由，Agent 化数据访问
- 优势：工具标准化、调用记录可审计（证据链）

### 3.2 Function Calling / Tool Planning

- 将材料库/数据库 API 封装为可调用工具（JSON Schema 描述）
- LLM 通过 Function Calling 动态规划工具调用序列
- 高级模式：分层策略模型（如 CheMatAgent 的 HE-MCTS）——高层选工具、低层执行

### 3.3 RAG 与知识库检索

- 向量库：chroma / qdrant / faiss
- 嵌入模型：bge-m3、gte 等中文/多语言模型
- 检索流程：文献片段向量化 → 语义检索 → LLM 生成

## 4. 推荐技术栈（初赛 MVP）

```
语言：Python 3.10+
LLM 接入：OpenAI API / 国产大模型 API / 本地模型（vLLM）
Agent 框架：LangChain / LangGraph 或自定义（轻量级优先）
文献检索：Sciverse MCP Server（必用，证据链）
文档解析：MinerU（pipeline 后端即可起步）
材料数据：mp-api + pymatgen（路线A 必需）
向量检索：chroma（本地、轻量）
前端/展示：Streamlit / Gradio（demo 演示）
```

## 5. 环境搭建示例

```bash
# 基础环境
conda create -n matagent python=3.10 -y
conda activate matagent

# 材料计算
pip install pymatgen mp-api ase rdkit

# Sciverse 工具
npx -y sciverse-mcp-server  # 或 pip install sciverse-agent-tools

# 文档解析
pip install "mineru[all]"

# 数据与可视化
pip install pandas numpy matplotlib datasets
```

## 6. 工具链选型原则

1. **证据链优先**：优先选用调用记录可审计的工具（Sciverse MCP）
2. **轻量起步**：初赛用最少工具跑通 MVP，复赛再扩展
3. **开源可复现**：优先开源工具（Apache/MIT 协议），符合开源贡献评审维度
4. **避免重复造轮子**：成熟能力（检索、解析、计算）直接集成，创新集中在搜索融合与 Agent 编排

---

> 相关文档：[[文献数据资源]]、[[材料数据库]]、[[前沿研究与基准]]

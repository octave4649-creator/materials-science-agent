---
alwaysApply: true
---
# 文献数据资源

## 1. Sciverse 科学智能数据库

### 1.1 定位

Sciverse 是 OpenDataLab（上海人工智能实验室）推出的**科学数据基座**，将海量公开学术文献处理为原生 Agent 友好的 AI-Ready 科学数据，支持元数据检索、语义证据片段、原文上下文和图表资源调用。赛题官方明确推荐使用 Sciverse API 的 MCP/Skill 接入方式，**其调用记录天然构成可审计的证据链**。

### 1.2 数据规模

| 指标 | 数值 |
|------|------|
| 学术元数据 | 4.66 亿条（跨论文、图书、专利） |
| 论文记录 | 3.59 亿条 |
| 图书记录 | 1.06 亿条 |
| 专利记录 | 7000 万条 |
| AI-Ready OA 全文 | 2832 万篇 |
| 期刊/会议覆盖 | 193 万 |

### 1.3 六大核心 API

| API | 用途 | 典型链路 |
|-----|------|---------|
| `agentic-search` | 语义证据检索：自然语言问题→可引用证据片段 | agentic-search → content → 带来源证据输出 |
| `meta-search` | 结构化元数据检索：按年份/期刊/作者/引用数筛选 | meta-catalog → meta-search → 论文清单 |
| `meta-catalog` | 字段能力发现：枚举可用字段与样例值，避免 Agent 编造不存在的字段 | meta-catalog → meta-search |
| `meta-paper-relations` | 论文关系网络检索：引文反查、关联扩展 | 证据链扩展、文献溯源 |
| `content` | 原文片段/上下文读取：防止只看 snippet 就下结论 | 全文核验、引用定位 |
| `resource` | 拉取图片、表格等二进制资源：支持 figure-aware 多模态 RAG | 图表证据、多模态检索 |

### 1.4 接入方式

- **API**：REST 接口，统一在 Console > Tokens 创建 API Key，同一 Key 可复用
- **Skills (MCP)**：`sciverse-mcp-server`，支持 npx 直接启动
- **CLI / SDK**：Python / TypeScript 官方包 `Sciverse-Agent-Tools`
- **Agent 工具模式**：支持 Anthropic / OpenAI 工具模式接入（Claude、Cursor、Codex）

### 1.5 典型应用场景

- 自动文献综述（Generate review）
- 论文短清单生成（Paper shortlist）
- 研究方向持续追踪（Track research direction）
- Scientific RAG、Citation Grounding、Evidence Pack 构建
- 跨文档方法对比、图表证据查找、论文与专利技术表达对照

### 1.6 参考资源

- 官方文档：https://sciverse.opendatalab.com/docs
- 工具仓库：https://github.com/opendatalab/Sciverse-Agent-Tools（v0.11.0，2026-07-31）
- 在线体验：https://sciverse.space
- 常用 Cookbook：AgentRAG 文献综述、Scientific RAG 数据源、全文证据检索

## 2. Sci-Base 数据集

### 2.1 定位

Sci-Base 是 Sciverse 的底层科学通识层，**全球规模最大的通用科学数据底座**，依托 MinerU 对超过 2500 万篇开放获取（OA）科学文献与书籍进行高质量数字化重构，沉淀出 6000 亿级 Tokens 高质量科学语料。

### 2.2 数据规模

- 2500 万+ 篇 OA 科学文献与书籍
- 6000 亿+ AI-Ready Tokens
- 覆盖自然科学 10+ 个一级核心学科
- 数据已更新至 2026 年（优于主流大模型知识截断时间）
- License：CC-BY-4.0

### 2.3 Hugging Face 数据集

- 地址：https://huggingface.co/datasets/opendatalab/Sci-Base
- Subset：`paper`（3.61M 行）、`textbook`（22.7k 行）
- 主要字段：`abstract`、`author`、`content_list`（结构化正文，含 bbox、表格、图片等）、`doi`、`is_oa`、`language`、`sci_category`（含 material 学科）、`sha256`、`title`
- 加载方式：

```python
from datasets import load_dataset

# 加载特定学科（如材料科学）
data = load_dataset("opendatalab/Sci-Base", "material")
# 或加载全部
data = load_dataset("opendatalab/Sci-Base")
```

### 2.4 用途

- 本地/离线构建材料科学文献语料库
- 材料文献智能体的检索底库与微调语料
- Research Gap 分析的知识基础
- 与 Sciverse API 互补：本地批处理用 Sci-Base，实时证据检索用 Sciverse

## 3. MinerU 文档解析引擎

### 3.1 定位

MinerU 是 OpenDataLab 开源的**智能文档解析引擎**，专为 LLM、RAG 和 Agent 工作流设计，将 PDF、DOCX、PPTX、XLSX、图片、网页等格式转换为结构化的 Markdown 或 JSON。GitHub 15k+ stars，2026 年 4 月起采用 Apache 2.0 风格自定义开源许可证（商业部署门槛大幅降低）。

### 3.2 核心能力

- **文档解析**：PDF/DOCX/PPTX/XLSX/图片 → Markdown/JSON
- **公式转换**：自动识别公式并转为 LaTeX 格式
- **表格转换**：自动识别表格并转为 HTML，支持跨页表格合并（缝合准确率 99.2%）
- **OCR**：109 种语言检测识别，自动启用于扫描版 PDF
- **版面分析**：标题、正文、表格、图片、公式区域识别；阅读顺序优化（双栏论文）
- **语义一致性**：移除页眉页脚脚注页码，确保语义连贯

### 3.3 三种解析后端

| 后端 | 特点 | 适用场景 |
|------|------|---------|
| pipeline | 传统 CV+NLP 流水线，速度快、无幻觉、确定性输出；纯 CPU 可运行（16GB 内存） | 大规模批量解析、无 GPU 环境 |
| vlm-engine | 基于自研 MinerU2.5-Pro VLM 模型，SOTA 精度（OmniDocBench 95.39）；需 GPU（8GB+） | 复杂布局、多栏混排、高精度要求 |
| hybrid-engine | pipeline 速度 + VLM 精度平衡（3.3 版本引入） | 精度与速度折中场景 |

### 3.4 安装与使用

```bash
# 安装（uv 方式）
pip install uv
uv pip install -U "mineru[all]"

# 命令行解析 PDF 生成 Markdown
mineru parse -i research_paper.pdf -o report.md --format markdown

# 批量处理文件夹
mineru batch -d ./docs -o ./output --threads 8

# 下载模型
mineru download-models --all
```

```python
# Python API
from mineru import DocumentParser

parser = DocumentParser(enable_table_merge=True, ocr_langs=["en", "zh"])
result = parser.parse("research_paper.pdf")
print(result.tables[0].to_html())   # 表格转 HTML
print(result.equations[0].latex)    # 公式 LaTeX 源码
```

### 3.5 在赛题中的用途

- 解析非 OA 或本地的材料科学文献 PDF（Sci-Base 未覆盖部分）
- 将文献解析为结构化 Markdown 供知识抽取模块使用
- 构建私有材料文献知识库的预处理管线

## 4. 文献检索策略

### 4.1 双通道检索架构

| 通道 | 工具 | 适用场景 |
|------|------|---------|
| 语义检索 | Sciverse `agentic-search` | 以自然语言研究问题找证据片段 |
| 结构化筛选 | Sciverse `meta-search` | 按年份/期刊/作者/学科精确过滤 |

### 4.2 推荐检索流程

1. **问题拆解**：将研究问题拆分为可检索的多个子问题
2. **结构化筛选**：用 meta-catalog 确认可用字段，meta-search 初筛候选论文
3. **语义证据**：用 agentic-search 定位关键证据片段
4. **原文核验**：用 content 读取原文上下文，防止只看 snippet 下结论
5. **图表调用**：用 resource 获取图表等二进制资源
6. **关系扩展**：用 meta-paper-relations 做引文反查与关联扩展
7. **证据打包**：汇总证据链，记录来源、DOI、页码、检索时间

### 4.3 证据链审计设计

- 每次检索调用记录：查询词、检索时间、返回结果 ID、采用片段及原文位置
- 生成的每个结论关联至少一条可回溯的证据
- 证据链输出格式建议：`结论 → 证据片段（来源 DOI / 页码 / API 调用记录）`

### 4.4 关键词策略

- 中英文双语关键词
- 结合学科术语：如构效关系（Structure-Property Relationship）、材料基因（Materials Genome）、高通量（High-throughput）等
- 使用布尔组合与近义词扩展

### 4.5 生物材料/蛋白质组学检索策略（新增）

针对 WAYB/WAYC 酵母蛋白质组学数据集，检索关键词需扩展到生物材料领域：

| 关键词类别 | 英文关键词 | 中文关键词 |
|-----------|-----------|-----------|
| 模式生物 | Saccharomyces cerevisiae, yeast | 酿酒酵母，酵母 |
| 组学技术 | proteomics, mass spectrometry, TMT | 蛋白质组学，质谱，TMT标记 |
| 数据来源 | WAYB, WAYC, Yeast Proteome Atlas | WAYB，WAYC，酵母蛋白质组图谱 |
| 扰动实验 | chemical perturbation, drug response, perturbation | 化学扰动，药物响应，扰动反应 |
| 构效关系 | gene expression-phenotype, protein-function, strain performance | 基因表达-表型，蛋白功能，菌株性能 |
| 条件控制 | temperature response, carbon source, galactose, glucose | 温度响应，碳源，半乳糖，葡萄糖 |
| 数据库 | Proteome Atlas, UniProt, YeastMine | 蛋白质组图谱，UniProt，YeastMine |

**检索示例**：
- `("Saccharomyces cerevisiae" OR "yeast") AND (proteomics OR "gene expression") AND ("chemical perturbation" OR "drug response")`
- `WAYB WAYC yeast proteome strain temperature galactose`

---

> 相关文档：[[赛题规则与要求]]、[[基础任务·文献调研 Agent]]、[[材料数据库]]

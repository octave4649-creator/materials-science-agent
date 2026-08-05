---
name: "literature-data-sources"
description: "提供材料文献智能体赛题的文献数据资源接入方法：Sciverse API（六大核心 API）、Sci-Base 数据集、MinerU 解析引擎、文献检索策略与证据链设计。当需要实现文献检索、接入 Sciverse/Sci-Base、解析 PDF 文档或构建证据链时调用。"
---

# 文献数据资源接入

## 1. Sciverse API（首选，证据链天然可审计）

**数据规模**：4.66 亿条学术元数据、2832 万+ AI-Ready OA 全文。

### 六大核心 API

| API | 用途 | 典型链路 |
|-----|------|---------|
| `agentic-search` | 语义证据检索→可引用证据片段 | agentic-search → content |
| `meta-search` | 结构化元数据检索（年份/期刊/作者筛选） | meta-catalog → meta-search |
| `meta-catalog` | 枚举可用字段，防 LLM 编造字段 | 检索前置 |
| `meta-paper-relations` | 引文反查、关联扩展 | 证据链扩展 |
| `content` | 原文片段/上下文核验 | 全文核验 |
| `resource` | 图片/表格二进制资源 | 多模态检索 |

### 接入方式

- **MCP**：`sciverse-mcp-server`（npx 启动）
- **SDK**：`Sciverse-Agent-Tools` → `AgentToolsClient`
- API Key 存环境变量 `SCIVERSE_API_KEY`

```python
import asyncio
from sciverse import AgentToolsClient

async def search_literature(query: str, top_k: int = 5):
    async with AgentToolsClient() as client:
        semantic = await client.semantic_search(query, top_k=top_k)
        meta = await client.search_papers(query=query, year_from=2020, page_size=10)
        return semantic, meta
```

## 2. Sci-Base 数据集（本地语料）

- Hugging Face：`opendatalab/Sci-Base`（CC-BY-4.0）
- 2500 万+ OA 文献、6000 亿+ tokens、更新至 2026 年
- 字段：`abstract`、`author`、`content_list`、`doi`、`is_oa`、`sci_category`（含 material）、`title`

```python
from datasets import load_dataset
data = load_dataset("opendatalab/Sci-Base", "material")
```

## 3. MinerU 文档解析

- 三后端：pipeline（纯 CPU 可跑）/ vlm-engine（GPU，SOTA）/ hybrid（平衡）
- PDF/DOCX/PPTX/XLSX → Markdown/JSON；表格转 HTML；公式转 LaTeX；OCR 109 语言

```bash
mineru parse -i paper.pdf -o report.md --format markdown
```

## 4. 检索策略

1. 问题拆解为子问题 → 2. meta-search 初筛 → 3. agentic-search 找证据 → 4. content 原文核验 → 5. meta-paper-relations 引文扩展 → 6. 证据打包

## 5. 证据链记录

每次调用记录：查询词、时间戳、返回 doc_id、DOI、采用片段。输出格式：`结论 → 证据片段（来源 DOI / 页码 / API 调用记录）`。

---

> 详细见 `.trae/rules/02-literature-data-sources.md`；证据链结构见 `00-project-rules.md` 第 4 节。

---
title: "分项计划·模块1 文献检索 Agent · 研究发现"
type: "plan"
category: "subplan"
tags: [检索Agent, findings, Sciverse]
created: "2026-08-04"
updated: "2026-08-04"
status: "active"
version: "1.1"
---

# 模块1 文献检索 Agent · 研究发现（findings）

## 技术调研

### Sciverse SDK 调用示例（v0.6.3+）

```python
import asyncio
from sciverse import AgentToolsClient

async def search_literature(query: str, top_k: int = 5):
    async with AgentToolsClient() as c:  # token + endpoint 自动解析
        # 1. 语义检索（向量+BM25 混合，返回 chunk 证据片段）
        semantic = await c.semantic_search(query=query, top_k=top_k, mode="balanced")
        for hit in semantic["hits"]:
            print(hit["doc_id"], hit["score"], hit["title"])
        # 2. 结构化筛选
        meta = await c.search_papers(query=query, year_from=2020, page_size=10)
        # 3. 原文回读（配合 doc_id + offset）
        content = await c.read_content(doc_id=meta["hits"][0]["doc_id"], offset=0, limit=8192)
        # 4. 字段 introspection（Agent 接入第一步）
        catalog = await c.list_catalog()
        return semantic, meta
```

### CLI 快速验证

```bash
sciverse auth login                          # 浏览器取 token
sciverse semantic-search "热电材料 掺杂" --top-k 5 | jq '.hits[].title'
sciverse search --author Hinton --year-from 2020 --page-size 3
sciverse content p_xxx --offset 0 --limit 8192 | jq -r '.text'
sciverse catalog --samples | jq '.fields[] | select(.sample_values | length > 0)'
sciverse resource "dt=xxx/p_yyy/f3.png" -o /tmp/figure.png
```

### 证据链闭环（官方 cookbook 模式）

问题提出 → 结构化筛选（meta-search）→ 语义检索（agentic-search）→ 原文回读（content）→ 图表获取（resource）→ 证据打包 → LLM 生成 → 引用回链

## 重要发现

### 发现 1：证据片段字段
- **内容**：semantic_search 返回 hit 含 doc_id、score、title、doi、page_no、snippet/chunk
- **影响**：doc_id + offset 可直接定位原文段落，构成可审计证据
- **建议**：EvidenceItem 记录 doc_id + page + snippet，溯源完整

### 发现 2：检索模式三档
- **内容**：`mode=fast|balanced|quality`
- **影响**：批量初筛用 fast，关键证据定位用 quality
- **建议**：初筛 fast + 精读 quality 两段式

### 发现 3（实测）：两通道返回结构不同
- **内容**：语义检索返回 `hits[]`（含 chunk 证据片段、page_no、score、doc_id）；
  结构化检索返回 `results[]`（含 unique_id、doi、citation_count、isbn13 等元数据）
- **影响**：统一结构必须兼容两套字段，doc_id 仅全文存在时返回
- **建议**：封装层归一化（已实现 `_hit_to_paper` / `_result_to_paper`）

### 发现 4（实测）：unique_id vs doc_id
- **内容**：`unique_id` 是元数据记录全局 ID（无全文也有，如 ebook:9781394317356）；
  `doc_id` 是全文内容 sha256 哈希（仅全文存在时返回）
- **影响**：去重与引用时应 doc_id 优先、unique_id 兜底，缺省用归一化标题
- **建议**：`_dedupe_key` 三级键策略（doc → uid → title）

### 发现 5（实测）：token 变量名与凭据文件
- **内容**：SDK 环境变量名为 `SCIVERSE_API_TOKEN`（技能文档写 SCIVERSE_API_KEY）；
  `sciverse auth login --token <t>` 保存到 `~/.sciverse/credentials.json`（0600）
- **影响**：代码读取须兼顾环境变量 + 凭据文件，否则「CLI 能用 SDK 不能用」
- **建议**：config.py `sciverse_token()` 环境变量优先、凭据文件兜底（已修复）

## 资源链接

- SDK：https://pypi.org/project/sciverse/
- 工具仓库：https://github.com/opendatalab/Sciverse-Agent-Tools
- 科研 RAG Demo：https://segmentfault.com/a/1190000047832013

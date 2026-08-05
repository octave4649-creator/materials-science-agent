---
title: "整体开发计划·研究发现"
type: "plan"
category: "overall-plan"
tags: [整体计划, findings, 研究发现, Sciverse, LangGraph]
created: "2026-08-04"
updated: "2026-08-04"
status: "active"
version: "1.0"
---

# 整体开发计划 · 研究发现（findings）

## 技术调研

### Sciverse Python SDK（v0.6.3+，最新 v0.11.0）
- **结果**：官方 SDK `pip install sciverse`，异步客户端 `AgentToolsClient`，提供五类检索工具
- **工具清单**：
  - `semantic_search(query, top_k=10, mode="fast|balanced|quality")`：语义检索（向量+BM25 混合），返回 chunk 证据片段
  - `search_papers(...)`：结构化元数据筛选（author/year/journal/subject/title-contains/sort）
  - `read_content(doc_id, offset=0, limit=8192)`：按字节区间读原文，配合 doc_id+offset
  - `list_catalog()`：字段 introspection（Agent 接入第一步先枚举可用字段，防编造）
  - `get_resource(file_name, -o out.png)`：论文图片二进制（figure-aware 多模态）
- **认证**：`sciverse auth login` → 浏览器打开 sciverse.space/tokens → token 存 `~/.sciverse/credentials.json`(0600)；优先层级：显式参数 > `SCIVERSE_API_TOKEN` env > 凭据文件
- **框架接入**：`OPENAI_TOOLS` / `ANTHROPIC_TOOLS` 常量直接用于 tool-calling；支持 MCP Server / CLI / Python / TS
- **CLI**：`sciverse search`、`sciverse semantic-search`、`sciverse content`、`sciverse catalog`、`sciverse resource`，输出 JSON 可 pipe jq
- **证据闭环链路**（官方 15 cookbooks）：问题提出 → 结构化筛选 → 语义检索 → 原文回读 → 图表获取 → 证据打包 → LLM 生成 → 引用回链
- **资源**：https://pypi.org/project/sciverse/ | https://github.com/opendatalab/Sciverse-Agent-Tools

### LangGraph 多智能体工作流（2026）
- **结果**：LangGraph = 有状态图编排框架，提供 typed state、节点/边、条件路由、checkpoint、interrupt/resume
- **核心模式**：
  - `StateGraph(AgentState)` + `add_node` + `add_edge` + `add_conditional_edges` + `set_entry_point`
  - 状态用 `TypedDict` + `Annotated[list, add_messages]` 累积消息
  - 条件边实现循环/自纠错：如 quality_score < 7 → 回到 researcher 重搜
  - HITL：`interrupt` + checkpoint 实现关键节点人工审核
- **科研 Agent 实践**：searcher → analyst（判断信息是否充足）→ writer 三角色循环图；quality router 决定 loop back 或 finalize
- **适用判断**：复杂多步/长流程/需审计 → LangGraph；简单 ReAct 用普通 SDK 循环即可
- **资源**：arXiv:2607.19297 | https://blog.csdn.net/2401_84813926/article/details/159423917

### 科研 RAG 证据链设计
- **结果**：科研 RAG 核心是「先证据后生成」+「可审计检索记录」
- **Evidence Store**：至少保存 query、接口返回时间、doc_id、DOI、证据片段、最终回答
- **Prompt 纪律**：只把证据片段+来源放入 prompt；证据不足时返回「不足以回答」而非编造；答案标注引用编号 [1][2]
- **API Key 纪律**：环境变量，禁止入库；content 按 doc_id 分段读取，不整篇塞入模型

## 重要发现

### 发现 1：Sciverse 是证据链天然载体
- **内容**：semantic_search 返回 doc_id+score+snippet，read_content 可回读原文，get_resource 取图表
- **影响**：检索→核验→资源全链路可审计，直接满足赛题证据链红线
- **建议**：检索 Agent 每次调用即写证据链，不事后补录

### 发现 2：融合深度是创新性得分关键
- **内容**：赛题明确「搜索方法与 LLM 深度融合而非仅生成搜索代码」
- **影响**：路线 A 须设计 LLM 参与生成/评估/剪枝三角色，且做消融实验证明价值
- **建议**：复赛报告须有「有/无 LLM 引导」对比数据

### 发现 3：初赛写作优先级高于代码
- **内容**：初赛不强制代码，核心是 4 页方案说明文档
- **影响**：时间分配应向选题与方案倾斜，代码以 MVP 验证为主
- **建议**：8.12 前完成 MVP 演示素材，8.13-8.16 全力撰写方案

## 资源链接

- Sciverse 文档：https://sciverse.opendatalab.com/docs
- Sciverse SDK：https://pypi.org/project/sciverse/
- Sciverse-Agent-Tools：https://github.com/opendatalab/Sciverse-Agent-Tools
- Sci-Base：https://huggingface.co/datasets/opendatalab/Sci-Base
- MinerU：https://github.com/opendatalab/MinerU
- Materials Project：https://materialsproject.org
- LangGraph 指南：arXiv:2607.19297
- 科研 RAG Demo：https://segmentfault.com/a/1190000047832013

---
title: "分项计划·模块1 文献检索 Agent · 任务规划"
type: "plan"
category: "subplan"
tags: [检索Agent, Sciverse, task_plan, 证据链]
created: "2026-08-04"
updated: "2026-08-04"
status: "active"
version: "1.0"
---

# 模块1 文献检索 Agent · 任务规划（task_plan）

## 任务目标

构建文献检索 Agent：根据研究问题自主检索并筛选文献，输出带证据链的候选文献清单，为抽取 Agent 提供输入。

## 约束条件

- 使用 Sciverse SDK（`AgentToolsClient`），Key 走环境变量 `SCIVERSE_API_KEY`
- 每次调用记录证据链（查询词、时间戳、doc_id、DOI、score）
- 遵循 `.trae/rules/00-project-rules.md`（代码规范、证据链结构）
- 接口以 Sciverse v0.11.0 为准（tools: search_papers/semantic_search/read_content/list_catalog/get_resource/meta-paper-relations）

## 阶段划分

### 阶段 1：环境与认证
- [ ] `pip install sciverse`
- [ ] `sciverse auth login`（浏览器取 token）
- [ ] `sciverse catalog --samples` 确认可用字段

### 阶段 2：双通道检索实现
- [ ] `semantic_search(query, top_k, mode)`：语义检索找证据片段
- [ ] `search_papers(query, author, year_from, journal, subject)`：结构化筛选
- [ ] 检索结果 → `read_content(doc_id)` 原文回读核验
- [ ] `get_resource` 图表资源（figure-aware）

### 阶段 3：问题拆解与筛选逻辑
- [ ] 研究问题拆解为可检索子问题
- [ ] 相关度打分与去重（score + 标题相似度）
- [ ] 按年份/期刊/引用数排序筛选

### 阶段 4：证据链落库
- [ ] 实现 EvidenceItem/EvidenceChain 数据结构
- [ ] 检索记录写 JSON 审计日志
- [ ] 输出候选文献清单（doc_id + DOI + title + evidence）

## 验收标准

- [ ] CLI 检索跑通（`sciverse semantic-search` 示例）
- [ ] SDK 双通道检索实现并可调用
- [ ] 输出含证据链的候选清单 JSON
- [ ] 单测覆盖（mock 外部 API）

## 技术决策

### 决策 1：SDK vs MCP
- **选择**：Python SDK（`AgentToolsClient`）
- **理由**：异步客户端适合 Agent 运行时，支持五类工具直接调用；MCP 留待复赛 LangGraph 集成

### 决策 2：检索模式
- **选择**：`mode="balanced"`（默认）
- **理由**：语义检索 fast/balanced/quality 三档中 balanced 速度与质量平衡

## 错误记录

### 错误 1：（待记录）
- **时间**：-
- **原因**：-
- **解决方案**：-

## 关联文档

- 技能：`.trae/skills/literature-data-sources/SKILL.md`
- 知识：`.trae/rules/02-literature-data-sources.md`
- 证据链结构：`.trae/rules/00-project-rules.md` 第 4 节

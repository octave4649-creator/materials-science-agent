---
title: "分项计划·模块2 知识抽取 Agent · 任务规划"
type: "plan"
category: "subplan"
tags: [抽取Agent, task_plan, MinerU, LLM, schema]
created: "2026-08-04"
updated: "2026-08-04"
status: "active"
version: "1.0"
---

# 模块2 知识抽取 Agent · 任务规划（task_plan）

## 任务目标

从检索 Agent 输出的文献中提取结构化材料知识（成分、结构、性能、模拟方法、合成条件），落库为知识库，供 Gap 识别与路线 A 使用。

## 约束条件

- MinerU 预处理 PDF → Markdown（表格转 HTML、公式转 LaTeX）
- LLM 输出必须符合 JSON Schema，回查原文防幻觉
- 知识库存储：JSON/Parquet + 向量化索引
- 遵循 `.trae/rules/04-literature-agent.md` schema 规范

## 阶段划分

### 阶段 1：MinerU 解析管线
- [ ] 安装 `pip install "mineru[all]"` + 下载模型
- [ ] pipeline 后端解析 3-5 篇材料 PDF → Markdown
- [ ] 表格合并/公式转换验证

### 阶段 2：抽取 Schema 与 Prompt
- [ ] 定义材料知识四元组 schema（JSON）
- [ ] 设计 LLM 抽取 Prompt（schema 约束 + 原文上下文）
- [ ] 实现多轮校验（抽取结果回查原文）

### 阶段 3：抽取实现与归一化
- [ ] 实现 extraction_agent 核心逻辑
- [ ] 材料别名/同构异名归一化去重
- [ ] 多篇文献同体系合并

### 阶段 4：知识库落库
- [ ] 抽取记录存储（JSON/Parquet）
- [ ] 向量化索引（chroma + bge-m3）
- [ ] 元数据关联（证据链接、source DOI）

## 验收标准

- [ ] 单篇文献能抽取完整四元组
- [ ] 字段级 F1 ≥ 0.85（人工标注小集）
- [ ] 抽取记录带证据链接可溯源
- [ ] 知识库落库可查询

## 技术决策

### 决策 1：解析后端
- **选择**：pipeline 后端起步
- **理由**：纯 CPU 可运行、确定性输出、速度快；复杂版式再切 vlm/hybrid

### 决策 2：抽取 Schema 结构
- **选择**：material/properties/methods/synthesis/source 五段式
- **理由**：与赛题知识抽取要求（成分/结构/性能/方法/条件）一一对应

## 错误记录

### 错误 1：（待记录）

## 关联文档

- 技能：`.trae/skills/literature-agent/SKILL.md`
- 知识：`.trae/rules/04-literature-agent.md` 第 3 节
- MinerU：`.trae/rules/02-literature-data-sources.md` 第 3 节

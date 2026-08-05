---
title: "分项计划·模块4 调研报告生成 Agent · 进度日志"
type: "plan"
category: "subplan"
tags: [报告生成, progress]
created: "2026-08-04"
updated: "2026-08-05"
status: "active"
version: "1.1"
---

# 模块4 调研报告生成 Agent · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：2026-08-05
- **完成状态**：阶段 1-4 完成（验证章节对接模块 6 + 初赛 4 页方案文档完成）

## 阶段进度

### 阶段 1：报告模板与 Schema
- [x] 章节结构定义（9 章节：abstract/scope/method/extraction/gaps/review/conclusion/references/appendix，对齐 04 规范 5.1 模板）
- [x] 报告数据 Schema（ReportSection/ReportMeta/ReportDocument，pydantic，含 input_hashes 版本快照 + self_check 自检）

### 阶段 2：内容组装
- [x] 研究现状综述聚合（section_review 按期刊分组，大小写归一化合并）
- [x] Gap 章节生成（四列表格 + 统计 + 可操作性）
- [x] 引用编号映射（build_references 三级去重键 + doc_id→[n] 编号，Gap 证据回映射）

### 阶段 3：可读性优化
- [x] 摘要自动生成（规则式兜底 + LLM 润色优先，失败降级不阻塞）
- [ ] 图表自动生成（待定：报告为文本/表格驱动，图表走可视化模块）
- [x] LLM 润色管线（仅摘要润色，禁止整篇生成——防编造数值/文献，findings 决策 2）

### 阶段 4：输出与版本管理
- [x] MD/HTML 导出（render.py 受控 Markdown 子集，无第三方依赖）
- [x] 版本快照（时间戳文件名 + 输入 sha256 + meta.json）
- [x] 初赛 4 页裁剪（2026-08-05 完成，产出 `docs/initial-round-proposal.md`）

### 阶段 5：验证章节对接（模块 6 产物入报告）
- [x] SECTION_ORDER 插入 validation 键（位置 6，「6. 数据库交叉验证」，conclusion 顺延为 7）
- [x] `section_validation()` 确定性汇总（扫描 validation_*.json：判定分布 Counter + 候选表 ≤20 行 + 判定口径说明，零编造）
- [x] ReportAgent 新增 `validation_dir` 参数（默认 None 占位，run_report.py 显式传 results/validation/）
- [x] 端到端：`run_report.py` 生成含验证章节报告（182 候选：已知 124 / 反例 10 / 新知 10 / 验证失败 38）

## 操作记录

### 2026-08-04 计划初始化
- **操作**：创建模块4三件套
- **结果**：任务规划完成
- **状态**：成功

### 2026-08-04 开发实施
- **操作**：实现 schemas/assembly/render/report_agent + run_report.py + 12 项单测
- **结果**：`python scripts/run_report.py` 端到端跑通，10 篇 + 5 知识条目 + 1 Gap → 9 章节报告，自检 6 项全 ✓
- **状态**：成功

### 2026-08-05 验证章节对接 + 初赛方案
- **操作**：报告对接模块 6 验证产物 + 撰写初赛方案说明
- **结果**：
  - `schemas.py` SECTION_ORDER 插入 validation 键（位置 6），SECTION_TITLES 对应「6. 数据库交叉验证」，conclusion 顺延为 7
  - `assembly.py` 新增 `section_validation()`（确定性汇总：判定分布 + 候选表 ≤20 行 + 判定口径，验证失败/反例如实呈现）
  - `report_agent.py` 新增 `validation_dir` 参数（默认 None 占位，保证测试隔离）；`run_report.py` 新增 `--validation-dir`（默认 results/validation/）
  - 新增 4 项单测：占位/空目录/有数据汇总/端到端验证章节（test_report_agent.py）
  - 端到端：`run_report.py` 生成报告 19 文献 + 5 知识 + 29 Gap + 182 候选验证，自检 6 项全 ✓（摘要走规则式兜底）
  - 初赛方案：`docs/initial-round-proposal.md`（问题真实性/AI 介入点/探索环境/发现信号/最小参照系 + 技术路线概述，≤4 页）
- **状态**：成功

### 2026-08-05 LLM 摘要润色真实验证（新 key 重跑）
- **操作**：注入用户级 `DEEPSEEK_API_KEY`（`[Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')`）重跑 `run_report.py`
- **结果**：
  - 根因确认：之前摘要走规则式兜底是终端会话 `DEEPSEEK_API_KEY` 仍是旧 key（`sk-2cb7...`）→ 401；用户级新 key（`sk-2a83...`）经 setx 写入后需新终端/重新注入才生效
  - 最小连通性验证：新 key 调 DeepSeek 成功（仅因 max_tokens=64 截断导致 JSON 解析失败，属预期）
  - 重跑成功：`report_20260804T215944.*` 三件套，**摘要来源 = LLM**（润色摘要已写入），6 项自检全 ✓，验证章节判定分布 已知 124 / 反例 10 / 新知 10 / 验证失败 38
- **状态**：成功

## 测试结果

### 已通过 ✅
- [x] `scripts/run_report.py` 端到端跑通（report_*.md/.html/.meta.json 三件套落盘）
- [x] pytest 12/12 模块 4 单测（引用去重/证据回映射/自检/渲染/落盘/LLM 降级）
- [x] ruff 零 error
- [x] LLM 降级路径真实验证（DeepSeek 401 → 规则摘要兜底，流水线不中断）
- [x] 验证章节 4 项单测（占位/空目录/有数据判定分布/端到端 validation_dir 传入）
- [x] 端到端报告含验证章节：182 候选判定分布 + 候选表 + 判定口径说明
- [x] LLM 摘要实际润色验证（新 key 重跑：摘要来源 = LLM，报告 `report_20260804T215944.md`）

### 待测项
- [ ] 全链路一键生成时长（四 Agent 串联，阶段 5 复赛）
- [ ] 证据回溯完整性（抽样 10 条结论人工核对）
- [ ] 可读性人工评分（初赛材料阶段）

## 错误日志

### 错误 1：self_check references_complete 计数错误
- **时间**：2026-08-04
- **类型**：代码
- **消息**：`content.count("\n[")` 计数恒为引用数 - 1，自检项恒 False（单测捕获）
- **解决方案**：改 `re.findall(r"^\[\d+\]", content, re.MULTILINE)` 统计行首编号

### 错误 2：_gap_statements 取错字段
- **时间**：2026-08-04
- **类型**：代码
- **消息**：`g['type']` KeyError（gaps.json 字段名是 `gap_type`）
- **解决方案**：改用 `g.get('gap_type', '未知')` 容错取值

## 下一步

1. 阶段 3 选题收敛时用四 Agent 流水线跑 2-3 个候选领域，对比报告 Gap 质量
2. 初赛材料阶段：实现报告 → 初赛 4 页方案文档裁剪（复用 report_*.md 内容）
3. 复赛前：补可视化图表（可选）、LangGraph 编排、证据链审计界面

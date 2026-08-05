---
title: "分项计划·模块2 知识抽取 Agent · 进度日志"
type: "plan"
category: "subplan"
tags: [抽取Agent, progress]
created: "2026-08-04"
updated: "2026-08-05"
status: "active"
version: "1.2"
---

# 模块2 知识抽取 Agent · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：2026-08-05
- **完成状态**：核心开发完成（阶段 1-4 主线完成；向量索引留待复赛）；**字段级 F1 评测链路完成（LLM vs 规则双路径 + schema null 容错重大 bug 修复）**

## 阶段进度

### 阶段 1：MinerU 解析管线
- [x] 安装 mineru（miniconda 3.13，版本 3.4.0；主环境 Python 3.14 无 wheel）
- [x] 解析验证（`mineru -p xxx.pdf -o out -b pipeline`，子进程封装可跑）
- [x] 表格/公式转换（CLI 默认开启 table/formula；管线封装 `--backend pipeline`）

### 阶段 2：抽取 Schema 与 Prompt
- [x] schema 定义（`src/extraction/schemas.py` 五段式 pydantic：material/properties/methods/synthesis/source）
- [x] Prompt 设计（`src/agent/extraction_agent.py` 中文硬性要求：严禁编造 + 原文回查）
- [x] 多轮校验（`_verify_against_source` 化学式归一化后回查原文）

### 阶段 3：抽取实现与归一化
- [x] 核心逻辑（`extractor.py` 规则式降级 + 化学式归一化 LaTeX/HTML → 纯文本）
- [x] 归一化去重（`normalize_formula` 作键；元素符号集合过滤单位误提取如 Wm）
- [x] 同体系合并（`merge_records` 属性/方法并集；`KnowledgeBase._merge_entry` 证据回链）

### 阶段 4：知识库落库
- [x] JSON 存储（`data/knowledge_base.json`，ensure_ascii=False + indent=2）
- [ ] 向量索引（复赛阶段接入，配合模块 3 Gap 识别语义检索）
- [x] 元数据关联（evidence_ids 回链证据链 doc_id）

### 阶段 5：字段级 F1 评测（2026-08-05 完成）
- [x] F1 计算器（`src/evaluation/f1.py`：六字段原子拆解 + 空-空跳过 + 无预测 precision=1.0 + macro 非空字段均值）
- [x] 评测脚本（`scripts/eval_extraction_f1.py`：LLM vs 规则双路径、gold/llm_reference/unavailable 三模式、gold 标注模板生成）
- [x] schema null 容错修复（`schemas.py` field_validator：structure/synthesis null→{}、properties/methods null→[]、method type 未知→OTHER）
- [ ] 人工 gold 标注后 `--gold` 重跑（最终 F1，模板 `data/eval/extraction_gold_template.json` 已生成）

## 操作记录

### 2026-08-04 计划初始化
- **操作**：创建模块2三件套
- **结果**：任务规划完成
- **状态**：成功

### 2026-08-04 核心开发
- **操作**：实现 schemas.py / common/llm.py / extractor.py / knowledge_base.py / mineru_pipeline.py / extraction_agent.py / run_extraction.py + 5 个测试文件
- **结果**：pytest 40/40 全绿、ruff 零 error
- **状态**：成功

### 2026-08-04 端到端验证
- **操作**：`python scripts/run_extraction.py` 复用模块 1 输出 `results/retrieval_20260804T152611.json`
- **结果**：10 篇输入 → 5 条记录落库（LLM 未配置走规则式降级）；核心体系 Ge0.93Ti0.01Bi0.06Te（zT=1.6）+ PbTe + Bi2Te3 + Ca5In2Sb6 + Bi0.5Sb1.5Te
- **状态**：成功

### 2026-08-04 MinerU 集成验证
- **操作**：`MINERU_PYTHON=C:\Users\Administrator\miniconda3\python.exe` 验证 `MineruParser.available()=True`，`parse_pdf` 跑通
- **结果**：mineru 3.4.0 CLI 语法为 `-p/-o/-b`（非文档的 `parse -i -o --format`）；`python -m mineru` 不可用（包无 `__main__`），需调用 Scripts\mineru.exe；真实解析赛题 PDF 成功（MD 35404 字符，表格转 HTML）；pipeline 模型约 1.1GB 已缓存于 `~/.cache/modelscope`（ModelScope 国内下载较快），二次解析免下载
- **状态**：成功

### 2026-08-05 字段级 F1 评测 + schema 容错修复
- **操作**：按整体计划阶段 5「量化评测」开发抽取评测链路，并修复评测暴露的重大 bug
- **结果**：
  - `src/evaluation/f1.py` + `tests/test_evaluation_f1.py`（10 项）：字段原子拆解与对齐语义（空-空跳过 / gold 有 pred 无→fn / 无预测且漏检 precision=1.0 / macro=非空字段均值 / 数值容差 5% / LaTeX 归一化 / 防除零）
  - `scripts/eval_extraction_f1.py`：双路径抽取（LLM 五段式 vs 规则降级）+ 三模式（gold / llm_reference / unavailable）+ 自动生成 gold 标注模板 `data/eval/extraction_gold_template.json`（10 条热电 chunk）；默认检索产物优先热电 query（避免选到电池领域）
  - **修复重大 bug**：LLM 按提示词「未提及字段填 null」→ pydantic 校验失败 → `_parse_llm_output` 返回 None → 整条记录静默丢弃（知识库仅剩规则式条目的深层原因）；`schemas.py` 增加 field_validator 容错（structure/synthesis null→{}、properties/methods null→[]、method type 未知→OTHER）+ `tests/test_extraction_schemas.py` 4 项回归
  - LLM 参考模式实跑（`results/eval/extraction_f1_20260805T065045.json`，LLM 失败 0/10）：formula F1=0.600、properties F1=0.222、composition/methods recall=0（规则不产出）、synthesis FP=4（字段错位）；micro F1=0.2667、macro F1=0.1644
  - pytest **139/139** 全绿、ruff 全量零 error
- **状态**：成功

## 测试结果

### 已通过 ✅
- [x] pytest 40/40（schema 往返 / 归一化 LaTeX-HTML / 规则式抽取 / 单位误提取过滤 / 同 formula 合并 / MinerU mock 成功失败 / LLM 降级 / 证据回查 / 知识库合并）
- [x] ruff check 零 error
- [x] 端到端抽取：10 篇 → 5 条知识库条目，证据 doc_id 回链
- [x] F1 计算器单测 10 项（2026-08-05：完全匹配 F1=1 / 规则缺字段 recall=0 precision=1 / 空-空跳过 / 数值容差 / 幻觉 fp / 防除零）
- [x] schema 容错单测 4 项（2026-08-05：structure/synthesis null / THEORETICAL→OTHER / properties null / formula 缺失仍非法）
- [x] LLM 参考模式抽取 F1 实跑（2026-08-05：`results/eval/extraction_f1_20260805T065045.json`，macro F1=0.1644 / formula F1=0.600，LLM 失败 0/10）

### 待测项
- [ ] 真实材料 PDF 全文解析（当前用赛题 PDF 验证管线，待模块 3 补材料语料）
- [ ] 人工 gold 标注（`data/eval/extraction_gold.json`）后 `--gold` 重跑字段级 F1（最终结果）
- [ ] 向量索引（复赛阶段）

## 错误日志

### 错误 1：pip install mineru 装到错误环境
- **时间**：2026-08-04
- **类型**：环境
- **消息**：pip 指向 miniconda，python 是 3.14；`pip install mineru` 报无匹配 wheel
- **解决方案**：确认主环境 3.14 无 mineru wheel（官方 ≤3.13）；miniconda 3.13 已有 mineru 3.4.0；`MineruParser` 用 `MINERU_PYTHON` 环境变量指定解释器，子进程调用

### 错误 2：规则式抽取 float('.') 崩溃
- **时间**：2026-08-04
- **类型**：代码
- **消息**：`ValueError: could not convert string to float: '.'`
- **解决方案**：`_ZT_RE`/`_GAP_RE` 捕获组 `[\d.]+` → `(\d+(?:\.\d+)?)`，保证至少一个数字

### 错误 3：`python -m mineru` 不可用
- **时间**：2026-08-04
- **类型**：CLI
- **消息**：`No module named mineru.__main__; 'mineru' is a package and cannot be directly executed`
- **解决方案**：`_mineru_exe()` 定位 python_bin 同环境 `Scripts\mineru.exe`，直接调用可执行文件

### 错误 4：mineru 3.4.0 CLI 语法与文档不一致
- **时间**：2026-08-04
- **类型**：CLI
- **消息**：`Missing option '-p' / '--path'`；文档写 `mineru parse -i paper.pdf -o out --format markdown`
- **解决方案**：实测 `mineru -p <path> -o <out> -b pipeline`；默认 backend 是 hybrid-engine（需 GPU），改用 pipeline（纯 CPU）

### 错误 5：pipeline 后端依赖缺失（shapely/ftfy/pyclipper + transformers 版本）
- **时间**：2026-08-04
- **类型**：环境
- **消息**：`No module named 'shapely'` → `No module named 'ftfy'` → `No module named 'pyclipper'`；transformers 5.14.1 报 `cannot import name 'find_pruneable_heads_and_indices'`
- **解决方案**：`pip install "mineru[pipeline]" "transformers<5"` 一次补齐（含 PyYAML）；transformers 降级 4.57.6 后 pipeline 可用

### 错误 6：schema 对 LLM null 输出严格校验 → 整条记录静默丢弃（重大）
- **时间**：2026-08-05
- **类型**：代码（schema 容错）
- **消息**：LLM 按提示词「未提及字段填 null」返回 `structure:null`/`synthesis:null`/`properties:null`/`methods:null`/`type:"THEORETICAL"` → pydantic 校验失败 → `_parse_llm_output` 返回 None → 整条抽取记录被丢弃（知识库仅剩规则式条目的深层原因；评测 F1 全 0 时暴露）
- **解决方案**：`schemas.py` 增加 field_validator 容错——`Material.structure` null→{}、`MethodEntry.type` 未知→OTHER、`ExtractionRecord.properties/methods` null→[]、`synthesis` null→{}；`formula` 缺失仍判非法（无合并键）
- **重试次数**：1（诊断链：F1 全 0 → llm_error 401 → key 修复 → LLM 有输出但 gold 全空 → 单测 `_parse_llm_output` 返回 None → 定位 schema 校验）

## 下一步

1. 配置 LLM API Key（LLM_API_KEY/OPENAI_API_KEY）跑 LLM 抽取，对比规则式质量
2. 模块 3 Gap 识别 Agent 直接消费 `data/knowledge_base.json`
3. 抽取质量评测集：人工标注 20-30 条，字段级 F1

---
title: "分项计划·模块3 Research Gap 识别 Agent · 进度日志"
type: "plan"
category: "subplan"
tags: [Gap识别, progress]
created: "2026-08-04"
updated: "2026-08-08"
status: "active"
version: "1.4"
---

# 模块3 Research Gap 识别 Agent · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：-
- **完成状态**：阶段 1-3 完成，阶段 4 部分完成（评测待做）

## 阶段进度

### 阶段 1：覆盖率分析引擎
- [x] 材料体系矩阵构建（`src/gap/coverage.py` coverage_matrix）
- [x] 空白格定位算法（find_blank_cells：研究充分但缺核心性能 → 未探索方向）

### 阶段 2：矛盾检测
- [x] 数值对比规则（同体系同性能多文献相对/绝对阈值双判定）
- [x] 冲突标记逻辑（detect_contradictions，多来源报道才比较）

### 阶段 3：LLM 推理与验证
- [x] Prompt 设计（连接发现 + 假设生成，schema 约束，证据必须来自知识库）
- [x] Sciverse 回查（semantic_search mode=fast，top5 按公式命中计数）
- [x] 新颖性判定（≥2 命中已知 / 1 命中部分已知 / 0 命中新知，启发式 + 人工复核）

### 阶段 4：Gap 输出与评测
- [x] Gap 清单结构（GapReport/GapCandidate schema，含 verification 字段）
- [x] 证据链关联（kb_entry_ids 回映射真实 doc_id，无证据 Gap 禁止输出）
- [x] 新颖性人工复核链路（2026-08-05：`scripts/review_gap_novelty.py` 三模式——默认生成清单 / `--verify` Sciverse 回查写回 / `--write-back` 人工批注回写；29 条全部回查成功，启发式建议「新知 20 / 已知 9」）
- [x] Gap 证据链回填（2026-08-08 九次深度开发：`src/evaluation/gap_evidence_backfill.py` 三通道匹配——kb_exact 公式精确 / kb_parent 分数掺杂公式整数母体 / retrieval chunk 子串；29 条 Gap 回填 17 条 / 新增 20 条证据 / 可追溯 1→18，审计复验不可追溯 0）
- [ ] 准确率评测（人工标注小集：29 条复核清单待人工批注 `confirmed_novelty` 后 `--write-back` 写回 gaps.json）

## 操作记录

### 2026-08-04 计划初始化
- **操作**：创建模块3三件套
- **结果**：任务规划完成
- **状态**：成功

### 2026-08-04 开发实施
- **操作**：实现覆盖率分析 + 矛盾检测 + Gap Agent + 运行脚本 + 单测
- **结果**：
  - `src/gap/coverage.py` / `src/gap/contradiction.py`（数据驱动 Gap）
  - `src/gap/schemas.py`（GapCandidate 增加 verification 验证说明字段）
  - `src/agent/gap_agent.py`（四步流水线：覆盖率→矛盾→LLM 推理→Sciverse 验证）
  - `scripts/run_gap.py` 端到端跑通：5 条知识库 → 5 条 Gap（LLM 4 + 覆盖率 1），新颖性回查 5/5
  - pytest 47/47 全绿、ruff 零 error
- **状态**：成功

### 2026-08-05 新颖性人工复核链路（评测补强）
- **操作**：`scripts/review_gap_novelty.py` 增加 `--verify` 模式（Sciverse 回查增强复核依据）+ 三模式完善
- **结果**：
  - 三模式闭环：默认生成复核清单 → `--verify` 逐条 Sciverse 回查（查询 = 主化学式 + Gap 陈述，top5 命中计数与 `gap_agent._verify_novelty` 一致）→ `--write-back` 读人工批注写回 gaps.json（novelty + novelty_confirmed + reviewed_at）
  - `_novelty_query()` 控 200 字符；`verify_gaps()` 异常降级留痕（SciverseError → verification 标「回查失败降级」），不中断整体
  - 实跑 `python scripts/review_gap_novelty.py --verify`：**29/29 回查成功**，verification 全部写回 gaps.json；启发式建议「新知 20 / 已知 9」vs 当前 novelty「部分已知 14 / 新知 15」——不一致条目即人工复核重点
  - 复核清单落盘 `results/eval/gap_novelty_review.json`（含 instruction / 证据计数 / 启发式建议 / 建议理由）
- **状态**：成功

### 2026-08-08 九次深度开发（Gap evidence_ids 回填 + 审计复验）
- **操作**：修复审计暴露的「29 条 Gap 仅 1 条可追溯」证据链缺口——实现三通道证据回填工具
- **结果**：
  - `src/evaluation/gap_evidence_backfill.py`：`normalize_formula` 化学式归一化 + `parse_integer_parent` 整数母体解析（AX 型 `Ge0.93Ti0.01Bi0.06Te`→`GeTe`、A2X3 型 `Bi0.5Sb1.5Te3`→`Sb2Te3`）+ `match_evidence_for_formula` 三通道匹配（kb_exact 公式精确 / kb_parent 知识库分数公式的整数母体 / retrieval 检索产物 chunk 子串）+ `backfill_gaps`（已有证据保序在前、并集去重、`evidence_backfill` 字段留痕来源）+ `render_report`
  - `scripts/backfill_gap_evidence.py` 薄 CLI（--gaps/--kb/--retrieval-dir/--out/--dry-run 预览）；`tests/test_gap_evidence_backfill.py` 14 项单测
  - **真实数据端到端**：29 条 Gap 回填 **17 条 / 新增 20 条证据**（kb_exact 17 + kb_parent 3）、n_unchanged=1、回填后仍 11 条无证据（SnTe/Mg3Sb2/ZrNiSn/Cu2Se/CoSb3 等非知识库母体，需补检索证据）；`results/eval/gap_evidence_backfill_20260808T082627.json` 留痕
  - **审计复验**：`evidence_report_20260808T082657.md` 显示 Gap 可追溯 **1/29 → 18/29**、无证据 11、不可追溯 0；`src/audit/evidence_report.py` 侧 `n_traceable` 字段透出
  - 实验报告同步：`docs/experiment-report.md` 证据链审计行更新（18/29 + 回填工具引用 + 复现命令 `python scripts/backfill_gap_evidence.py`）
  - 全量回归：pytest **356/356** 全绿、ruff 零 error
- **状态**：成功

## 测试结果

### 已通过 ✅
- [x] 覆盖率矩阵定位（find_blank_cells 输出带证据链 Gap）
- [x] 矛盾检测（多来源冲突标记，单来源不误报）
- [x] LLM 输出解析（kb_entry_ids → 真实 doc_id 映射，编造 formula/无证据 Gap 丢弃）
- [x] 新颖性回查（已知/部分已知/新知三态 + Sciverse 失败降级留痕）
- [x] 去重（公式 + 类型 + 陈述三键）
- [x] pytest 47/47 全绿（含新增 test_gap_agent 7 条）
- [x] `scripts/run_gap.py` 端到端（DeepSeek LLM 4 条 + coverage 1 条 + Sciverse 验证 5 条）
- [x] 新颖性复核链路 `--verify`（2026-08-05：29/29 回查成功，verification 写回 gaps.json + 清单落盘）
- [x] Gap 证据链回填（2026-08-08：`test_gap_evidence_backfill.py` 14 项全绿——kb_exact/kb_parent/retrieval/no_match/empty + 索引加载去重 + 回填保序去重 + source_dist + evidence_backfill 留痕）
- [x] 审计复验端到端（2026-08-08：`evidence_report_20260808T082657.md` 可追溯 1/29 → 18/29、不可追溯 0）
- [x] pytest **356/356** 全绿、ruff 零 error（2026-08-08 九次深度开发全量回归）

### 待测项
- [ ] Gap 新颖性人工评估（Sciverse 回查为启发式，最终需人工复核）
- [ ] 矛盾检测召回率（当前知识库单来源无冲突，需扩充语料）

## 错误日志

### 错误 1：占位统计逻辑残留
- **时间**：2026-08-04
- **类型**：代码
- **消息**：run() 中 `stats.n_contradiction = stats.n_coverage and 0` 等占位写法
- **解决方案**：改为先取列表再 `len()`；`_llm_gaps` 返回 (gaps, ok) 元组区分「失败」与「无产出」

### 错误 2：PowerShell 内联 JSON 转义失败
- **类型**：环境
- **消息**：`python -c "..."` 中 `{"ok": true}` 被 PowerShell 拆坏报 SyntaxError
- **解决方案**：改用 `scripts/verify_llm.py` 脚本文件验证（避免内联引号转义）

## 下一步

1. 扩充热电语料（更多文献/体系）后重跑 Gap 识别，验证矛盾检测召回
2. 构建 Gap 人工标注小集做准确率评测（t7）
3. 与模块 4 报告生成、模块 5 路线 A 联动（Gap 作为搜索种子输入）

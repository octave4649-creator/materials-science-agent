---
title: "分项计划·模块1 文献检索 Agent · 进度日志"
type: "plan"
category: "subplan"
tags: [检索Agent, progress]
created: "2026-08-04"
updated: "2026-08-04"
status: "active"
version: "1.1"
---

# 模块1 文献检索 Agent · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：-
- **完成状态**：模块 1 主体完成（检索→去重→证据链→单测全绿）

## 阶段进度

### 阶段 1：环境与认证 ✅
- [x] 安装 sciverse 0.11.0（`pip install sciverse`）
- [x] auth login（token 写入 `~/.sciverse/credentials.json`，权限 0600）
- [x] catalog 字段确认（doc_id / unique_id 语义澄清）

### 阶段 2：双通道检索 ✅
- [x] semantic_search（返回 hits：chunk/doc_id/page_no/score）
- [x] search_papers（返回 results：unique_id/doi/citation_count）
- [ ] read_content 核验（代码已封装，待抽取 Agent 联动时启用）
- [ ] get_resource（待多模态场景启用）

### 阶段 3：问题拆解与筛选 ✅
- [x] 子问题拆解（规则式：分号/句号拆分）
- [x] 打分去重（doc_id → unique_id → 归一化标题三级键）
- [x] 排序筛选（语义分优先，其次引用数）

### 阶段 4：证据链落库 ✅
- [x] 数据结构（EvidenceItem / EvidenceChain，JSON 序列化）
- [x] 审计日志（AuditLogger 追加式 JSONL）
- [x] 候选清单输出（results/retrieval_*.json，含论文清单 + 证据链）

## 操作记录

### 2026-08-04 计划初始化
- **操作**：创建模块1三件套
- **结果**：任务规划完成
- **状态**：成功

### 2026-08-04 开发实施
- **操作**：按整体计划阶段 1 + 模块 1 开发
- **结果**：
  - 搭建项目骨架：`src/{agent,retrieval,common}` + `tests/` + `scripts/`
  - 实现 `evidence.py`（证据链）、`sciverse_client.py`（缓存+错误收敛）、
    `retrieval_agent.py`（拆解/双通道/去重/证据打包）、`config.py`、`logging.py`
  - 演示脚本 `scripts/run_retrieval.py` 端到端跑通：命中 10 篇，证据链 10 条
  - 单测 12/12 通过，ruff 零 error
- **状态**：成功

## 测试结果

### 已通过 ✅
- [x] `sciverse semantic-search "thermoelectric..." --top-k 3 --mode fast`（CLI 通）
- [x] SDK `AgentToolsClient.semantic_search / search_papers`（运行时结构确认）
- [x] `python scripts/run_retrieval.py` 端到端（命中 10 篇，含 score/年份/证据片段）
- [x] pytest 12 项全绿（证据链往返 / 缓存去重 / 异常降级 / 标题归一化）
- [x] ruff check 零 error

### 待测项
- [ ] read_content 原文核验（与抽取 Agent 联动）
- [ ] get_resource 图表资源
- [ ] 检索质量评测（NDCG@K，需构建评测集，见 DEVELOPMENT-GUIDE 第 6 节）

## 错误日志

### 错误 1：scripts 直接运行报 ModuleNotFoundError
- **时间**：2026-08-04
- **原因**：`python scripts/xxx.py` 时项目根不在 sys.path
- **解决方案**：脚本顶部 `sys.path.insert(0, 项目根)`；pytest 用 `pythonpath=["."]`

### 错误 2：SDK 调用报「未配置 Sciverse token」
- **时间**：2026-08-04
- **原因**：`sciverse_token()` 只读环境变量，未读 `auth login` 保存的凭据文件
- **解决方案**：config.py 增加凭据文件兜底（环境变量 > credentials.json）

## 下一步

1. 模块 2 知识抽取 Agent（复用检索输出，MinerU + LLM schema）
2. 检索质量评测集构建（人工标注小集，算 NDCG@K）
3. 阶段 3 选题：用检索 Agent 跑 2-3 个候选领域对比

---
title: "分项计划·模块6 数据库交叉验证 · 进度日志"
type: "plan"
category: "subplan"
tags: [数据库验证, progress]
created: "2026-08-04"
updated: "2026-08-05"
status: "active"
version: "1.3"
---

# 模块6 数据库交叉验证 · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：2026-08-05
- **完成状态**：阶段 1（OQMD ✅ / MP ✅）、阶段 2 简化实现、阶段 3 ✅、阶段 4 ✅；批量验证 34 finding → 182 候选；验证章节已对接模块 4；验证失败项 A/B 位拆分重验 38→0；跨库分歧 MP 相图级核对消除；搜索-验证闭环回喂

## 阶段进度

### 阶段 1：数据库接入
- [x] MP API Key + mp-api 跑通（`mp_api_key` 用户级环境变量 + `python -m pip install mp-api pymatgen`，真实查询成功）（2026-08-05）
- [x] OQMD REST 跑通（免 Key，`https://oqmd.org/oqmdapi/formationenergy`，整数成分直查）
- [ ] NOMAD/AFLOW/JARVIS 可选接入（按验证需求，暂未接）

### 阶段 2：结构匹配与归一化
- [ ] pymatgen 结构解析（暂未引入，当前按 composition 归一化直查）
- [x] 成分/结构匹配规则（整数成分归一化直查 + 分数成分跳过防超时 + `_normalize` 字段映射）
- [ ] 单位与条件归一化（当前记录原始字段，标注来源）

### 阶段 3：性质对比与误差分析
- [x] 同属性同条件对比逻辑（PropertyCheck：stability/band_gap 对比，expected vs db_value + consistent）
- [x] 稳定性判定（hull≤0.1 eV/atom 且 delta_e<0 → 稳定）
- [x] 误差阈值配置（DFT 带隙低估 30-50% 注释说明，见 03-materials-databases.md）

### 阶段 4：新知判定与验证报告
- [x] 新知/已知/反例三类标记（+「验证失败」四类，分数掺杂不伪装结论）
- [x] 验证结果写回证据链（validation JSON 含 source_finding/gap_statement/evidence_ids/entries/source_url）
- [x] 验证报告生成（对接模块4）（2026-08-05：SECTION_ORDER 插入 validation 章节，`section_validation()` 汇总判定分布，`run_report.py` 输出含验证章节报告）

## 操作记录

### 2026-08-04 计划初始化
- **操作**：创建模块6三件套
- **结果**：任务规划完成
- **状态**：成功

### 2026-08-05 开发实施
- **操作**：按 task_plan 开发数据库交叉验证（OQMD 主 + MP 增强）
- **结果**：
  - `src/validation/schemas.py`：DBEntry（db/formula/delta_e/stability/band_gap/is_stable/source_url）+ PropertyCheck + VerificationResult（四类判定 verdict/to_dict）
  - `src/validation/oqmd_client.py`：免 Key REST 客户端（整数成分直查 + 分数成分跳过防超时 + 进程缓存 + best_entry/is_stable 判定）
  - `src/validation/mp_client.py`：`mp_available()`（有 MP_API_KEY 且 mp-api 可导入）→ query_summary 增强；缺失优雅降级返回 None（区别于命中 0 条）
  - `src/agent/validation_agent.py`：消费 findings → 四类判定（已知/新知/反例/验证失败）→ 落盘 + 审计日志
  - `scripts/run_validation.py`：端到端（`--findings/--limit/--no-mp`）
  - `tests/test_validation.py`：9 项（四类判定/整数成分 guard/OQMD 解析 mock/网络错误雨伞/Agent 全流程 mock/空目录）
  - 真实 OQMD 验证：GeTe 母体 hull=0.002 eV/atom 稳定 → 「已知」，掺杂成分 novel_dopant 标记；分数母体（Ge0.93Ti0.01Bi0.06Te）明确「验证失败」不伪装结论
  - `data/gaps.json` 补充纯母体 GeTe（基础母体，解锁可验证候选）
  - pytest 78/78 全绿（模块 6 新增 9 项，全 mock 无网络）、ruff 零 error
- **状态**：成功

### 2026-08-05 MP 增强路径启用
- **操作**：配置 `MP_API_KEY`（用户级 setx）+ 主环境安装 mp-api/pymatgen，重跑 run_validation.py
- **结果**：
  - 踩坑：`pip` 指向 miniconda3、`python` 指向 pythoncore-3.14，`pip install` 装错环境 → 改用 `python -m pip install mp-api pymatgen`（0.46.4 + 2026.5.4）
  - 真实 MP 查询成功：GeTe（mp-1080459 hull=0.028 / mp-1172873 / mp-1181264）、Bi2Te3（mp-34202 stable=True hull=0.0）、PbTe（mp-2517816 / mp-1079574）
  - 交叉验证产物 `validation_20260804T213340_1.json`：entries 同时含 OQMD + MP 双库条目
  - **跨库分歧发现**：GeTe 在 OQMD 稳定（hull=0.002）但 MP 中 mp-1080459 不稳定（hull=0.028）——两库竞争相集合/DFT 设置不同，是「数据库间分歧」留痕素材（负结果与分歧同样入库，见 03 规范 7.2）
- **状态**：成功

### 2026-08-05 批量验证 + 报告对接
- **操作**：扩充 gaps.json 至 29 条 → 批量搜索 29 finding → 批量验证 → 验证章节对接模块 4
- **结果**：
  - `scripts/expand_gaps.py`：策展 16 条（域内可证伪陈述 source=curated）+ LLM 推理 12 条（source=llm）+ 既有 1 条（真实证据链 source=coverage），去重后 **29 条**（新知 15 / 部分已知 14）
  - `run_search.py --no-llm --top-n 29 --generations 2 --pop-size 10`（offset 分批断点续跑）→ 29 个 finding
  - `run_validation.py` 批量验证：**34 个验证文件、182 个候选**，判定分布**已知 124 / 反例 10 / 新知 10 / 验证失败 38**，覆盖 14 个母体体系（GeTe/PbTe/Bi2Te3/Mg3Sb2/ZrNiSn/Cu2Se/CoSb3 等）
  - 模块 4 对接：`section_validation()` 汇总判定分布 + 候选表 + 判定口径；`run_report.py` 生成含「6. 数据库交叉验证」章节的报告
- **状态**：成功

### 2026-08-05 三次深度开发（验证失败重验 / 相图级核对 / 闭环回喂）
- **操作**：A/B 位拆分纯母体解析重验 38 个验证失败项；跨库分歧 MP 相图级核对；反例母体提取回喂搜索
- **结果**：
  - `src/validation/parent_parser.py`：`parse_integer_parent(formula)` A/B 位拆分——AX 型 `Ge0.93Ti0.01Bi0.06Te` → `GeTe`、A2X3 型 `Bi0.5Sb1.5Te3` → `Sb2Te3`；主阳离子 = 下标占比最大者；`_ANIONS` 白名单（Te/Se/S/As/P/Br/Cl/I/F/O/N）；解析失败返回 None 保持「验证失败」如实标注
  - `src/validation/schemas.py`：VerificationResult 新增 `parent_formula` 字段（由分数宿主解析出的整数母体）
  - `src/agent/validation_agent.py`：`_validate_candidate` 分数宿主路径改造——`_FRACTION_RE` 命中 → `parse_integer_parent` → 成功用整数母体调 OQMD/MP 重验（reason 注明「按 A/B 位拆分解析整数母体后重验」），失败仍「验证失败」如实
  - `scripts/rerun_failed_validation.py`：只重验「验证失败」项（38 个），输出对齐验证产物结构（`validation_<ts>_rerun_{i}.json`，VerificationOracle 直接读取）+ 分布对比汇总（`failed_rerun_summary_<ts>.json`）→ **38 验证失败全部重验为「已知」（GeTe/Sb2Te3 在库稳定），失败 38→0，parsed_ok 38/38**
  - `src/search/verification_oracle.py`：host 表额外索引 `parent_formula`，真值表 182→**220 条**（formula 判定：已知 62 / 反例 10 / 新知 10；host 判定：已知 10 / 反例 2 / 新知 2）
  - `src/validation/feedback.py`：`extract_negative_hosts()` 提取反例母体（SiGe/Cu2Se → 搜索剪枝黑名单）+ `extract_disputes()` 提取跨库分歧（仅 entries 同时覆盖 OQMD+MP 且判定冲突）
  - `scripts/check_mp_phase_diagram.py`：MP 相图级核对——`get_entries_in_chemsys` + `pymatgen.analysis.phase_diagram.PhaseDiagram` → hull/分解产物，输出 `mp_phase_check_<ts>.json`；**GeTe 相图级 hull=0.0 稳定，跨库分歧（OQMD 稳定 vs MP 条目不稳定）归因「条目级亚稳相 vs 相图级判定」粒度差异，分歧消除**
  - `tests/test_validation.py` 新增解析器 4 项 + 重验 1 项；`tests/test_feedback.py` 3 项；pytest **115/115** 全绿、ruff 全量零 error
- **状态**：成功

## 测试结果

### 已通过 ✅
- [x] 真实 OQMD 验证：GeTe 母体稳定 → 「已知」+ novel_dopant；分数成分「验证失败」明确标注
- [x] 真实 MP 验证：GeTe/Bi2Te3/PbTe 三母体查询成功（material_id/hull/band_gap/is_stable 全字段）
- [x] 双库交叉验证产物：entries 同时含 OQMD + MP 条目，跨库分歧留痕
- [x] 三类判定 + 验证失败四类判定单测全绿（全 mock，CI 无网络依赖）
- [x] pytest 78/78、ruff 零 error
- [x] `scripts/run_validation.py` 端到端落盘 `results/validation/validation_*.json`
- [x] 批量验证：34 文件 / 182 候选（已知 124 / 反例 10 / 新知 10 / 验证失败 38）
- [x] 验证章节对接模块 4：`section_validation()` 4 项单测 + 端到端报告含「6. 数据库交叉验证」
- [x] A/B 位拆分纯母体解析单测 4 项 + 重验单测 1 项（AX 型 Ge0.93Ti0.01Bi0.06Te→GeTe / A2X3 型 Bi0.5Sb1.5Te3→Sb2Te3，解析失败返回 None）
- [x] 重验端到端：`rerun_failed_validation.py` 38 验证失败全部重验为「已知」（失败 38→0，parsed_ok 38/38），oracle 真值表 182→220 条
- [x] MP 相图级核对：`check_mp_phase_diagram.py` GeTe 相图 hull=0.0 稳定，跨库分歧归因「条目级 vs 相图级」粒度差异，分歧消除
- [x] 搜索-验证闭环：`feedback.py` 反例母体提取（SiGe/Cu2Se）+ 跨库分歧提取单测 3 项
- [x] pytest 115/115 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-05 三轮深度开发回归）

### 待测项
- [ ] 3+ 数据库查询连通性（OQMD ✅ / MP ✅，NOMAD/AFLOW 未接）
- [x] 跨库分歧（OQMD 稳定 vs MP 不稳定）的相图级核对（2026-08-05 完成：GeTe 相图 hull=0.0 稳定，归因「条目级 vs 相图级」粒度差异，分歧消除）
- [x] 验证失败项优化（2026-08-05 完成：A/B 位拆分纯母体解析重验，38 验证失败全部转「已知」）

## 错误日志

### 错误 1：OQMD http 301 重定向
- **时间**：2026-08-05
- **类型**：网络
- **消息**：`http://oqmd.org/oqmdapi/formationenergy` 报 301 Moved Permanently
- **解决方案**：用 `https://oqmd.org` + httpx `follow_redirects=True`
- **重试次数**：1

### 错误 2：分数掺杂成分查询超时
- **时间**：2026-08-05
- **类型**：网络/性能
- **消息**：`Pb0.94Ti0.06Te` / `Ge0.96Ti0.04Te` 分数成分查询 OQMD 长时间无响应
- **解决方案**：`_FRACTION_RE` 检测含小数成分直接跳过（返回空，标记验证失败），仅整数成分（GeTe/Bi2Te3）直查；掺杂扩展用 novel_dopant 标记而非直查
- **重试次数**：2

### 错误 3：`run_validation.py` 打印 AuditLogger.name 属性不存在
- **时间**：2026-08-05
- **类型**：代码
- **消息**：`AttributeError: 'AuditLogger' object has no attribute 'name'`
- **解决方案**：改用 `.agent` 属性
- **重试次数**：1

### 错误 4：pip 与 python 指向不同环境，mp-api 装错环境
- **时间**：2026-08-05
- **类型**：环境
- **消息**：`pip install mp-api` 报告 Successfully installed，但 `python -c "import mp_api"` 报 ModuleNotFoundError；`mp_available()` 恒 False
- **解决方案**：核对 `python -c "import sys; print(sys.executable)"`（pythoncore-3.14）与 `(Get-Command pip).Source`（miniconda3）→ 统一用 `python -m pip install mp-api pymatgen`
- **重试次数**：1

## 下一步

1. ~~验证失败项优化~~（已完成：A/B 位拆分重验 38→0，见操作记录三次深度开发）
2. ~~跨库分歧相图级核对~~（已完成：GeTe 分歧消除，归因「条目级 vs 相图级」粒度差异）
3. ~~按验证判定迭代搜索~~（首轮闭环完成：反例母体 SiGe/Cu2Se 回喂 GA 剪枝器端到端生效）
4. oracle 真值表扩面：纳入 OQMD 全库查询与更多母体体系（配合模块 5 消融重跑，提升 LLM 融合增益验证）
5. 按需接入 NOMAD/AFLOW（原始数据/晶体对称性验证）

## 关联文档

- 知识：`.trae/rules/03-materials-databases.md`
- 上游：模块 5 路线 A findings
- 下游：模块 4 报告生成（验证章节）

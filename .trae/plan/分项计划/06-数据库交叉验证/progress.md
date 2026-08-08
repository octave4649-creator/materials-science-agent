---
title: "分项计划·模块6 数据库交叉验证 · 进度日志"
type: "plan"
category: "subplan"
tags: [数据库验证, progress]
created: "2026-08-04"
updated: "2026-08-08"
status: "active"
version: "1.8"
---

# 模块6 数据库交叉验证 · 进度日志（progress）

## 会话信息

- **开始时间**：2026-08-04
- **结束时间**：2026-08-08
- **完成状态**：阶段 1（OQMD ✅ / MP ✅）、阶段 2 简化实现、阶段 3 ✅、阶段 4 ✅；批量验证 34 finding → 182 候选；验证章节已对接模块 4；验证失败项 A/B 位拆分重验 38→0；跨库分歧 MP 相图级核对消除；搜索-验证闭环回喂；**OQMD 全库扩面 oracle 真值自动纳入（12/12 母体全覆盖，2026-08-08）**；**共识候选验证闭环（12 个多算法共识候选 → 已知 9 / 反例 3，对照表产出，2026-08-08 十二次深度开发）**；**共识反例 MP 相图级双库核验（Cu2Se hull=0.0826 / SiGe hull=0.0162 相图级稳定，条目级 vs 相图级分歧归因消除，2026-08-08 十三次深度开发）**；**MP 在线双库核验扩展（7 共识母体相图级全稳定 + 双 thermo 交叉复核固化 mp_phase.py（Mg3Sb2/Sb2Te3/ZrNiSn 默认 R2SCAN hull 异常 → GGA_GGA+U legacy 0.0）+ 8 项单测，2026-08-08 十五次深度开发）**；**OQMD 定时重跑扩面（12 母体池全查已知 10 / 反例 2，oracle 真值自动纳入，2026-08-08 十五次深度开发）**；**NOMAD/AFLOW 可选接入完成（模块 6 阶段 1 未勾选项落地——nomad_client.py OPTIMADE 元素级 filter + HTML 拦截识别 / aflow_client.py AFLUX species matchbook + 显式字段请求 + spacegroup 映射 / run_extra_db_check.py CLI 12 母体聚合实跑 12/12 present，2026-08-08 十六次深度开发）**

## 阶段进度

### 阶段 1：数据库接入
- [x] MP API Key + mp-api 跑通（`mp_api_key` 用户级环境变量 + `python -m pip install mp-api pymatgen`，真实查询成功）（2026-08-05）
- [x] OQMD REST 跑通（免 Key，`https://oqmd.org/oqmdapi/formationenergy`，整数成分直查）
- [x] NOMAD/AFLOW 可选接入（2026-08-08 十六次深度开发：`nomad_client.py` OPTIMADE 元素级 filter + HTML 拦截识别降级留痕；`aflow_client.py` AFLUX species matchbook + 显式字段请求 `enthalpy_formation_atom,Egap` + `spacegroup_relax→spacegroup` 映射；`run_extra_db_check.py` 12 母体聚合实跑 12/12 present）

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
- [x] OQMD 全库验证扩面 + oracle 真值自动纳入（2026-08-08 十一次深度开发：`scripts/expand_oracle_truth.py` 聚合母体池 → OQMD 批量直查 → `oracle_truth_*.json` 落盘 → `run_ablation.py` 自动经 `VerificationOracle.load_oracle_truth` 纳入评分；**12/12 母体全覆盖**）
- [x] 共识候选验证闭环（2026-08-08 十二次深度开发：`src/validation/consensus_verify.py` + `verify_consensus.py` CLI + 19 单测；`consensus_verify_20260808T105523.{json/md/html}` 对照表，**12 个多算法共识候选 → 已知 9 / 反例 3**）
- [x] 共识候选 MP 在线双库核验扩展（2026-08-08 十五次深度开发：7 共识母体相图级全稳定 + `src/validation/mp_phase.py` 双 thermo 交叉复核固化（hull>0.5 触发 GGA_GGA+U legacy 复核 + thermo_discrepancy 触发即留痕）+ 8 项单测，`mp_phase_check_20260808T133350.json`——共识候选可信性论证扩展）
- [x] OQMD 定时重跑扩面（2026-08-08 十五次深度开发：OQMD 服务恢复后 12 母体池全查**已知 10 / 反例 2**，`oracle_truth_20260808T132948.json`；扩池后新 dopant 对应母体由聚合逻辑自动纳入，免改代码）

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

### 2026-08-08 十一次深度开发（OQMD 全库验证扩面 + oracle 真值自动纳入）
- **操作**：承接十次深度开发剩余项——OQMD 全库验证扩面，oracle 真值自动纳入评分
- **结果**：
  - `scripts/expand_oracle_truth.py`：`_integer_formula` 变量式文本 → 可直查整数成分（含名义母体归一化）；`collect_host_pool` 聚合母体池（gaps[].formulas + known_facts[].host + findings top_candidates[].host 去重）；`expand_oracle` 批量 OQMD 直查 → 判定（已知/反例/验证失败）落盘 `results/oracle/oracle_truth_<ts>.json`（结构与 validation 产物对齐，VerificationOracle.load_oracle_truth 直接读取）
  - `src/search/verification_oracle.py` 新增 `load_oracle_truth(oracle_dir)`：verdict → host_stable 映射（已知=True / 反例=False），formula 表 + host 表双索引 + VERDICT_PRIORITY 覆盖，与 validation 的 entries 推断逻辑等价
  - `src/validation/oqmd_client.py` 重试机制加固：MAX_RETRIES=3 + RETRY_BASE_DELAY=2.0 指数退避（服务端 5xx/超时自动重试，4xx 直接抛 OQMDError）——**OQMD 服务间歇性 502 下 3 轮复跑 4/12 → 11/12 → 12/12 全覆盖**
  - 最终 oracle 真值表 `oracle_truth_20260808T102223.json`：**12 母体全部判定**（已知 GeTe/PbTe/SnTe/Mg3Sb2/ZrNiSn/CoSb3/AgSbTe2/Ca5In2Sb6/Sb2Te3 等 10 + 反例 Cu2Se/SiGe 2）；失败/不完整产物 3 个归档 `results/oracle/archive_20260808_failed/` 防粉尘污染
  - 消融重跑量化扩面价值：`run_ablation.py` 自动加载 validation（220 条）+ oracle 真值（+12 条母体直查）→ **full 0.833 / rule 0.933 / llm 0.833**
  - pytest **412/412** 全绿（新增 OQMD 重试机制等 13 项）、ruff 全量（src/tests/scripts）零 error
- **状态**：成功

### 2026-08-08 十二次深度开发（共识候选验证闭环）
- **操作**：承接十一次深度开发产出——12 个多算法共识候选批量送 OQMD/MP 交叉验证，产出「共识候选 → 数据库判定」对照表（直接支撑路线 A「可信性与新颖性」评分）
- **结果**：
  - `src/validation/consensus_verify.py`：`split_candidate`（`_CAND_RE` 正则 host-dopant+浓度）/ `resolve_parent`（三形态分流：变量式→parse_variable_parent / 分数式末尾阴离子→parse_integer_parent / 末尾非阴离子合金式→去数字下标）/ `parse_ensemble_md` / `build_truth_map`（oracle + validation 按 VERDICT_PRIORITY 覆盖）/ `verify_one`（真值缓存优先 → online 回退 OQMD+MP）/ `verify_consensus` / `summarize` / `render_markdown` / `render_html`；修复 3 缺陷（import html 缺失 / return 残留 / render_html 截断）
  - `scripts/verify_consensus.py` CLI（`--ensemble/--truth/--min-votes/--out/--online/--mp`）→ **`consensus_verify_20260808T105523.{json/md/html}`：12 共识候选 → 已知 9 / 反例 3（Cu2Se-Te5%、Si0.8Ge0.2-P2%×2），known=0.75/counter=0.25/novel=0**
  - 11 个候选解析实测正确（Mg3Sb2→Mg3Sb2、Bi0.5Sb1.5Te3→Sb2Te3、Cu2Se→Cu2Se、ZrNiSn→ZrNiSn、CoSb3-Yb0.2Ba0.10%→CoSb3、Si0.8Ge0.2→SiGe）
  - 判定分歧留作路线 A 讨论点：Cu2Se/SiGe 为「DFT 亚稳相 vs 实验应用」分歧（oracle 反例 hull=0.125/0.512）
  - `tests/test_consensus_verify.py` 19 项单测全绿；pytest **440/440** 全绿、ruff 全量零 error
- **状态**：成功

### 2026-08-08 十三次深度开发（共识反例 MP 相图级双库核验）
- **操作**：承接十二次深度开发遗留分歧——Cu2Se/SiGe（oracle 判反例）用 `check_mp_phase_diagram.py` 相图级复核「条目级亚稳 vs 相图级」，对齐 GeTe 先例消除分歧，补强路线 A 可信性论证
- **结果**：
  - `scripts/check_mp_phase_diagram.py` 改造：新增 `_chemsys_for_formula(formula)`（`re.compile(r"[A-Z][a-z]?")` 提取元素 → `sorted(set(...))` 去重排序 → 连字符拼接，Cu2Se→"Cu-Se"、SiGe→"Ge-Si"，**MP 要求元素按字母序**）+ `--formulas "Cu2Se,SiGe"` 显式公式路径（推导 chemsys → 相图级核对）+ `stable = bool(hull < 0.1)` 显式转 Python bool（pymatgen 返回 np 标量，修复 json.dumps 序列化崩溃）+ note 字段动态化（`f"相图级核对：{formula} 在 MP 相图中"` 去除 GeTe 硬编码）
  - 实跑 `results/validation/mp_phase_check_20260808T111941.json`：**Cu2Se hull=0.0826 稳定（分解 Cu3Se2 0.833 mol + Cu 0.167 mol，n_entries=46）、SiGe hull=0.0162 稳定（分解 Ge 0.5 mol + Si 0.5 mol，n_entries=66）**——OQMD 条目级判反例（hull=0.125/0.512）vs MP 相图级稳定，归因「条目级 vs 相图级」粒度差异 +「DFT 亚稳 ≠ 实验不可用」（两者均为热电常用材料），与 GeTe 先例（经验 45）一致，**跨库分歧消除**
  - 结论写入 JSON：构效关系判定需结合 DFT 与实验双重证据，分歧本身作为「数据库间分歧」科学素材写入报告（03 规范 7.2 负结果同入库）
  - 质量门禁：pytest **440/440** 全绿、ruff 全量（src/tests/scripts）零 error（check_mp_phase_diagram.py 已 format 规范化）
- **状态**：成功

### 2026-08-08 十五次深度开发（MP 在线双库核验扩展 / OQMD 定时重跑扩面）
- **操作**：承接十四次深度开发下一步候选②③——① MP 在线双库核验扩展：将 Cu2Se/SiGe 相图级核验（经验 117 流程）扩展到其余共识候选；② OQMD 服务稳定后定时重跑扩面（扩池后新 dopant 对应母体自动纳入 oracle 真值表）
- **结果**：
  - **t1 MP 双 thermo 交叉复核固化**：7 共识母体（Mg3Sb2/Sb2Te3/ZrNiSn/GeTe/CoSb3/Cu2Se/SiGe）相图级全稳定；**发现并修复 MP 默认 thermo 数据层缺陷**——Mg3Sb2/Sb2Te3/ZrNiSn 默认 GGA_GGA+U_R2SCAN 联合 thermo 的 hull 异常巨大（9.7261/21.6121/13.4307 eV），换 GGA_GGA+U legacy thermo 复核 hull=0.0 稳定（MP 数据层缺陷非材料真实性质）；固化 `src/validation/mp_phase.py`（`_HULL_ABNORMAL_THRESHOLD=0.5` 触发 + `additional_criteria={"thermo_types": ["GGA_GGA+U"]}` 复核 + **触发即留痕** thermo_discrepancy=True/legacy_hull/note——判定一致也留痕，判定不同以 legacy 为准）+ `scripts/check_mp_phase_diagram.py` 薄封装复用
  - **t1 单测**：`tests/test_mp_phase.py` 重写 helper 化（`_make_fake_mp` 记录 additional_criteria 调用的伪 MPRester + `_make_switch_pd` 可切换 hull 的伪 PhaseDiagram + `_install` 模块级 monkeypatch），**8 项全绿**（chemsys 字母序去重 / 稳定不触发 / 异常触发 legacy 稳定 / 异常判定一致留痕 / 异常 legacy 稳定 / 异常 legacy 不稳定 / 无 formula 降级 / MP 未安装降级）；触发暴露「判定一致时丢弃 legacy 信息」缺陷 → 修复为触发即留痕
  - **t2 OQMD 定时重跑扩面**：OQMD 服务恢复（探测 200）→ `expand_oracle_truth.py` 12 母体池全查成功（**已知 10 / 反例 2**），`oracle_truth_20260808T132948.json`；扩池后新 dopant 对应母体（Mg3Sb2/CoSb3 等）由聚合逻辑自动纳入，`VerificationOracle.load` 免改代码
  - 产出：`mp_phase_check_20260808T133350.json`（7 母体核验 + 3 例双 thermo 复核留痕）
  - 质量门禁：pytest **450/450** 全绿（新增 mp_phase 8 项）、ruff 全量（src/tests/scripts）零 error（修复 mp_phase.py 1 处 E501）
- **状态**：成功

### 2026-08-08 十六次深度开发（NOMAD/AFLOW 可选接入 + 双库核验补强）
- **操作**：承接十五次深度开发下一步候选①——按需接入 NOMAD（原始数据 OPTIMADE）/ AFLOW（晶体对称性）交叉验证，补强路线 A「双库核验」论证；同步完成初赛 docx 排版审阅与 demo 素材就绪核验
- **结果**：
  - `src/validation/nomad_client.py`：免 Key OPTIMADE 客户端（`https://nomad-lab.eu/prod/optimade/v1/structures`，元素级 filter `elements HAS ALL "Ge", "Te"` + `elements ALL` 精确匹配 + 响应 meta.data_more / count 归一化 + 进程缓存 + MAX_RETRIES 指数退避）；**HTML 拦截识别**——本地网络被防火墙拦截时站点返回 200 + HTML（json 解析失败），识别为「网络不可用」抛 NOMADError 降级留痕，不误判「命中 0 条」
  - `src/validation/aflow_client.py`：免 Key AFLUX 客户端（`https://aflow.org/API/aflux/`，species matchbook 逐元素 `paging(1)` 交并集 + 进程缓存 + `best_entry` min 焓选择 + `_normalize` dict/list 兼容）；**两个实测修复**——① AFLUX 需在 URL 显式请求字段（`enthalpy_formation_atom,Egap,` 前缀），否则两字段返回 None；② `spacegroup_relax` 需映射到 `DBEntry.spacegroup`（schemas.py 已有字段但 `_normalize` 未读）
  - `src/validation/schemas.py`：`DBEntry` 新增 `spacegroup` 字段（str|None）；`DatabaseId` 从 `Literal["oqmd","mp"]` 扩展为 `Literal["oqmd","mp","nomad","aflow"]`
  - `scripts/run_extra_db_check.py`：12 母体聚合 + `check_one` 存在性判定——**present-first**（任一库命中 → present，即使另一库不可达；两库均可达且 0 命中 → absent；均未命中但至少一库不可达 → unreachable 留痕，不误判「新知」）+ `render_markdown` 对照表 + CLI
  - **12 母体实跑** `results/validation/extra_db_check_20260808T135909.json`：**12/12 全部 present**——AFLOW 全命中并附带空间群（GeTe=166 / PbTe=225 / Bi2Te3=166 / SnTe=225 / Mg3Sb2=206 / ZrNiSn=225 / Cu2Se=216 / CoSb3=194 / SiGe=216 / AgSbTe2=227 / Ca5In2Sb6=123 / Sb2Te3=166）；**SiGe AFLOW 焓 +0.025 eV/atom（正值）与 OQMD 反例判定互相印证**；NOMAD 本地网络被拦截识别为「未连通」留痕（未影响结论）
  - `tests/test_extra_clients.py`：**17 项单测全绿**（NOMAD 8 + AFLOW 8 + check_one 存在性判定 3）——HTML 拦截识别 / filter 构建 / AFLUX dict 响应 / spacegroup 映射 / present-first 语义锁定
  - **t3 初赛 docx 排版审阅**：3 处超长单元格（80/63/62 显示宽度 > 60）措辞压缩 → `md_to_docx.py` 重新生成 → `review_docx_layout.py` **0 问题「✅ 排版合格，可提交」**
  - **t4 demo 素材就绪核验**：`demo-script.md` 引用 9 个产物全部存在；`demo-panel.html` 完全自包含（内嵌 JSON + 内联 JS 无外部依赖）可直接录屏
  - OQMD 定时重跑常态化核验：`expand_oracle_truth.py` 聚合逻辑自动纳入新 dopant 对应母体，服务波动时重跑即自动扩面，无需代码改动
  - 质量门禁：pytest **467/467** 全绿（新增 17 项）、ruff 全量（src/tests/scripts）零 error（修复 nomad_client.py 1 处 E501）；临时诊断脚本已清理

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
- [x] OQMD 全库验证扩面（2026-08-08 十一次深度开发：`expand_oracle_truth.py` 母体池聚合 + 批量直查，3 轮复跑 4/12→11/12→**12/12** 全覆盖（已知 10 + 反例 2），`oracle_truth_20260808T102223.json`；OQMD 502 重试机制加固 MAX_RETRIES=3 指数退避；失败产物归档防污染；消融自动纳入 → full 0.833）
- [x] pytest **412/412** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-08 十一次深度开发全量回归）
- [x] 共识候选验证闭环（2026-08-08 十二次深度开发：`verify_consensus.py` 12 共识候选 → **已知 9 / 反例 3**（Cu2Se/SiGe 反例），对照表 `consensus_verify_20260808T105523.{json/md/html}`；`consensus_verify.py` 单测 19 项；Cu2Se/SiGe「DFT 亚稳 vs 实验应用」分歧留作路线 A 讨论点）
- [x] pytest **440/440** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-08 十二次深度开发全量回归）
- [x] 共识反例 MP 相图级双库核验（2026-08-08 十三次深度开发：Cu2Se hull=0.0826 / SiGe hull=0.0162 相图级稳定（分解产物齐全），OQMD 条目级 vs MP 相图级分歧归因「条目级 vs 相图级」粒度差异消除，`mp_phase_check_20260808T111941.json`；`--formulas` 显式公式路径 + `_chemsys_for_formula` 字母序推导 + np 标量序列化修复）
- [x] pytest **440/440** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-08 十三次深度开发全量回归）
- [x] MP 在线双库核验扩展（2026-08-08 十五次深度开发：7 共识母体相图级全稳定 + 双 thermo 交叉复核固化 `mp_phase.py`（hull>0.5 触发 GGA_GGA+U legacy 复核 + **触发即留痕** thermo_discrepancy/legacy_hull/note——判定一致也留痕），`mp_phase_check_20260808T133350.json`；`test_mp_phase.py` 8 项单测全绿）
- [x] OQMD 定时重跑扩面（2026-08-08 十五次深度开发：OQMD 恢复后 12 母体池全查**已知 10 / 反例 2**，`oracle_truth_20260808T132948.json`；扩池后母体自动纳入 oracle 真值表，免改代码）
- [x] pytest **450/450** 全绿、ruff 全量（src/tests/scripts）零 error（2026-08-08 十五次深度开发全量回归）
- [x] NOMAD/AFLOW 可选接入（2026-08-08 十六次深度开发：`nomad_client.py` OPTIMADE 元素级 filter + HTML 拦截识别降级留痕；`aflow_client.py` AFLUX species matchbook + 显式字段请求 `enthalpy_formation_atom,Egap`（AFLOW 实测修复）+ `spacegroup_relax→spacegroup` 映射；`schemas.py` DBEntry.spacegroup + DatabaseId 4 库；`run_extra_db_check.py` CLI + present-first 存在性判定单测 3 项锁定）
- [x] **12 母体实跑**（2026-08-08 十六次深度开发：`extra_db_check_20260808T135909.json` **12/12 全部 present**——AFLOW 全命中（空间群 GeTe=166/PbTe=225/Bi2Te3=166/SnTe=225/Mg3Sb2=206/ZrNiSn=225/Cu2Se=216/CoSb3=194/SiGe=216/AgSbTe2=227/Ca5In2Sb6=123/Sb2Te3=166），SiGe AFLOW 焓 +0.025 为正与 OQMD 反例判定互相印证；NOMAD 本地网络拦截识别「未连通」留痕不误判新知）
- [x] pytest **467/467** 全绿（新增 test_extra_clients 17 项）、ruff 全量（src/tests/scripts）零 error（2026-08-08 十六次深度开发全量回归）

### 待测项
- [x] 3+ 数据库查询连通性（OQMD ✅ / MP ✅ / AFLOW ✅ 12/12 命中 / NOMAD 本地网络拦截识别「未连通」留痕，代码路径就绪待网络恢复后实跑验证）
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
4. ~~oracle 真值表扩面~~（已完成，见十一次深度开发：`expand_oracle_truth.py` 母体池聚合 + OQMD 批量直查 **12/12 全覆盖**自动纳入消融评分，full 0.833）
5. ~~下一批深化候选：① 共识候选验证闭环~~（已完成，见十二次深度开发：`verify_consensus.py` 12 共识候选 → 已知 9 / 反例 3 对照表）② ~~OQMD 服务稳定后定时重跑扩面~~（已完成，见十五次深度开发：OQMD 恢复后 12 母体池全查已知 10 / 反例 2，`oracle_truth_20260808T132948.json`）
6. ~~共识候选反例 MP 相图级双库核验~~（已完成，见十三次深度开发：Cu2Se/SiGe 相图级稳定（hull=0.0826/0.0162），「条目级 vs 相图级」分歧归因消除，对齐 GeTe 先例）
7. ~~共识候选 MP 在线双库核验扩展~~（已完成，见十五次深度开发：7 共识母体相图级全稳定 + 双 thermo 交叉复核固化 `mp_phase.py`（Mg3Sb2/Sb2Te3/ZrNiSn 默认 R2SCAN hull 异常 → legacy 0.0）+ 8 项单测）
8. ~~按需接入 NOMAD/AFLOW~~（已完成，见十六次深度开发：`nomad_client.py` + `aflow_client.py` + `run_extra_db_check.py` 12 母体实跑 12/12 present，AFLOW 全命中附空间群；NOMAD 本地网络拦截留痕待恢复后补跑）
9. ~~OQMD 定时重跑扩面常态化~~（已完成，见十五次深度开发：服务波动时按 `expand_oracle_truth.py` 重跑即自动扩面，无代码改动）
10. 后续候选：① NOMAD 网络恢复后实跑验证（`run_extra_db_check.py` 双库都可达时 absent 判定路径尚未真实触发）；② AFLOW 空间群/焓值纳入构效关系解释（空间群 166/225/216 等与热电性能的关联论证）；③ 初赛 docx 人工审阅提交（8.16 截止，见整体计划人工行动项）

## 关联文档

- 知识：`.trae/rules/03-materials-databases.md`
- 上游：模块 5 路线 A findings
- 下游：模块 4 报告生成（验证章节）

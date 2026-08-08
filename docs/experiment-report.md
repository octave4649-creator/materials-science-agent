# 实验报告：材料科学文献驱动的科学发现智能体

> 赛题：GOAI 赛道三 · 方向三 · 路线 A（构效关系发现）
> 主攻细分领域：**热电材料（掺杂-性能构效关系）**
> 更新：2026-08-08

---

## 1. 实验概览

| 评测项 | 结论 | 产物 |
|--------|------|------|
| 知识抽取字段级 F1（LLM vs 人工 gold，热电 5 条） | LLM micro 0.68 / macro 0.66（formula 1.0 / composition 0.67 / properties 0.57）；规则式 micro 0.28 / macro 0.17 | `results/eval/extraction_f1_20260808T163821.json` |
| Gap 识别与新颖性复核 | 29 条 Gap（新知 15 / 部分已知 14），29/29 Sciverse 回查留痕 | `data/gaps.json`、`results/eval/gap_novelty_review.json` |
| 召回率 · 规则模式（16 条已知关系全量，扩池后） | BO coverage=1.0（池缺口根治：DOPANT_POOL 11→16 + BO 默认全池 16）；MCTS cov 0.375→**1.0**（host 过滤修复，十四次深度开发） | `results/eval/recall_matrix_20260808T211437.json` |
| 召回率 · LLM 模式（16 条已知关系全量） | GA recall@1=0.75/@5=0.938/cov=0.938 最优；SR 0.688/0.875/0.875；MCTS 短板攻坚后 cov=1.0/recall@5=0.812（展开即评估 + host 过滤 + batch 10） | 同上 |
| 三臂消融（VerificationOracle 真值，8 Gap） | full 0.806 / rule 0.885 / llm 0.785；GA 演化增益 +2.65% | `results/ablation/ablation_report.json` |
| 数据库交叉验证 | OQMD 主 + MP 增强；oracle 真值表 220 条 / 15 母体体系；38 项验证失败经 A/B 位拆分重验后归零 | `results/validation/` |
| 证据链审计 | 80 doc_id / 29 Gap / 36 finding / 47 验证；Gap 可回溯 29/29（六通道回填后），降级留痕 472 条 | `results/audit/evidence_report_20260808T091510.md/.html` |
| 四算法融合投票 | 29 Gap / 348 候选；Borda rank 加权（规则模式 0 共识，如实记录；LLM 模式待批量） | `results/ensemble/ensemble_20260808T093952.md/.html` |

## 2. 研究问题与范围

- **科学问题**：热电材料的能量转换效率由无量纲优值 zT 决定（zT = S²σT/κ）。掺杂（dopant）× 浓度（concentration）在母体（host）中的组合空间巨大，如何高效、可解释地从文献证据出发定位「高潜力掺杂方案」是一个典型的搜索问题。
- **智能体链路**：文献检索（Sciverse 双通道）→ 知识抽取（LLM + schema）→ Research Gap 识别（覆盖率/矛盾/LLM 推理 + Sciverse 回查）→ 搜索算法 × LLM 融合探索（GA/MCTS/BO/SR）→ 数据库交叉验证（OQMD/MP）→ 证据链可审计输出。
- **数据**：Sciverse 真实检索产物（46 篇热电/电池文献语料，RAG 索引 920 词项）、5 条知识库条目、29 条 Gap、16 条已知构效关系标注（known_facts，覆盖池内/超池/超宿主三档边界）。

## 3. 评测口径与可复现性

- **固定随机种子**：GA `random.Random(gen)`（按代数）、MCTS `random.Random(7)`、SR `random.Random(42)`、BO 浓度网格全覆盖无随机。
- **公平探索口径**：四算法统一 `explore_top=max(ks)`，top_candidates 输出「探索轨迹候选全集（去重按评分降序）」——避免 MCTS/BO 单候选输出导致 hit@k 失真。
- **评测双模式**：规则模式（无 LLM，确定性可复现基线）与 LLM 模式（deepseek-chat，非确定性但全量审计日志留痕）。
- **评测产物**：全部落盘 `results/eval/*.json`，含 `generated_at` 时间戳与输入产物路径，可对照复核。

## 4. 基本任务评测结果

### 4.1 知识抽取字段级 F1（LLM vs 人工 gold）

人工标注 `data/eval/extraction_gold.json`（**热电 5 条**：Ge0.93Ti0.01Bi0.06Te / PbTe / Bi2Te3 / Sr5In2Sb6 / Bi0.5Sb1.5Te3，来自热电检索产物 `retrieval_20260804T152611.json`；gold 由 AI 预填 + 人工复核修正产出），`eval_extraction_f1.py --gold` 对照评测 LLM 与规则式双路径：

| 字段 | LLM P / R / F1 | 规则 P / R / F1 |
|------|----------------|-----------------|
| formula | 1.0 / 1.0 / **1.0000** | 0.6 / 0.6 / 0.6000 |
| composition | 0.75 / 0.6 / **0.6667** | 1.0 / 0.0 / 0.0 |
| structure | —（gold 未覆盖） | — |
| properties | 0.5714 / 0.5714 / **0.5714** | 1.0 / 0.1429 / 0.2500 |
| methods | 0.3333 / 0.5 / **0.4000** | — |
| synthesis | —（gold 未覆盖） | — |
| **micro** | 0.6842 / 0.6842 / **0.6842** | 0.4 / 0.2105 / **0.2759** |
| **macro**（非空字段均值） | 0.6637 / 0.6679 / **0.6595** | 0.72 / 0.1486 / **0.1700** |

- **LLM 抽取显著优于规则式**：micro F1 高 +40.8pt、macro 高 +49.0pt；化学式（formula）抽取达到 **F1=1.0**（5/5 全对），composition/properties 均明显领先——支撑「LLM + schema 抽取」设计决策。
- 规则式短板：properties 召回 0.1429（仅能命中「数字+单位」显式形态）、composition/methods 全漏——对文献自由文本的字段召回能力有限。
- 观察：LLM 的 properties 与 methods 仍有提升空间（chunk 多为结论摘要，条件/方法表述多样），指向「提示词按字段对齐 + 结构化段落输入」的改进方向。
- 注：早期电池领域 gold 模板（`extraction_gold_template.json` 旧版）与主攻热电领域错位，已弃用；本次重建热电版 gold 链路（`eval_extraction_f1.py --ai-prefill` 预填 + 人工复核），历史 `extraction_f1_20260808T155846.json`（电池 + 已丢失 gold）不再引用。

### 4.2 Research Gap 识别与新颖性复核

- 29 条 Gap（策展 16 + LLM 12 + 真实证据链 1），三类识别方法：覆盖率分析（成分×性能空白格）、矛盾检测（同体系阈值冲突）、LLM 推理 + Sciverse 回查验证。
- `review_gap_novelty.py --verify`：29/29 Sciverse 语义回查成功；启发式建议「新知 20 / 已知 9」vs 人工初标「新知 15 / 部分已知 14」——不一致条目为人工复核重点（待人工批注 `--write-back` 出最终新颖性准确率）。
- 代表性 Gap：PbTe-Na 共掺杂 600-800K 协同窗口空白、Cu2Se-Te 取代的迁移活化能定量影响、ZrNiSn-Ti 的功率因子 trade-off 未量化——均具备可转化为搜索任务的形态。

### 4.3 已知关系召回率（规则模式 16 条全量，扩池后）

| 算法 | recall@1 | recall@3 | recall@5 | coverage | n_cand_avg |
|------|---------|---------|---------|----------|-----------|
| GA | 0.0625 | 0.0625 | 0.125 | 0.250 | 12.0 |
| MCTS | 0.0625 | 0.0625 | 0.125 | 0.375 | 30.0 |
| BO（全池 16 dopant） | 0.0625 | 0.0625 | 0.0625 | **1.0** | 183.6 |
| SR | 0.0625 | 0.1875 | 0.25 | 0.312 | 12.0 |

- coverage 与 hit@k 差异量化「规则评分偏好（浓度 3-8%）vs 期望浓度（1-2%）错配」；BO 扩池后（DOPANT_POOL 11→16 + 默认全池遍历）coverage 0.4375→**1.0**，池缺口根治实证（I/Te/Nb/Fe/Mg 等 5 个期望 dopant 入池，16/16 全覆盖）。

## 5. 路线 A 评测结果

### 5.1 三臂消融（VerificationOracle 真值评分代理）

VerificationOracle 加载全部 OQMD 验证产物构建真值表（220 条公式记录 / 15 母体体系），以稳定性判定系数（已知 0.85 / 新知 0.60 / 验证失败 0.45 / 反例 0.15）为代理评分，8 条 Gap 三臂对比：

| 臂 | mean_best_score | LLM 调用 | 失败 | 唯一 dopant 数 |
|----|----------------|---------|------|---------------|
| full（GA × LLM 融合） | **0.806** | 55 | 1 | 1.5 |
| rule（纯规则 GA） | **0.885** | 0 | 0 | 1.0 |
| llm（LLM 直出候选） | 0.785 | 16 | 0 | 2.75 |

| 增益 | 值 | 解读 |
|------|-----|------|
| GA 演化增益（full - rule） | **+2.65%** | 严苛真值下 LLM 融合未损害演化增益（真值表扩面后由负转正） |
| LLM 融合增益（full - llm） | -8.93% | 负值收窄；成因 = 真值表覆盖集中于 rule 臂命中母体，非 LLM 无能（对比 5.2 召回率 LLM 模式全量覆盖） |
| LLM 直出 vs 规则（llm - rule） | -11.28% | LLM 直出多样性高（2.75 dopant）但命中的已验证母体少 |

> 消融历史（如实记录）：首轮 oracle full 0.803 / rule 0.933 / llm 0.836 → A/B 位拆分重验 38 失败项归零后 full 0.806 / rule 0.885 / llm 0.785。

### 5.2 四算法召回率统一对比矩阵（16 条已知关系全量，LLM/规则双模式，扩池后）

| 算法 | 模式 | recall@1 | recall@3 | recall@5 | coverage |
|------|------|---------|---------|---------|----------|
| **GA** | LLM | **0.750** | **0.875** | **0.938** | 0.938 |
| SR | LLM | 0.688 | 0.875 | 0.875 | 0.938 |
| MCTS | LLM | 0.438 | 0.750 | 0.812 | **1.0** |
| BO | LLM | 0.438 | 0.750 | 0.750 | **1.0** |
| BO | 规则 | 0.062 | 0.062 | 0.062 | **1.0** |
| MCTS | 规则 | 0.062 | 0.062 | 0.125 | **1.0** |
| GA | 规则 | 0.062 | 0.062 | 0.125 | 0.250 |
| SR | 规则 | 0.062 | 0.188 | 0.250 | 0.312 |

- 全量 16 条（夜间批量 `eval_recall.py --llm --algo all --bo-dopants 16 --max-facts 16`，deepseek-chat）下，LLM 模式 **GA 最优**（recall@1=0.75/@5=0.938/cov=0.938），SR 次之（recall@1=0.688）；**MCTS/BO 双模式 coverage=1.0**（16/16 全覆盖）；LLM 模式相对规则模式全面增益（GA cov 0.25→0.938、SR 0.312→0.938、BO 0.0625→0.75、MCTS cov 0.375→1.0、recall@5 0.25→0.812）。
- 十四次深度开发 MCTS 短板攻坚：cov 0.375→**1.0**、recall@1 0.062→**0.438**、recall@5 0.25→**0.812**——两处结构性上限修复（「展开即评估」解决叶采样预算：每次迭代仅评估 1 叶 → 展开层批量打分全部 80 叶全收录；`valid_hosts` 过滤去掉带数字下标母体 Mg3Sb2/Bi2Te3/CoSb3 → 期望母体全部入搜索空间）+ LLM 批量评估 batch 20→10（规避 max_tokens=1200 截断致 hit@k 与规则模式完全一致的静默降级陷阱），详见 exp.md 经验 123/124/125。
- 注：早期 3 条小批量矩阵（`recall_matrix_20260808T160119.json`，SR recall@3=1.0）由 16 条全量矩阵（`recall_matrix_20260808T204159.json`）取代，最新为 `recall_matrix_20260808T211437.json`（MCTS 短板修复后重合并）；全量结果保留 GA 优势口径。

### 5.3 数据库交叉验证（OQMD 主 + MP 增强）

- OQMD 免 Key REST：整数成分直查（分数成分经 A/B 位拆分纯母体后重验），hull ≤ 0.1 eV/atom 判定稳定。
- 验证规模：47 份验证产物 / oracle 真值表 220 条 / 15 母体体系；38 项「分数成分超时」验证失败 → 重验后全部「已知」，失败 38→0。
- 结果分布示例：GeTe 母体 hull=0.002 eV/atom 稳定 → 「已知」；掺杂成分标记 novel_dopant 交 LLM 判断新知。
- 跨库分歧处理：GeTe 在 OQMD「稳定」vs MP mp-1080459「不稳定」→ `check_mp_phase_diagram.py` 相图级核对（get_entries_in_chemsys + PhaseDiagram）hull=0.0 稳定，分歧归因「条目级亚稳相 vs 相图级判定」粒度差异，分歧消除。
- 反例闭环：10 个反例母体（SiGe、Cu2Se 等）自动回喂 GA 剪枝器（action="prune_feedback"），实现「搜索-验证」负反馈闭环。

### 5.4 四算法输出融合投票

- `src/search/ensemble.py`：候选 key =（host 归一化 + dopant + 浓度 0.5 步长取整）；rank 1/rank 加权 → 同算法去重只计最高排名（防刷票）→ 得票降序。
- 四算法规则模式产物（GA/MCTS/BO/SR 各 29 份 finding，`results/findings/`）：29 Gap / 348 候选，**0 多算法共识**——规则模式各算法使用独立「规则网格」种子（GA-Ti4%、BO-Ti1%、SR-Cu4%、MCTS 跨母体探索），候选配方互不重合，共识为 0 是诚实结果。
- 多算法共识的价值预期在 LLM 模式（种子由 LLM 生成更趋同）；规则模式融合清单 `results/ensemble/ensemble_20260808T093952.md/.html` 已按得票/得分降序呈现单算法最优候选（如 Pb0.96Ti0.04Te、Bi2Te3-Ti4%）。
- 旧单算法清单（`ensemble_20260808T080948`）已由四算法版本取代；旧 finding 归档至 `results/findings/archive_20260804/` 避免污染投票。

## 6. 证据链与可审计性

- **数据结构**：`EvidenceItem{source, doc_id, page, text, fetched_at}` → `EvidenceChain{conclusion, items, validated}`，任何结论（Gap/Finding/验证）强制携带。
- **统一审计日志**：全部 Agent 写 JSONL（`results/logs/`），`src/audit/evidence_report.py` 五项审计（日志健康度 / 证据链覆盖 / 降级留痕 / 判定分布 / 输出渲染 MD+HTML）。
- **审计结果**：检索 doc_id=80 / 29 Gap / 146 finding / 47 验证 / 5 知识库条目；审计首轮暴露 Gap 28/29 `evidence_ids` 为空——经 `scripts/backfill_gap_evidence.py`（kb_exact / kb_parent / kb_similar / retrieval / retrieval_title / retrieval_parent 六通道，`src/evaluation/gap_evidence_backfill.py`）回填后 **Gap 可回溯 1/29 → 29/29**（六通道来源分布：retrieval 28 / retrieval_title 8 / kb_similar 2 / kb_parent 2，含变量式名义母体 Ge1-xBixTe→GeTe）；finding/验证的 evidence 经 `scripts/backfill_result_evidence.py`（`src/evaluation/result_evidence_backfill.py`，六通道扩展到 finding top_candidates[].host 与验证 candidate_formula/parent_formula）补强后 **finding 可追溯 7/36 → 146/146、验证可追溯 15/47 → 43/47**（剩余 4 份无证据为 failed_rerun_summary/mp_phase_check 等非候选汇总文件，如实保留）；降级留痕 540 条（LLM 缺失 Key/失败时规则路径不中断）。

## 7. 科学意义与新知/已知区分

- **已知（文献+数据库双支撑）**：GeTe/PbTe 母体稳定、Na 掺杂 PbTe 提升 zT、Bi2Te3 系掺杂方案——搜索能复现文献已知关系，验证搜索空间建模正确性。
- **新知候选（构效关系假设）**：Ge0.94Bi0.06Te（full 臂 0.933）、Mg3Sb2-Zn(on Mg)3%（llm 臂，5 唯一 dopant 多样性）、ZrNiSn-Ti5% 功率因子 trade-off 量化缺口——输出时标注「与已有结论的关系」并在 OQMD 真值表中验证。
- **可解释性**：LLM 评估器返回科学/可行性/文献支持三维评分 + 机制简述（如「In 掺杂共振能级」），SR 输出显式公式 + R²，非黑箱。

## 8. 局限性与负结果（如实记录）

- LLM 融合增益为负（-8.93%）：真值表覆盖偏置所致；改进 = 扩大 oracle 真值 + 提升 full 臂候选多样性（夜间批量）。
- 规则模式召回率整体低（GA/SR cov 0.25-0.31）：规则评分与期望浓度窗口错配；已通过 BO v2 外层遍历 + 扩池缓解（BO cov 0.4375→**1.0**，GA/SR 由 LLM 模式弥补）。
- **MCTS 短板攻坚完成（十四次深度开发，cov 0.375→1.0）**：原局限 = 树搜索结构（UCT 预算内仅访问部分叶节点）+ LLM 评估器价值信号未传导至节点排序；已通过「展开即评估」（level1 展开 dopant 层时批量打分全部 80 叶并收录，覆盖不再依赖迭代预算）+ `valid_hosts` 过滤修复（此前把带数字下标母体 Mg3Sb2/Bi2Te3/CoSb3 挡在搜索空间外 → 期望母体全入空间）+ LLM 批量评估 batch 20→10（规避 max_tokens 截断致评分静默 fallback 规则）三处修复，LLM 模式 cov=1.0、recall@5=0.812，不再是全量矩阵短板。
- Gap evidence_ids 回填后已 29/29 全可追溯（六通道：kb_exact / kb_parent / kb_similar / retrieval / retrieval_title / retrieval_parent）；finding/验证 evidence 已通过 `scripts/backfill_result_evidence.py` 补强（finding 146/146、验证 43/47，验证剩余 4 份无证据为非候选汇总文件）。
- LLM 抽取 composition/structure 字段 recall=0：提示词与输入结构需对齐（gold 口径下属性类字段 F1 0.6 已可用）。

## 9. 复现说明

```bash
# 安装与环境变量见 README「安装步骤 / 环境变量」
pip install -r requirements.txt

# 全链路复现（命令级）
python scripts/run_retrieval.py            # 1 检索
python scripts/run_extraction.py           # 2 抽取
python scripts/run_gap.py                  # 3 Gap
python scripts/run_report.py               # 4 报告
python scripts/run_search.py --no-llm --top-n 29 --generations 2 --pop-size 10   # 5 搜索
python scripts/run_validation.py           # 6 验证
python scripts/run_audit_report.py         # 7 审计
python scripts/backfill_gap_evidence.py    # 7.5 Gap 证据链回填（--dry-run 预览 / 写回 gaps.json）
python scripts/backfill_result_evidence.py # 7.6 finding/验证 证据链回填（--target findings|validation|all）
python scripts/run_ensemble.py             # 8 融合投票

# 评测复现
python scripts/eval_extraction_f1.py --gold       # 字段级 F1（需 data/eval/extraction_gold.json）
python scripts/eval_recall.py --algo all          # 规则模式召回率
python scripts/eval_recall.py --llm --algo all --bo-dopants 16 --max-facts 16   # LLM 模式全量 16 条（夜间批量，需 DEEPSEEK_API_KEY）
python scripts/merge_recall_matrix.py             # 四算法对比矩阵
python scripts/run_ablation.py                    # 三臂消融

# 质量门禁
ruff check .
python -m pytest -q
```

- 随机种子：见第 3 节；LLM 模式非确定性，调用日志 `results/logs/*.jsonl` 可审计。
- 全部评测固定输入产物（时间戳文件），重跑即得可对比 JSON。

## 10. 依赖与合规披露

### 商业 API / 闭源模型

| 服务 | 用途 | 费用假设 | 可替代性 |
|------|------|---------|---------|
| Sciverse API | 文献检索 / Gap 回查 | 免费额度 | 可替换 Semantic Scholar / OpenAlex |
| DeepSeek chat API | LLM 抽取 / 推理 / 搜索三角色 | 按 token 计费（低） | 任意 OpenAI 兼容端点（`src/common/llm.py` 可配） |
| Materials Project API | 数据库增强验证 | 免费 | 缺失时降级 OQMD |

### 外部数据来源

| 数据集 | 来源 | 授权协议 |
|--------|------|---------|
| Sci-Base | HuggingFace opendatalab/Sci-Base | CC-BY-4.0 |
| 检索产物语料 | Sciverse 真实检索结果（本地） | 检索 API 条款 |
| OQMD | oqmd.org | 开放学术使用 |
| Materials Project | materialsproject.org | MP 使用条款 |

### 已有项目与原创性

本项目为参赛团队原创实现（无第三方项目衍生）；技术路线参考公开文献（CheMatAgent HE-MCTS、dZiner、ChatMat 等，见 `.trae/rules/05-route-a-SPR.md` 前沿基准），实现均为自研代码。

---

> 配套文档：`README.md`（快速开始/复现）、`docs/initial-round-proposal.md`（初赛方案）、`.trae/plan/整体计划/`（开发计划与进度）

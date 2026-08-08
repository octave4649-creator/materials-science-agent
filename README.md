# 材料科学文献驱动的科学发现智能体

> 赛道三：前沿探索 AI for Research · 方向三（材料科学文献驱动的科学发现智能体）· 路线 A（构效关系发现）

面向**热电材料**细分领域，构建「文献检索 → 知识抽取 → Research Gap 识别 → 搜索算法 × LLM 融合探索 → 数据库交叉验证」全链路可审计的科学发现智能体，产出具有文献证据链支撑、经公开材料数据库验证的**掺杂-性能构效关系（Structure–Property Relationship, SPR）候选**。

## 项目简介

- **基本任务（文献调研 Agent）**：Sciverse 双通道检索 + LLM/规则双路径知识抽取 + 覆盖率/矛盾/LLM 推理三种 Gap 识别 + 结构化调研报告生成，全流程证据链（`EvidenceChain`）可审计。
- **进阶路线 A（构效关系发现）**：遗传算法（GA）/ 蒙特卡洛树搜索（MCTS）/ 贝叶斯优化（BO）/ 符号回归（SR）四算法 × LLM 三角色融合（假设种子生成器 / 科学合理性评估器 / 搜索空间引导器），四算法输出融合投票，OQMD/MP 数据库交叉验证，VerificationOracle 真值评分代理消融量化。
- **复赛增强**：Sci-Base RAG local search（手写 Okapi BM25）+ LangGraph 多 Agent 状态机编排（条件路由 + HITL 审核）、证据链审计界面、四算法融合投票。

## 核心结果（量化概览）

| 评测项 | 结果 | 产物 |
|--------|------|------|
| 知识抽取字段级 F1（LLM vs 人工 gold） | micro F1=0.40 / macro F1=0.33 | `results/eval/extraction_f1_20260808T155846.json` |
| 召回率·LLM 模式（3 条小批量） | SR recall@3=1.0/cov=1.0 最优，GA recall@5=1.0，MCTS cov=1.0 | `results/eval/recall_matrix_20260808T160119.json` |
| 召回率·规则模式（16 条全量） | BO coverage=0.4375 最高 | 同上 |
| 三臂消融（VerificationOracle 真值） | full 0.806 / rule 0.885 / llm 0.785；GA 演化增益 +2.65% | `results/ablation/ablation_report.json` |
| 批量搜索-验证 | 29 Gap → 36 finding → 220 候选验证记录（14 母体体系） | `results/findings/`、`results/validation/` |
| 证据链审计 | 30 doc_id / 29 Gap / 36 finding / 47 验证，降级 404 条留痕 | `results/audit/evidence_report_*.md/.html` |
| 四算法融合投票 | 29 Gap / 157 候选，Borda rank 加权共识 | `results/ensemble/ensemble_*.md/.html` |

> 详见 [实验报告](docs/experiment-report.md)。

## 环境要求

- Python 3.10+（实测 3.14 主环境；MinerU 解析需 3.13，见 `src/extraction/mineru_pipeline.py`）
- 依赖：见 [requirements.txt](requirements.txt)（`pyproject.toml` 同步维护）
- 外部服务：Sciverse API（文献检索）、DeepSeek API（LLM，可选但推荐）、Materials Project API（数据库验证，可选）

## 安装步骤

```bash
pip install -r requirements.txt

# 可选依赖组（按需）
pip install -e ".[extraction]"   # MinerU 文档解析
pip install -e ".[validation]"   # pymatgen / mp-api 数据库验证
pip install -e ".[search]"       # scikit-learn / pymoo / deap
```

## 环境变量

密钥一律走环境变量或项目根 `.env`（不入库），见 `src/common/config.py`：

| 变量 | 用途 | 必需 |
|------|------|------|
| `SCIVERSE_API_TOKEN`（或 `SCIVERSE_API_KEY`） | Sciverse 文献检索（亦支持 `sciverse auth login` 凭据兜底） | 检索必填 |
| `DEEPSEEK_API_KEY` | LLM 抽取 / Gap 推理 / 搜索三角色（未配置时自动降级规则路径） | 推荐 |
| `MP_API_KEY` | Materials Project 增强验证（缺失时优雅降级 OQMD） | 可选 |

## 快速开始（命令级复现）

```bash
# 1. 文献检索（Sciverse 双通道，产物 results/retrieval_*.json）
python scripts/run_retrieval.py

# 2. 知识抽取（LLM 优先 + 规则降级，产物 data/knowledge_base.json）
python scripts/run_extraction.py

# 3. Research Gap 识别（覆盖率/矛盾/LLM 推理 + Sciverse 回查，产物 data/gaps.json）
python scripts/run_gap.py

# 4. 调研报告生成（9 章节 MD/HTML，产物 results/reports/）
python scripts/run_report.py

# 5. 路线 A：批量搜索（29 Gap → findings，--no-llm 为规则模式）
python scripts/run_search.py --no-llm --top-n 29 --generations 2 --pop-size 10

# 6. 数据库交叉验证（OQMD 免 Key + MP 增强，产物 results/validation/）
python scripts/run_validation.py

# 7. 证据链审计报告（统一日志可视化，产物 results/audit/）
python scripts/run_audit_report.py

# 8. 四算法融合投票（消费 findings，产物 results/ensemble/）
python scripts/run_ensemble.py
```

### 评测复现

```bash
# 字段级 F1（--gold 对照人工标注 data/eval/extraction_gold.json）
python scripts/eval_extraction_f1.py --gold

# 召回率评测（四算法 × 规则/LLM 双模式；--llm 需 DEEPSEEK_API_KEY）
python scripts/eval_recall.py --algo all
python scripts/eval_recall.py --algo ga --llm

# 四算法统一对比矩阵合并
python scripts/merge_recall_matrix.py

# 三臂消融（full / rule / llm，VerificationOracle 真值评分）
python scripts/run_ablation.py

# Gap 新颖性人工复核（--write-back 写回 gaps.json）
python scripts/review_gap_novelty.py --write-back
```

## 可复现性说明

- **固定随机种子**：GA 按代数确定性随机（`random.Random(gen)`）、MCTS `random.Random(7)`、SR `random.Random(42)`、BO 浓度网格全覆盖无随机；评测固定 `--max-facts` 等参数可逐条复现。
- **LLM 模式依赖外部模型**（deepseek-chat），非完全确定性——每次调用的请求/响应均写审计日志（`results/logs/*.jsonl`），且 LLM 失败自动降级规则路径并留痕，管线不中断。
- **评测链路**：所有评测输出含 `generated_at` 时间戳与输入产物路径，可对照 `results/eval/*.json` 复核。
- **数据缓存**：检索/验证结果缓存于 `data/cache/`（不入库），重复调用不重复计费。

## 项目结构

```
├── src/
│   ├── agent/          # 检索/抽取/Gap/报告/搜索/验证六 Agent
│   ├── audit/          # 证据链审计（evidence_report）
│   ├── common/         # LLM 统一接入 / 配置 / JSON 审计日志
│   ├── evaluation/     # 字段级 F1 / 召回率评测
│   ├── extraction/     # MinerU 解析 + schema 抽取 + 知识库
│   ├── gap/            # 覆盖率 / 矛盾检测 / Gap schema
│   ├── orchestration/  # LangGraph 状态机编排（HITL）
│   ├── proteome/       # 生物材料·酵母蛋白质组学管线
│   ├── rag/            # Sci-Base RAG（手写 BM25）
│   ├── report/         # 报告组装 / 渲染
│   ├── retrieval/      # Sciverse 双通道检索 + 证据链
│   ├── search/         # GA/MCTS/BO/SR × LLM 融合 + 融合投票
│   └── validation/     # OQMD/MP 验证 + VerificationOracle + 反例回喂
├── scripts/            # 全部运行/评测入口
├── data/               # gaps / knowledge_base / 评测标注
├── results/            # 检索/抽取/Gap/搜索/验证/评测/审计/融合产物
├── tests/              # 单元测试（pytest，全 mock 无网络）
└── docs/               # 方案文档 / 实验报告
```

## 评测与质量

```bash
ruff check .            # 零 error 门禁
python -m pytest -q     # 全量单测（311+ 项，全 mock 无网络依赖）
```

## 依赖与授权披露

- **商业 API / 闭源模型**：Sciverse API（文献检索，免费额度）、DeepSeek chat API（LLM，按 token 计费，可替换为任意 OpenAI 兼容端点）、Materials Project API（数据库验证，免费）。调用环节均写入证据链日志，缺失 Key 自动降级不影响管线。
- **外部数据**：Sci-Base（CC-BY-4.0）、Sciverse 检索产物、OQMD（开放）、Materials Project（遵守其使用条款）；全部外部数据于 `data/README.md` 登记。
- **开源依赖**：见 [requirements.txt](requirements.txt) 与 `pyproject.toml`。
- **协议**：本项目以 MIT 协议开源，见 [LICENSE](LICENSE)。

## 致谢

- OpenDataLab Sciverse / Sci-Base / MinerU（文献数据与解析）
- Materials Project / OQMD（材料数据库）
- 赛事：GOAI 世界人工智能开源大赛 · 赛道三

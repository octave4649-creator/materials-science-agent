---
alwaysApply: true
---
# 项目规范

## 1. 规范概述

本文件是项目开发的总规范，适用于所有参与「方向三：材料科学文献驱动的科学发现智能体」赛题开发的成员。规范遵循 6A（感知/分析/行动/适应/评估/自主）与 5S（结构/标准/安全/可扩展性/可持续性）原则，覆盖从目录组织到提交发布的完整开发链路。

**适用范围**：本仓库全部代码、文档、数据与配置。所有提交必须符合本规范，特殊场景需在 PR/提交说明中注明理由。

**材料领域定位**：本项目面向**生物材料**方向——以酵母蛋白质组学（WAYB/WAYC 数据集）为核心研究对象，将酵母菌株视为「功能生物材料」，以基因表达谱作为「材料成分描述符」，以培养条件（温度/培养基/化学扰动）作为「合成加工条件」，构建设效关系（基因表达→菌株性能）发现管线。

**配套文档**：

| 文档 | 用途 |
|------|------|
| `DEVELOPMENT-GUIDE.md` | 整体开发路线图与方法论（做什么、怎么做、顺序） |
| `.trae/rules/01-10-*.md` | 知识库：赛题规则、数据源、材料数据库、Agent 设计等 |
| `materials-science-kb/` | 知识库导航与清单 |

**核心数据集**：

| 数据集 | 内容 | 规模 |
|--------|------|------|
| WAYB/WAYC 酵母蛋白质组学 | 5 种菌株 × 41 种化学扰动 × 5243 蛋白表达量 | 13,412 样本（train+val+test） |

## 2. 项目结构规范

### 2.1 目录结构

```
项目根目录/
├── DEVELOPMENT-GUIDE.md          # 整体开发指导（总入口）
├── README.md                     # 项目简介、快速开始（提交前必填）
├── requirements.txt / pyproject.toml  # 依赖锁定
├── .trae/rules/                  # 知识库与规范（01-10 + 本文件）
├── materials-science-kb/         # 知识库导航与清单
├── src/                          # 源码（核心）
│   ├── agent/                    # Agent 编排（LangGraph 状态机）
│   │   ├── retrieval_agent.py    # 检索 Agent
│   │   ├── extraction_agent.py   # 抽取 Agent
│   │   ├── analysis_agent.py     # 分析 Agent（Gap 识别）
│   │   └── report_agent.py       # 报告 Agent
│   ├── retrieval/                # 文献检索实现
│   │   ├── sciverse_client.py    # Sciverse API 封装
│   │   └── evidence.py           # 证据链数据结构
│   ├── extraction/               # 知识抽取
│   │   ├── schemas.py            # 抽取 Schema
│   │   └── mineru_pipeline.py    # MinerU 解析管线
│   ├── gap/                      # Research Gap 识别
│   │   ├── coverage.py           # 覆盖率分析
│   │   └── contradiction.py      # 矛盾检测
│   ├── search/                   # 路线A：搜索算法 × LLM
│   │   ├── ga_search.py          # 遗传算法
│   │   ├── mcts_search.py        # MCTS
│   │   ├── bo_search.py          # 贝叶斯优化
│   │   └── sr_search.py          # 符号回归
│   ├── validation/               # 数据库交叉验证
│   │   ├── mp_client.py          # Materials Project 封装
│   │   └── proteome_validator.py # 蛋白质组学数据验证（新增：生物材料）
│   ├── proteome/                 # 生物材料·蛋白质组学管线（新增）
│   │   ├── data_loader.py        # WAYB/WAYC 数据加载
│   │   ├── feature_engineering.py # 特征工程（基因表达→材料描述符）
│   │   └── strain_response.py    # 菌株响应标签构建
│   ├── report/                   # 报告生成
│   └── common/                   # 公共模块
│       ├── llm.py                # LLM 统一接入
│       ├── config.py             # 配置管理（环境变量）
│       └── logging.py            # 审计日志
├── scripts/                      # 运行脚本
├── data/                         # 数据（或获取脚本）
│   ├── raw/                      # 原始数据（WAYB/WAYC CSV）
│   ├── processed/                # 预处理后的数据
│   └── cache/                    # 缓存
├── results/                      # 实验结果
├── docs/                         # 文档
└── tests/                        # 测试
```

### 2.2 结构约束

- 代码按功能模块分目录，禁止单文件堆叠
- `data/` 不存放原始大文件，使用获取脚本或 symlink，避免仓库膨胀
- 新增模块遵循既有模式：`src/<module>/` + `tests/test_<module>.py`
- 配置与密钥禁止硬编码，统一走环境变量或 `.env`（不入库）

## 3. 代码规范

### 3.1 语言与格式

| 项目 | 规范 |
|------|------|
| 语言 | Python 3.10+，类型标注（type hints）必写 |
| 缩进 | 4 空格，禁 Tab |
| 行长 | 不超过 100 字符 |
| 引号 | 字符串用单引号，文档字符串用双引号 |
| 命名 | 变量/函数小驼峰或 snake_case；类 PascalCase；常量 SNAKE_CASE |
| 格式工具 | 统一 `ruff format` + `ruff check`（pre-commit 钩子） |
| 排序 | `import` 按标准库 → 第三方 → 本地排序 |

### 3.2 注释与文档

- 公共函数/类必须写 docstring：功能、参数、返回值、异常
- 复杂逻辑（搜索算法、证据链构建）必须有行内注释说明思路
- 注释用中文，与代码同步更新
- 禁止大段无注释代码；禁止「为了注释而注释」

### 3.3 错误处理

- 网络/API 调用必须 try/except 包裹，记录可读错误并给出降级策略
- LLM 输出必须校验 schema，解析失败时重试或标记降级
- 禁止裸 `except: pass` 吞异常

### 3.4 测试

- 每个模块配套 `tests/` 单测，关键逻辑（Gap 识别、搜索算法）覆盖率 ≥ 70%
- 外部依赖（Sciverse/MP）用 mock 或本地 fixture 测试，避免 CI 依赖网络
- 复赛前必须有可重复的评测脚本（见 7.3 评测规范）

## 4. Agent 开发规范

### 4.1 Agent 设计原则

1. **职责单一**：一个 Agent 只做一类事（检索/抽取/分析/报告），通过编排层组合
2. **证据链强制**：任何结论输出必须附带 `EvidenceChain`（来源、DOI、页码、调用记录），禁止无来源结论
3. **可观测性**：每个 Agent 暴露结构化日志（输入、输出、耗时、工具调用序列）
4. **可回退**：LLM 调用失败/超时必须有降级路径（重试 → 简化 prompt → 跳过并记录）
5. **人工介入（HITL）**：关键节点（Gap 确认、构效关系输出）支持人工审核，符合 LangGraph checkpoint

### 4.2 证据链数据结构

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class EvidenceItem:
    """单条证据"""
    source: str          # 来源（sciverse / mp / oqmd / mineru）
    doc_id: str          # 文档/记录 ID（如 DOI、material_id）
    page: str | None     # 页码或段落定位
    text: str            # 证据原文片段
    fetched_at: datetime = field(default_factory=datetime.now)

@dataclass
class EvidenceChain:
    """证据链：一个结论的全部证据"""
    conclusion: str                # 结论陈述
    items: list[EvidenceItem]      # 证据列表
    validated: bool = False        # 是否经数据库/人工验证
```

### 4.3 Agent 日志规范

- 统一 JSON 日志：`{ts, agent, action, input_summary, output_summary, duration_ms, status}`
- 工具调用序列单独记录（工具名、参数、结果摘要）——用于审计与消融实验
- 日志写入 `results/logs/`，文件名含日期

## 5. 数据与 API 使用规范

### 5.1 Sciverse 使用规范

- API Key 存环境变量 `SCIVERSE_API_KEY`，禁止入库
- 调用记录自动写入证据链（doc_id + fetched_at）
- 注意配额与费用：优先缓存检索结果到 `data/cache/`，避免重复调用
- 语义检索与结构化检索分离，按需调用

### 5.2 材料数据库规范

- Materials Project 使用 `MP_API_KEY` 环境变量，禁止硬编码
- 查询结果缓存到本地（Parquet/JSON），标注抓取时间
- 批量查询注意 API 限额，必要时分片 + 限速
- 引用数据遵守各库使用条款（MP/OQMD/NOMAD 须注明出处）

### 5.3 蛋白质组学数据规范（生物材料方向）

- WAYB/WAYC 数据集存放在 `data/raw/`，文件名保持原始不变
- 数据结构：metadata CSV（15列样本元数据）+ proteome CSV（5244列=1 sample_ID + 5243 蛋白特征）
- 样本划分：train(5920) / val_strain_only(1547) / val_chem_only(1065) / val_both(269) / val_time(157) / test(4454)
- 5 种酵母菌株：BAI、BAH、DHY210、CEK、CGD
- 培养条件：温度(30°C/37°C)、培养基(YNB+CSM+葡萄糖/半乳糖)、41 种化学扰动
- 特征处理：5243 维蛋白表达量需做对数转换/归一化后作为搜索算法输入
- 特征工程：将基因表达谱聚合为「菌株-条件」级别的材料描述符（e.g. 特定功能蛋白家族的表达模式）

### 5.4 数据与授权

- Sci-Base（CC-BY-4.0）可自由使用，需注明来源
- WAYB/WAYC 数据集为赛事提供，仅限本次参赛使用
- 禁止将付费/受限数据混入开源仓库
- 所有外部数据在 `data/README.md` 中登记：来源、授权、版本、获取时间

## 6. 文档规范

### 6.1 元数据要求

所有知识/规范 Markdown 文件必须带 YAML frontmatter：

```yaml
---
title: "文档标题"
category: "分类"
tags: [标签1, 标签2]
description: "检索摘要"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: "draft" | "review" | "published"
version: "1.0"
---
```

### 6.2 命名规范

- 文件：`kebab-case`（小写连字符），数字前缀排序：`01-xxx.md`
- 目录：小写连字符
- 图片/资源：`assets/` 下按主题子目录

### 6.3 更新纪律

- 知识内容变化即更新 `updated` 与 `version`
- 过时内容标注 `status: draft` 或删除，不留「僵尸文档」
- 文档与代码同步：接口变更后 24h 内更新对应文档

## 7. 质量与评测规范

### 7.1 代码质量门禁

- 提交前：`ruff check` 零 error、单测全绿
- PR 评审：至少 1 人评审，重点检查证据链、错误处理、schema 校验
- 关键路径（检索、抽取、搜索）必须有 smoke test

### 7.2 评测规范（对应 DEVELOPMENT-GUIDE.md 第 6 节）

- 建立 `results/` 评测基线，指标记录为 JSON，可对比
- 基本任务评测：检索 NDCG@K、抽取 F1、Gap 准确率/新颖性
- 路线 A 评测：搜索效率、发现质量、融合深度（消融）、可解释性
- 所有评测固定随机种子，结果可复现

### 7.3 实验记录

- 每个实验记录：配置、输入、输出、指标、时间
- 负结果同样记录（Gap 识别失败、搜索无收敛）——用于报告科学意义论证

## 8. Git 工作流规范

### 8.1 分支模型

```
main            # 稳定版（提交前冻结）
├── dev         # 集成开发分支
└── feature/*   # 功能分支（从 dev 切出）
```

- `main` 只接受可运行、可复现的版本
- 新功能：`feature/<模块>-<简述>`，完成后合并 dev
- 修复：`fix/<简述>`

### 8.2 提交规范（Conventional Commits）

```
<type>(<scope>): <描述>

类型：feat / fix / docs / test / refactor / chore / style
示例：
feat(retrieval): 实现 Sciverse 语义检索封装
fix(gap): 修复覆盖率分析边界条件
docs(rules): 更新项目规范第 5 节
```

- 提交信息用中文描述，一行 ≤ 72 字符
- 一次提交只做一个逻辑变更
- 禁止提交密钥、大文件（>50MB）、缓存产物

### 8.3 保护规则

- 严禁 force push 到 main/dev
- `.env`、`*.key`、`MP_API_KEY`、`SCIVERSE_API_KEY` 必须加入 `.gitignore`

## 9. 合规规范

### 9.1 API 与模型披露

| 场景 | 要求 |
|------|------|
| 商业 API | 披露调用环节、费用假设、权限范围、可替代性、对复现性的影响 |
| 闭源模型 | 同商业 API 要求 |
| 外部数据 | 登记来源、授权、版本 |

### 9.2 开源合规

- 复赛前仓库必须有 `LICENSE` 文件
- 派生项目须说明原项目来源、团队贡献范围、新增创新点、与原协议兼容性
- README 必须包含：项目简介、环境要求、安装步骤、快速开始、复现说明、依赖与授权清单

### 9.3 安全红线

- 禁止提交任何密钥、Token、API Key
- 禁止在日志中输出完整 Key 或敏感配置
- 输入校验：LLM 输出必须经 schema 校验后才可入库

## 10. 团队协作规范

- 每日同步进度：`todo` 列表更新到项目看板/文档
- 模块负责人制：检索/抽取/Gap/搜索各设负责人，接口先行
- 每周代码评审：重点评审证据链完整性与模块解耦
- 复用优先：已有能力（Sciverse/MinerU/mp-api）不重复造轮子，创新聚焦搜索×LLM 融合

## 11. 规范执行

- 本规范由全体成员共同维护，修订需在 PR 中说明原因
- CI 门禁：ruff + pytest + 关键 smoke test（复赛阶段启用）
- 违反规范的风险：证据链断裂（影响 30% 科学意义分）、代码不可复现（影响 45% 技术性能分）、合规缺失（影响 5% 开源贡献分甚至取消资格）

---

> 相关文档：[[DEVELOPMENT-GUIDE]]、[[赛题规则与要求]]、[[工具链]]

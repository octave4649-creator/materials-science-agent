---
title: "分项计划·模块2 知识抽取 Agent · 研究发现"
type: "plan"
category: "subplan"
tags: [抽取Agent, findings, MinerU, schema]
created: "2026-08-04"
updated: "2026-08-04"
status: "active"
version: "1.0"
---

# 模块2 知识抽取 Agent · 研究发现（findings）

## 技术调研

### MinerU 三后端（2026 最新）
- **结果**：pipeline（CV+NLP，纯 CPU 16GB 可跑，无幻觉确定性）/ vlm-engine（MinerU2.5-Pro，OmniDocBench 95.39，GPU 8GB+）/ hybrid（速度+精度平衡）
- **安装**：`pip install "mineru[all]"`；CLI `mineru parse -i paper.pdf -o out.md --format markdown`
- **能力**：表格转 HTML + 跨页合并（99.2%）、公式转 LaTeX、OCR 109 语言、版面分析与阅读顺序优化
- **许可证**：Apache 2.0 风格自定义（2026.4 起）

### 知识抽取 Schema（五段式）

```json
{
  "material": {"formula": "string", "composition": "string", "structure": {"space_group": "string", "lattice": "string", "phase": "string"}},
  "properties": [{"name": "string", "value": "number", "unit": "string", "condition": "string"}],
  "methods": [{"type": "DFT|MD|ML|EXPERIMENT", "software": "string", "key_params": "string"}],
  "synthesis": {"precursors": "string", "temperature": "string", "atmosphere": "string", "duration": "string"},
  "source": {"doi": "string", "page": "string", "paragraph": "string"}
}
```

## 重要发现

### 发现 1：防幻觉三件套
- **内容**：schema 约束 + 原文回查 + 证据链接
- **影响**：LLM 抽取需结构化输出 + 校验，防止编造材料数据
- **建议**：抽取结果必须带 source（doi/page/paragraph）字段

### 发现 2：抽取→知识库驱动路线 A
- **内容**：抽取结果既服务 Gap 识别，也服务路线 A 候选生成
- **影响**：一次采集多处复用，避免重复劳动
- **建议**：落库时即做向量化，供语义检索

### 发现 3：MinerU 3.4.0 CLI 语法与文档不一致（实测）
- **内容**：官方文档写 `mineru parse -i paper.pdf -o out.md --format markdown`；实测 3.4.0 为 `mineru -p <path> -o <out> -b <backend>`，`-p/-o` 必填，无 `--format`（默认输出 markdown）
- **影响**：按文档写命令必报 `Missing option '-p' / '--path'`
- **建议**：封装层以 `mineru --help` 实测为准；默认 backend 为 hybrid-engine（需 GPU），无 GPU 用 `-b pipeline`（纯 CPU 16GB 可跑）

### 发现 4：`python -m mineru` 不可用，需调用可执行文件
- **内容**：mineru 包无 `__main__.py`，`python -m mineru` 报错；控制台脚本在 `Scripts\mineru(.exe)`
- **影响**：子进程封装须先定位可执行文件（python_bin 同环境 Scripts 目录）
- **建议**：`_mineru_exe()` 探测 `Scripts\mineru.exe` → `Scripts\mineru` → PATH 兜底

### 发现 5：化学式归一化需元素符号校验
- **内容**：LaTeX 单位 `0.42\mathrm{Wm}^{-1}\mathrm{K}^{-1}` 会把 `Wm` 误当化学式；`[A-Z][a-z]?\d*` 段式解析 + 118 元素符号集合校验可过滤
- **影响**：规则式降级路径的噪声会污染知识库（下游 Gap 识别输入）
- **建议**：`_is_valid_formula` 校验每段为合法元素符号（至少 2 段）；`re.search` 只取第一个匹配，需用 `finditer` 遍历全部候选跳过非法项

### 发现 6：chunk 证据片段可直接作为抽取输入
- **内容**：模块 1 输出 `papers[].chunk`（Sciverse agentic-search 证据片段）含 LaTeX 化学式/zT/温度，无需全文即可抽取四元组
- **影响**：抽取 Agent 与 MinerU 解耦，主线不依赖 PDF 解析即可验收
- **建议**：MinerU 用于非 OA/本地 PDF 增强；chunk 证据作为默认输入

## 资源链接

- MinerU：https://github.com/opendatalab/MinerU
- 知识抽取设计：`.trae/rules/04-literature-agent.md`

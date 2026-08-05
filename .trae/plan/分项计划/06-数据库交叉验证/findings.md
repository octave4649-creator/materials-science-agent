---
title: "分项计划·模块6 数据库交叉验证 · 研究发现"
type: "plan"
category: "subplan"
tags: [数据库验证, findings, MaterialsProject, pymatgen]
created: "2026-08-04"
updated: "2026-08-04"
status: "active"
version: "1.0"
---

# 模块6 数据库交叉验证 · 研究发现（findings）

## 技术调研

### Materials Project（MP）
- **内容**：最大开源材料计算数据库之一，约 15 万+ 计算材料，DFT 性质（形成能、带隙、弹性、磁性等）
- **API**：`pip install mp-api`，`from mp_api.client import MPRester`，需 API Key（materialsproject.org 注册）
- **关键字段**：`formation_energy_per_atom`、`band_gap`、`is_stable`、`e_above_hull`、`structure`（CIF）
- **用法**：`mp.materials.summary.search(formula="...", fields=[...])`；pymatgen 解析结构

### OQMD
- **内容**：开放量子材料数据库，百万级 DFT 热力学数据
- **API**：REST（`http://oqmd.org/oqmdapi/formationenergy`），无需 Key，支持 composition 查询

### NOMAD / AFLOW / JARVIS
- **NOMAD**：开放研究数据存档，重视原始计算文件；REST API 按 metadata 查询
- **AFLOW**：结构与性质数据库，`aflow.org` REST 查询，含计算带隙、热力学
- **JARVIS**：NIST 联合计算材料库，含 ML 预测结果，`jarvis-tools` 包

### 构效关系验证流程（赛题推荐）
1. **结构匹配**：候选材料（成分/结构）→ pymatgen 解析 + 数据库结构匹配
2. **性质对比**：文献/LLM 主张的性质 vs 数据库计算值（同属性同条件）
3. **误差分析**：偏差阈值判定一致/不一致；稳定相判定用 `e_above_hull`（<0.1 eV/atom 近似稳定）
4. **新知判定**：数据库查不到 / 文献与数据库矛盾 → 标记为待验证新知，进证据链

## 重要发现

### 发现 1：实验值 vs 计算值必须区分
- **内容**：文献多为实验值，MP 等为 DFT 计算值，两者天然有偏差（带隙尤甚，DFT 低估）
- **影响**：直接比较会误判矛盾
- **建议**：对比表标注数据来源（实验/计算），误差阈值按属性类型分别设定

### 发现 2：稳定相判定是关键过滤器
- **内容**：路线 A 候选若不稳定（e_above_hull 高），无合成价值
- **影响**：先用稳定性过滤候选，再比性质
- **建议**：`e_above_hull < 0.1 eV/atom` 作稳定阈值，Phase Diagram 检查竞争相

### 发现 3：验证结果反哺 Gap 与路线 A
- **内容**：验证确认的「新知」升级为科学发现；被否定的候选标记反例（负结果也作证据）
- **影响**：形成「文献→假设→数据库验证→结论」闭环，证据链完整
- **建议**：验证结果统一写回证据链库，供模块 4 报告引用

## 资源链接

- 知识：`.trae/rules/03-materials-databases.md`
- MP：https://materialsproject.org | https://docs.materialsproject.org
- OQMD：http://oqmd.org
- NOMAD：https://nomad-lab.eu
- AFLOW：http://aflow.org
- JARVIS：https://jarvis.nist.gov

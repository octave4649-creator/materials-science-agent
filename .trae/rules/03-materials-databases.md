---
alwaysApply: true
---
# 材料数据库

## 1. 数据库总览与选型

### 1.1 五大数据库对比

| 数据库 | 规模 | 数据内容 | 强项 | 访问方式 |
|--------|------|---------|------|---------|
| Materials Project (MP) | 14 万+ 材料 | 带隙、生成能、能带、态密度、相图 | 电子结构可视化、半导体筛选 | `mp-api` + `MPRester`，需 API Key |
| OQMD | 100 万+ 材料 | 生成能、相图、平衡结构 | 热力学稳定性 | 开放 REST API |
| NOMAD | 海量计算数据 | 原始计算数据与衍生性质 | 数据共享与可复现性 | 网页 + API，OPTIMADE 标准 |
| AFLOW | 350 万+ 结构 | 晶体结构、空间群、对称性、热力学 | 晶体对称性分析、原型结构分类 | REST API `aflowlib.org/API` |
| JARVIS-DFT | 4 万+ 材料 | 光学性质、2D 材料、力学性质 | 光学与二维材料 | 网页 + API |

### 1.2 选型原则

> 一句话选型：MP=首选、AFLOW=晶体对称、OQMD=热力学、NOMAD=共享/复现。根据研究目的选择入口。

- 构效关系挖掘 → MP（性质齐全）+ OQMD（热力学验证）
- 晶体结构探索 → AFLOW（对称性/原型结构）
- 高精度验证 → NOMAD（原始数据可复现）
- 光电/2D 材料 → JARVIS

## 2. Materials Project（MP）

### 2.1 简介

MP 是劳伦斯伯克利国家实验室 2011 年启动的世界最大材料数据库之一，基于 DFT（VASP）计算，覆盖几乎所有元素的无机晶体材料。赛题路线 A 官方推荐与其交叉验证。

### 2.2 数据内容

- 带隙（band gap）、生成能（formation energy）
- 能带结构（band structure）、态密度（DOS）
- 相图（phase diagrams）、热力学稳定性（energy above hull）
- 晶体结构、磁性、力学性质

### 2.3 API 接入

```bash
pip install mp-api pymatgen
```

```python
from mp_api.client import MPRester

# 需要 MP_API_KEY（登录 materialsproject.org 后从 dashboard 获取）
with MPRester("your_api_key_here") as mpr:
    # 按 material_id 查询
    docs = mpr.materials.summary.search(material_ids=["mp-149"])

    # 按性质过滤：含 Si、O 且带隙在 0.5-1.0 eV 之间
    docs = mpr.materials.summary.search(
        elements=["Si", "O"], band_gap=(0.5, 1.0)
    )

    # 限制返回字段加速检索
    docs = mpr.materials.summary.search(
        elements=["Li", "Fe"],
        fields=["material_id", "band_gap", "volume", "formation_energy_per_atom"]
    )
```

### 2.4 关键字段

`material_id`、`formula_pretty`、`band_gap`、`is_metal`、`is_stable`、`formation_energy_per_atom`、`energy_above_hull`、`volume`、`density`、`symmetry`、`ordering`、`total_magnetization`

### 2.5 使用注意

- 功能性（functional）：结构包含 PBE、PBE+U、r²SCAN 弛豫结果，可用 `origins` 字段追溯
- API Key 需保密；大规模下载需联系官方（heavy.api.use@materialsproject.org）
- 数据须遵守 MP 使用条款并注明出处

## 3. OQMD（Open Quantum Materials Database）

### 3.1 简介

美国西北大学开发，专注**生成能与相图**，覆盖元素、二元、三元体系，规模 100 万+ 材料。

### 3.2 数据内容

- 生成能（formation energy）、相图（phase diagrams）
- 平衡结构、热力学稳定性

### 3.3 API 接入

- 网页：http://oqmd.org
- REST API：支持按化学式、元素组成、性质区间查询
- 也支持通过 pymatgen 等工具间接调用

### 3.4 用途

- 路线 A 构效关系的热力学稳定性验证
- 补充 MP 之外的组分空间覆盖

## 4. NOMAD

### 4.1 简介

NOMAD（Novel Materials Discovery）是计算材料科学数据仓库，强调**原始数据共享与可复现性**，遵循 OPTIMADE 标准化访问协议。

### 4.2 数据内容

- 第一性原理计算的原始输入输出
- 衍生性质数据（结构、能量、电子结构等）
- 多方法学（DFT、MD 等）数据

### 4.3 访问方式

- 网页：https://nomad-lab.eu
- OPTIMADE API：标准化的跨库材料数据查询协议
- 支持批量下载与元数据检索

### 4.4 用途

- 获取可复现的高精度计算数据
- 验证文献中报道的计算结果
- 路线 B（模拟方法创新）的基准数据来源

## 5. AFLOW

### 5.1 简介

杜克大学开发，全球最大晶体结构库之一（350 万+ 结构），擅长晶体对称性分析与原型结构分类。

### 5.2 数据内容

- 晶体结构、空间群、对称性信息
- 热力学数据、原型结构
- VASP / Quantum ESPRESSO 计算结果

### 5.3 访问方式

- 网页：http://aflowlib.org
- REST API：`http://aflowlib.org/API`
- 支持按化学式、元素、结构原型查询

## 6. JARVIS-DFT

### 6.1 简介

美国国家标准与技术研究院（NIST）开发的 JARVIS 系列，JARVIS-DFT 覆盖 4 万+ 材料，特色是光学性质与 2D 材料。

### 6.2 数据内容

- 光学性质（带隙、介电常数等）
- 2D 材料、力学性质
- 多种 DFT 泛函与后处理数据

### 6.3 访问方式

- 网页：https://jarvis.nist.gov
- Python 包：`jarvis-tools`

## 7. 数据库交叉验证方法（路线 A 核心流程）

### 7.1 验证目标

区分「新知」与「已知」：发现的构效关系须说明与已有数据库/文献结论的关系。

### 7.2 交叉验证流程

1. **文献知识抽取**：从文献中抽取成分-结构-性能三元组
2. **数据库查询**：对候选材料体系在 MP/OQMD/NOMAD 中查询
3. **一致性检查**：对比文献报道值与数据库计算值
4. **新颖性判断**：若数据库中存在但文献未讨论 → 潜在 Gap；若数据库缺失 → 潜在新材料发现
5. **证据链记录**：记录每个结论的数据库来源、查询参数、DOI

### 7.3 验证指标示例

- 生成能一致性、带隙区间重叠度
- 热力学稳定性排序（hull 距离）
- 相图预测与实验相图对比

## 8. 扩展数据源

| 数据源 | 内容 | 用途 |
|--------|------|------|
| Alexandria | 大尺度计算材料数据 | 构效关系补充 |
| COD | 晶体学开放数据库 | 结构验证 |
| C2DB | 二维材料数据库 | 2D 材料研究 |
| Materials Cloud Archive | 计算数据归档 | 数据复现 |
| MaterialsGalaxy | 材料数据聚合 | 综合查询 |
| MatRouter | 本地优先 MCP server，聚合 MP/AFLOW/OQMD/NOMAD 等 | Agent 化材料数据路由 |

---

> 相关文档：[[文献数据资源]]、[[路线A·构效关系发现]]、[[工具链]]

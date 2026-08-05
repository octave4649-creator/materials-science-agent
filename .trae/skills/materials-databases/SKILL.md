---
name: "materials-databases"
description: "提供材料科学数据库的接入与交叉验证方法：Materials Project、OQMD、NOMAD、AFLOW、JARVIS 的数据内容、API 用法与构效关系验证流程。当需要查询材料性质、做数据库交叉验证、区分新知与已知时调用。"
---

# 材料数据库接入与交叉验证

## 1. 数据库总览

| 数据库 | 规模 | 强项 | 访问 |
|--------|------|------|------|
| Materials Project | 14 万+ 材料 | 带隙/生成能/能带/相图 | `mp-api` + `MPRester`，Key 存 `MP_API_KEY` |
| OQMD | 100 万+ 材料 | 热力学稳定性/相图 | 开放 REST API |
| NOMAD | 海量计算数据 | 原始数据可复现（OPTIMADE） | 网页 + API |
| AFLOW | 350 万+ 结构 | 晶体对称/原型分类 | REST API |
| JARVIS-DFT | 4 万+ 材料 | 光学性质/2D 材料 | `jarvis-tools` |

**选型**：构效关系→MP+OQMD；晶体对称→AFLOW；高精度→NOMAD；光电/2D→JARVIS。

## 2. Materials Project 用法

```python
from mp_api.client import MPRester

with MPRester("your_mp_api_key") as mpr:
    # 按元素+性质区间过滤
    docs = mpr.materials.summary.search(
        elements=["Si", "O"],
        band_gap=(0.5, 1.0),
        fields=["material_id", "band_gap", "formation_energy_per_atom"]
    )
```

关键字段：`material_id`、`band_gap`、`is_metal`、`is_stable`、`formation_energy_per_atom`、`energy_above_hull`、`symmetry`。

## 3. 交叉验证流程（路线 A 核心）

```
文献知识抽取 → 数据库查询 → 一致性检查 → 新颖性判断 → 证据链记录
```

- 库中有、文献未讨论 → 潜在 Gap
- 库中缺失 → 潜在新材料发现
- 指标：生成能一致性、带隙区间重叠度、hull 距离、相图对比

## 4. 使用纪律

- Key 走环境变量，禁止硬编码
- 查询结果缓存到本地（标注抓取时间）
- 遵守各库使用条款并注明出处
- 批量查询注意 API 限额，分片 + 限速

---

> 详细见 `.trae/rules/03-materials-databases.md`。

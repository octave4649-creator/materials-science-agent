# 数据登记

> 依据 `.trae/rules/00-project-rules.md` 5.4「数据与授权」：所有外部数据在此登记来源、授权、版本、获取时间。

| 数据 | 来源 | 授权协议 | 版本 | 获取时间 | 存放位置 |
|------|------|---------|------|---------|---------|
| Sci-Base（material 子集） | HuggingFace `opendatalab/Sci-Base` | CC-BY-4.0 | 2026 更新版 | 未拉取（网络受限，走离线聚合） | `data/cache/scibase/`（构建产物） |
| Sciverse 检索产物 | Sciverse API（`SCIVERSE_API_TOKEN`） | 检索 API 条款 | API 实时 | 2026-08-04 起 | `results/retrieval_*.json`（语料源） |
| WAYB/WAYC 酵母蛋白质组学 | 赛事提供（生物材料管线） | 仅限本次参赛使用，禁止混入开源仓库 | 13,412 样本 | 2026-08-06 | `data/raw/`（本地） |
| OQMD 验证结果 | OQMD REST API（免 Key） | 开放学术使用 | 实时 | 2026-08-04 起 | `results/validation/`（缓存） |
| Materials Project 数据 | materialsproject.org（`MP_API_KEY`） | MP 使用条款 | 实时 | 2026-08-05 起 | `results/validation/`（缓存） |

## 使用约束

- `data/raw/`（WAYB/WAYC）仅限本地，**禁止**随仓库提交（数据协议限制）。
- 检索/验证缓存落 `data/cache/` 与 `results/`，均已加入 `.gitignore`，不入库。
- 引用 OQMD / Materials Project 数据须注明出处（实验报告已登记）。

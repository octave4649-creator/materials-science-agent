---
title: "开发经验记录（避免翻车）"
category: "rules"
tags: [经验, exp, 踩坑记录, Sciverse, 开发规范]
description: "各模块开发过程中积累的实测经验、踩坑与解决方案"
created: "2026-08-04"
updated: "2026-08-05"
status: "active"
version: "1.10"
---

# 开发经验记录（exp）

> 本文件记录开发过程中的实测经验与踩坑，新增经验按「日期 + 模块」追加，避免后续开发翻车。

## 2026-08-04 · 模块 1 文献检索 Agent

### 经验 1：sciverse CLI 不在 PATH，`python -m sciverse` 无效
- **现象**：`sciverse` 命令报 `The term 'sciverse' is not recognized`；`python -m sciverse` 报 `No module named sciverse.__main__`
- **原因**：CLI 未加入 PATH；sciverse 是包，没有 `__main__.py`
- **解决**：用完整路径调用 `C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\Scripts\sciverse.exe`；日常开发直接 `from sciverse import AgentToolsClient` 走 SDK
- **注意**：Windows 下 pip 安装的可执行脚本都在 `...\Scripts\`，找不到命令先查该目录

### 经验 2：token 变量名是 SCIVERSE_API_TOKEN，且凭据文件可兜底
- **现象**：CLI `auth login --token` 能用，但 SDK 报「未配置 Sciverse token」
- **原因**：SDK 环境变量名为 `SCIVERSE_API_TOKEN`（技能文档写的是 SCIVERSE_API_KEY）；`auth login` 凭据保存在 `~/.sciverse/credentials.json`（权限 0600），代码未读取
- **解决**：`src/common/config.py` 的 `sciverse_token()` 读取顺序：`SCIVERSE_API_TOKEN` → `SCIVERSE_API_KEY` → `~/.sciverse/credentials.json` 兜底
- **注意**：`auth login --token` 对非 `sv-` 开头的 token 会警告但保存成功，可忽略

### 经验 3：scripts 直接运行报 ModuleNotFoundError
- **现象**：`python scripts/run_retrieval.py` 报 `No module named 'src'`
- **原因**：直接运行脚本时项目根不在 `sys.path`
- **解决**：脚本顶部 `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`；pytest 在 pyproject 配 `pythonpath=["."]`

### 经验 4：Sciverse 两通道返回结构不同，需归一化
- **现象**：`semantic_search` 返回 `hits[]`（含 chunk 证据片段、page_no、score、doc_id）；`search_papers` 返回 `results[]`（含 unique_id、doi、citation_count、isbn13 等元数据）
- **关键语义**：`unique_id` 是元数据全局 ID（无全文也有，如 `ebook:9781394317356`）；`doc_id` 是全文内容 sha256 哈希（仅全文存在时返回）
- **解决**：封装层归一化 `_hit_to_paper` / `_result_to_paper`；去重键三级策略：`doc_id` → `unique_id` → 归一化标题（清 HTML 标签 + 小写 + 合并空白）

### 经验 5：ruff 行长限制 100，logger 长调用易触发 E501
- **现象**：`ruff check` 报 E501 Line too long（104/102 > 100）
- **原因**：`logger.log(...)` 单行过长
- **解决**：长调用换行格式化；提交前 `ruff check` 零 error 是门禁

### 经验 6：pytest 临时目录传 Path 而非 str
- **现象**：`tempfile.mkdtemp()` 返回 str，直接当 Path 用报 `AttributeError: 'str' object has no attribute 'mkdir'`
- **解决**：`Path(tempfile.mkdtemp())` 转换后传入

### 经验 7：Sciverse 调用要做缓存与错误收敛
- **实测**：`data/cache/` 落盘 `search_papers_*.json`、`semantic_search_*.json`，缓存键 = 方法名 + 参数 sha256，避免重复调用消耗配额
- **降级**：语义通道 `SciverseError` 不中断流水线，降级走结构化通道并留痕（审计日志记录降级状态）

## 2026-08-04 · 模块 2 知识抽取 Agent

### 经验 8：pip/python 环境不一致，Python 3.14 无 mineru wheel
- **现象**：`pip install mineru` 装到 miniconda 但主环境 python 是 3.14，报无匹配 wheel
- **原因**：mineru 官方支持 ≤3.13；主环境与 pip 指向的环境不一致
- **解决**：确认 miniconda 3.13 已装 mineru 3.4.0；架构上将 MinerU 隔离为子进程调用，`MINERU_PYTHON` 环境变量指定解释器（默认 "python"）
- **注意**：先 `pip --version` + `python --version` 确认环境对应关系，再决定装包还是子进程隔离

### 经验 9：mineru 3.4.0 CLI 语法与文档不一致 + `python -m mineru` 不可用
- **现象**：按文档 `mineru parse -i paper.pdf -o out --format markdown` 报 `Missing option '-p' / '--path'`；`python -m mineru` 报 `No module named mineru.__main__`
- **解决**：实测语法为 `mineru -p <path> -o <out> -b <backend>`，`-p/-o` 必填、无 `--format`（默认输出 markdown）；默认 backend 是 hybrid-engine（需 GPU），无 GPU 用 `-b pipeline`（纯 CPU 16GB 可跑）；mineru 是包非 `__main__`，需调用 `Scripts\mineru(.exe)` 可执行文件
- **注意**：CLI 版本差异大，封装层先用 `mineru --help` 实测；`_mineru_exe()` 探测 `python_bin` 同环境 `Scripts\mineru.exe` → `Scripts\mineru` → PATH 兜底
- **补充**：pipeline 后端缺 `shapely` 等 CV 依赖会报 `No module named 'shapely'`，需补装；transformers 5.x 过新会报 `cannot import name 'find_pruneable_heads_and_indices' from 'transformers.pytorch_utils'`，需降级 `transformers<5`（本机实测装到 4.57.6 后 pipeline 可用）

### 经验 10：正则捕获组 `[\d.]+` 会匹配孤立点导致 float() 崩溃
- **现象**：端到端抽取 `ValueError: could not convert string to float: '.'`
- **原因**：`_ZT_RE`/`_GAP_RE` 捕获组 `[\d.]+` 匹配到孤立 `.`
- **解决**：捕获组改 `(\d+(?:\.\d+)?)`，保证至少一个数字
- **注意**：凡 `float()`/`int()` 转换的捕获组，模式必须保证至少一个数字

### 经验 11：化学式归一化要做元素符号校验，防单位误提取
- **现象**：知识库出现 `Wm` 条目（来自 `0.42\mathrm{Wm}^{-1}\mathrm{K}^{-1}` 热导率单位）
- **解决**：`_is_valid_formula` 段式解析（`[A-Z][a-z]?\d*`）+ 118 元素符号集合校验（至少 2 段）；`re.search` 只返回第一个匹配位置，须用 `finditer` 遍历全部候选跳过非法项（否则单位出现在真实化学式之前就抓错）
- **注意**：规则式降级的噪声会直接污染知识库 → 下游 Gap 识别，必须过滤

### 经验 12：AuditLogger.step yield 的是 None，不能 `as log` 赋值
- **现象**：`with self.logger.step(...) as log:` 想写 output_summary，但 log 是 None
- **解决**：`with self.logger.step(...):` 内部用 `self.logger.log("xxx_done", ...)` 记录结果；先读 `src/common/logging.py` 接口再使用

### 经验 13：LLM 输出解析要注入权威来源，不信任模型编造
- **现象**：LLM 可能编造 DOI/页码
- **解决**：`_parse_llm_output` 用 `raw["source"] = {doi, page, doc_id}` 覆盖为检索阶段注入的权威来源；pydantic schema 校验 + 化学式回查原文（归一化后子串匹配）
- **注意**：防幻觉三件套 = schema 约束 + 原文回查 + 证据链接（00-project-rules.md 4.1）

### 经验 14：chunk 证据片段可直接作为抽取输入，与 MinerU 解耦
- **现象**：模块 1 输出 `papers[].chunk`（agentic-search 证据片段）已含 LaTeX 化学式/zT/温度
- **解决**：抽取 Agent 主线用 chunk 证据，MinerU 只用于非 OA/本地 PDF 增强
- **注意**：流水线验收不阻塞在 MinerU 上；知识库 JSON 落库时 `evidence_ids` 回链 doc_id 保证可审计

## 2026-08-04 · 模块 3 Gap 识别 Agent

### 经验 15：LLM 配置在用户级环境变量，旧终端不生效
- **现象**：`setx`/用户级 `LLM_API_KEY` 配置后，已有终端仍报「未配置 LLM API Key」
- **原因**：进程环境变量在启动时快照，新设置不向已开终端传播
- **解决**：新建终端验证，或命令内临时注入 `$env:LLM_API_KEY = [Environment]::GetEnvironmentVariable('LLM_API_KEY','User')`
- **注意**：部署/复现文档要写明「需重启终端或新开终端」；`python -c` 内联 JSON 会被 PowerShell 拆坏（`{"ok": true}`），改用脚本文件验证

### 经验 16：LLM 生成的 Gap 证据必须回映射，不信任模型编造 doc_id
- **现象**：LLM 可能编造材料/证据，直接落库会污染 Gap 清单
- **解决**：Prompt 要求 LLM 输出 `kb_entry_ids`（知识库条目编号），`_parse_llm_gaps` 按编号取真实 `evidence_ids` 注入；formula 必须命中知识库已有归一化化学式，无证据的 Gap 直接丢弃（证据链红线）
- **注意**：pydantic `model_validate` 默认忽略未知字段，`kb_entry_ids` 不会破坏 schema 校验

### 经验 17：新颖性判定是启发式，必须标注「需人工复核」
- **现象**：Sciverse 回查用「top5 片段含主化学式命中数」判新知/已知，但化学式在 chunk 中未必逐字出现（LaTeX/缩写），误判风险高
- **解决**：判定结果写入 `verification` 字段并注明「仅供参考，需人工复核」；Sciverse 失败降级为默认新颖性并留痕
- **注意**：赛题评估要点「新颖性准确率」最终靠人工标注小集评测（t7），不把自动判定当结论

### 经验 18：Gap 输出文件路径要可配置，避免测试污染 data 目录
- **现象**：GapAgent 默认落盘 `data/gaps.json`，单测运行会写入真实数据目录
- **解决**：`__init__` 增加 `output_path` 参数（默认 DEFAULT_GAP_PATH），测试传 tmp_path
- **注意**：凡是 Agent 有落盘副作用，测试都要注入输出路径

## 2026-08-04 · 模块 4 报告生成 Agent

### 经验 19：报告自检用「统计行首编号」而非子串计数
- **现象**：`self_check` 的 `references_complete` 用 `content.count("\n[")` 统计参考文献，计数恒为引用数 - 1（首行无前导换行），n>1 时恒 False；单测 `test_self_check_all_pass` 捕获
- **解决**：`re.findall(r"^\[\d+\]", content, re.MULTILINE)` 统计行首 `[n]`
- **注意**：自检逻辑必须配「全通过」单测，否则自检项形同虚设

### 经验 20：取 JSON 字段用 `.get()` 容错，字段名以落盘结构为准
- **现象**：`_gap_statements` 用 `g['type']` 取 Gap 类型，KeyError（gaps.json 实际字段名是 `gap_type`）
- **解决**：统一 `g.get('gap_type', '未知')`；跨模块读字段先看上游落盘 JSON 的真实键名（schema.py 的 Field 名）
- **注意**：模块间契约以「落盘文件」为准，不以「思维中的名字」为准

### 经验 21：LLM 环境变量扩展后，所有测试 fixture 必须同步清空新变量
- **现象**：llm.py 新增 `DEEPSEEK_API_KEY` 兼容后，单测被真实环境 key 污染——`test_llm_available_false_without_key` 返回 True、抽取测试真调网络 401
- **解决**：4 个测试文件的 `_no_llm` fixture 全部补 `monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)`
- **注意**：凡新增「密钥/端点类」环境变量识别，先 grep `delenv` 全局排查测试 fixture

### 经验 22：LLM 凭据 401 属用户侧问题，代码侧验证降级路径即可
- **现象**：真实 `DEEPSEEK_API_KEY` 调 DeepSeek 端点返回 401（凭据失效），非代码 bug
- **解决**：不改代码、不硬编码 key；跑一次带 LLM 的完整流程验证「识别 LLM → 调用失败 → 降级规则摘要 → 流水线不中断 → 审计留痕」闭环
- **注意**：凭据失效要主动告知用户更新；报告摘要来源字段（`llm_abstract`）天然标记了降级，可作评测留痕

### 经验 23：模板生成的报告要做「可读性自检」5 连查
- **现象**：首版报告出现空检索时间、子查询未缩进、`et al.` 双句号、同名期刊分两组、标题残留 HTML 标签
- **解决**：逐一修复——时间字段三级 fallback（generated_at → ts → 当前 UTC）；列表二级缩进；`fmt()` 末尾判 `.` 防双句号；期刊分组键小写归一化；标题展示前过 `_plain_text()` 去 HTML 标签
- **注意**：生成式报告交付前必须人工过一遍 md 成品，模板瑕疵一次改到位，别等评测才发现

## 2026-08-05 · 模块 5 路线 A 搜索融合（GA × LLM 三角色）

### 经验 24：统一 LLM 封装调用契约，三位置 dict 与关键字参数都要兼容
- **现象**：`llm_chat_json` 签名是 `(system, user, *, max_tokens, temperature)`，但 LLMRoles 按 `(system, user, {"max_tokens": N, "temperature": T})` 三位置调用 → 每次抛 TypeError，llm_failures=11 而直接调用成功，极难排查（「LLM 可用但全失败」）
- **解决**：`llm_chat_json` 增加第三位置参数 `params: dict[str, Any] | None = None`，`if params: max_tokens = int(params.get("max_tokens", max_tokens))`；tests/test_llm.py 新增 `test_chat_json_params_dict_contract` mock httpx.post 验证两种调用约定，防回归
- **注意**：公共函数被多模块调用时，调用约定要写进 docstring；跨模块新调用方先查契约再写代码

### 经验 25：名义化学式拼接前先判断母体是否「纯二元」，否则产生垃圾公式
- **现象**：母体是已掺杂公式 `Ge0.93Ti0.01Bi0.06Te`，`host.split('Te')[0]` 把已有数字下标拼进新公式 → `Ge0.93Ti0.01Bi0.060.96Ti0.04Te`
- **解决**：`_nominal_formula` 仅对「以 Te 结尾且前部无数字」的纯二元母体生成 `A(1-x)D(x)Te`，复杂母体回退 `host-Dx%` 命名
- **注意**：凡基于字符串 split 拼接化学式，先断言输入形态（是否含数字下标），再决定拼接规则

### 经验 26：LLM 三角色必须设计「失败自动降级」兜底，流水线不中断
- **现象**：真实 LLM 调用有失败率（超时/解析失败），若任一角色抛异常会中断整个搜索
- **解决**：LLMRoles 的 generate_seeds/evaluate/prune 内部 try/except，失败返回 None；ga_search 检测 None 自动降级为规则评估（`rule_score` 化学启发式）+ SearchLog 记录降级原因
- **注意**：LLM 失败数量（llm_failures）本身是审计指标，可量化「LLM 可用性」，写入消融报告

### 经验 27：测试 fake LLM 按 system 内容分发角色，且键必须与真实公式一致
- **现象**：`_fake_chat` 生成器分发条件失效（scores 为空）；evaluate 返回的 formula 键 `"PbTe-Ti6%"` 与 `_nominal_formula` 产物 `"Pb0.94Ti0.06Te"` 不匹配，评估结果写不进候选
- **解决**：分发条件用 `"candidates" in system and "打分" not in system and "剪枝" not in system`；测试键用真实名义公式（`Pb0.94Ti0.06Te`）
- **注意**：测试替身的「数据形状」必须与真实代码输出一致，否则测试通过也无意义（测的是假逻辑）

## 2026-08-05 · 模块 6 数据库交叉验证（OQMD / MP）

### 经验 28：OQMD 免 Key REST 可用，但分数掺杂成分查询会超时
- **现象**：`Pb0.94Ti0.06Te`、`Ge0.96Ti0.04Te` 等分数成分查 `https://oqmd.org/oqmdapi/formationenergy` 长时间无响应；整数成分（GeTe/Bi2Te3）秒回
- **解决**：`_FRACTION_RE = re.compile(r"\d\.\d")` 检测含小数成分直接跳过（返回空 → 判定「验证失败」并明确标注），仅整数成分直查；掺杂扩展用 novel_dopant 标记而非直查
- **注意**：数据库查询要设「查询形状 guard」（分数成分跳过），比超时重试更高效；「验证失败」是诚实结论，不伪装成新知/反例

### 经验 29：OQMD 必须用 https + follow_redirects，http 会 301
- **现象**：`http://oqmd.org/oqmdapi/...` 报 301 Moved Permanently
- **解决**：基址改 `https://oqmd.org`，httpx 请求加 `follow_redirects=True`；网络调用统一 try/except 兜底（网络错误 → 返回空列表 → Agent 层判定验证失败留痕）
- **注意**：免 Key API 也可能重定向/限流，封装层要「失败可降级」且不向调用方抛裸异常

### 经验 30：Agent 的第三方依赖（数据库客户端）要注入可 mock，CI 不依赖网络
- **现象**：验证 Agent 若直接 import OQMDClient 真实查询，单测会真打网络，CI 不可复现
- **解决**：`ValidationAgent.__init__(oqmd: OQMDClient)` 依赖注入；测试用 `_fake_oqmd(best)` 按 composition 返回固定 best_entry；数据库客户端测试用 mock httpx.get
- **注意**：凡「外部依赖」一律注入；单测全 mock 保证 CI 确定性（00-project-rules.md 3.4）

### 经验 31：pip 与 python 可能指向不同环境，装依赖前先核对（模块 6 MP 路径）
- **现象**：`pip install mp-api pymatgen` 报告 Successfully installed（实际装进 miniconda3），但 `python -c "import mp_api"` 报 ModuleNotFoundError → `mp_available()` 恒 False，且 `pip show mp-api` 显示已安装，极具迷惑性
- **根因**：本机 `pip` 指向 miniconda3\Scripts\pip.exe，而 `python` 指向 pythoncore-3.14-64（PATH 顺序导致两者不一致）
- **解决**：装依赖统一用 `python -m pip install <pkg>`（保证与 `python` 同环境）；排查「装了却 import 不到」先核对 `python -c "import sys; print(sys.executable)"` 与 `(Get-Command pip).Source`
- **注意**：凡出现「pip 装成功但 import 失败」，第一怀疑就是双环境；pyproject `validation` extra 已声明 mp-api/pymatgen 版本约束，复现文档须写明 `python -m pip install -e ".[validation]"`

### 经验 32：MP 与 OQMD 对同一材料稳定性判定可能分歧，属科学事实不是 bug（模块 6）
- **现象**：GeTe 在 OQMD 稳定（hull=0.002）但 MP 中 mp-1080459 不稳定（hull=0.028）——两库竞争相集合/DFT 设置不同
- **处理**：判定以主库（OQMD）为准并 append 另一库条目留痕，分歧写进 reason/注释而非抹平；「数据库间分歧」本身是可写进报告的交叉验证素材
- **注意**：跨库验证天然会有分歧，不要「取平均」抹掉证据；分歧要显式记录（两库的 hull 值、来源 URL、查询时间）

## 2026-08-05 · 二次深度开发（初赛材料 / 批量验证 / 消融 / MCTS·BO·SR）

### 经验 33：DeepSeek json_object 模式要求 prompt 含「json」字样，否则 400（贯穿全模块）
- **现象**：key 修复后仍 `Client error '400 Bad Request'`——payload 含 `response_format: {"type": "json_object"}`，但 system/user prompt 无 "json" 字样
- **根因**：DeepSeek 的 json_object 模式触发条件 = prompt/schema 里必须出现 "json" 字面量（OpenAI 无此限制）
- **解决**：system prompt 加「严格输出 JSON 对象：{...}」；既有 ga_search/expand_gaps 提示词已含 "JSON" 不用改；新增 LLM 调用先检查 prompt 是否含 "json"
- **注意**：LLM 报错排查顺序——401 先查 key，400 再查 payload 格式（json 字样/参数名），403 查权限；用临时脚本隔离验证，别在大流程里反复试

### 经验 34：真实证据不足时，Gap 清单用「策展 + LLM 扩展 + 去重」分层补齐（模块 3 扩展）
- **现象**：知识库仅 5 条证据，覆盖率分析只能产出 1 条 Gap，撑不起 20+ 候选批量验证
- **解决**：`expand_gaps.py` 三层策略——① 策展 16 条（域内可证伪陈述，source=curated，公开文献共识）② LLM 推理 8-12 条（基于知识库摘要 + 既有 Gap，source=llm，失败降级跳过）③ 语句归一化去重（去空白/标点/小写）合并，schema 校验后落盘 → 29 条（新知 15 / 部分已知 14）
- **注意**：扩充的 Gap 必须「域内可证伪 + 可操作」，source 字段区分产生方式，复赛报告要交代哪些是策展假设哪些来自真实证据链，避免被质疑编造

### 经验 35：批量搜索/验证用「offset 分批 + 断点续跑」，避免长任务一次性超时（模块 5/6）
- **现象**：29 条 Gap 一次性跑 GA 搜索 + OQMD 验证，单条网络调用有超时风险，中断即重跑
- **解决**：`SearchAgent.run(offset=N)` + `run_search.py --offset` 切片 `gaps[offset:offset+top_n]`；`run_validation.py` 逐 finding 独立落盘 `validation_{ts}_{i}.json`，失败单条不影响整体
- **注意**：批量任务默认「每输入一条产一个独立输出文件」，天然支持断点续跑与增量审计

### 经验 36：三臂消融要保证公平性，负增益要科学解读不掩盖（模块 5 阶段 4）
- **现象**：消融结果 full 0.806 / rule 0.820 / llm 0.473——LLM 融合增益 **-1.66%**（负值）
- **设计**：`rule` 臂显式走 `ga_search(llm_on=False)`（与 full 同种子/同评分），`llm` 臂隔离 GA 演化（一次生成+评估无演化）——三臂只有「LLM 参与」与「演化算子」两个变量，才可归因
- **解读**：负的 LLM 融合增益说明规则评分代理已覆盖多数科学直觉（promoting dopant + 浓度区间），LLM 增量在假设多样性（llm 臂 unique_dopants 更高）而非分数；GA 演化增益 +70.41% 是主收益
- **注意**：消融的诚实呈现比「看起来好」更重要（负结果也是科学素材，00-rules 7.3）；复赛改进方向 = 换更严苛评分代理（引入 OQMD 验证结果作真值）再重跑

### 经验 37：报告验证章节确定性汇总，验证失败/反例如实呈现，零编造（模块 4 对接）
- **现象**：34 个验证文件 / 182 候选，含 38 个「验证失败」与 10 个「反例」——不能只挑好看的写
- **解决**：`section_validation()` 用 Counter 统计判定分布 + 候选表（≤20 行）+ 判定口径说明；「母体在库且稳定→已知 / 在库不稳定→反例 / 不在库→新知 / 分数成分无法直查→验证失败」，全部可回溯 OQMD/MP 记录
- **注意**：报告组装延续「确定性 + 零编造」原则（findings 2），任何章节不做 LLM 整篇生成；验证失败项留作下一步「纯母体解析重验」的改进指标

### 经验 38：SR/BO 用纯 Python 最小二乘（正规方程 + 高斯消元），无第三方依赖可交付（模块 5）
- **现象**：项目红线「无第三方依赖（除 httpx/pydantic）」，gplearn/sklearn 不可用
- **解决**：`sr_search.py` 手写正规方程闭式解 `X^T X w = X^T y` + 高斯消元解线性方程组；`bo_search.py` 二次多项式代理复用同一 `_least_squares`；SR 输出显式公式 + R² + 最优浓度
- **注意**：数值稳定用小矩阵（次数 ≤3），正规方程对病态矩阵用高斯消元选主元兜底；SR 优先策略成立——显式公式直接支撑「科学意义」评分维度（可解释性）

### 经验 39：Section 顺序新增章节键后，测试断言与自检要同步适配（模块 4）
- **现象**：SECTION_ORDER 插入 validation 键后，`[s.key for s in doc.sections] == SECTION_ORDER` 类断言自动适配（遍历驱动），但 markdown 加粗导致断言 `"2 个"` 失败（实际 `"**2** 个"`）
- **解决**：断言先看实际渲染输出再写；`ReportAgent` 新增可选目录参数默认 None（测试隔离真实 results/），`run_report.py` 显式传默认值——「脚本显式、库默认惰性」避免测试依赖真实文件
- **注意**：凡「默认取真实 results/ 目录」的 Agent 参数，单测必须显式传 tmp_path 或默认 None，否则 CI/他人环境被本机产物污染

### 经验 40：验证 key 连通性时，max_tokens 截断导致的 JSON 解析失败不是 key 问题（模块 4）
- **现象**：注入新 `DEEPSEEK_API_KEY` 后最小连通性验证返回 `LLMError('LLM 输出非合法 JSON: {"answer": "..."')`，易被误判为「key 仍不可用」
- **根因**：`max_tokens=64` 太短，DeepSeek 返回被截断 → JSON 不完整 → 解析失败；**key 本身已连通**（有内容返回即证明鉴权通过）
- **解决**：连通性验证看两点即可——① 无 401/403（鉴权通过）② 返回体含模型输出文本；要测完整 JSON 解析则调大 `max_tokens`（≥256）
- **注意**：DeepSeek 报错排查顺序（经验 33）：401 查 key → 400 查 payload → **输出解析失败先查 max_tokens 是否截断**；摘要走规则式兜底时先查日志（`report_agent_*.jsonl` 的 `report_llm_abstract` 行 reason），确认是 401 旧 key 还是别的原因

## 2026-08-05 · 三次深度开发（初赛合规 / Oracle 严苛评分 / 验证失败重验 / 闭环回喂）

### 经验 41：初赛方案 docx 定稿用自写受控 Markdown 子集转换器，pandoc 不可用不阻塞（模块 4/提交）
- **现象**：pandoc 在 Windows 主环境不可用；python-docx 1.2.0 可用——方案 docx 定稿被转换工具卡住
- **解决**：`scripts/md_to_docx.py` 自写转换器，只支持受控子集（`#`~`######` 标题 / 表格 / `-*`与`1.` 列表 / `>` 引用 / ` ``` ` 代码块 / `**粗体**`与`` `行内代码` `` / 段落 / 分隔线），验证 12 标题 + 5 表格通过；表格用 `Light Grid Accent 1` 样式 + 表头粗体
- **注意**：提交类格式转换优先「受控子集 + 内部工具」，别为 pandoc 装大依赖；ruff 对 md_to_docx.py 的长条件行（E501）与尾随空格（W291）要全量检查，别只查单文件

### 经验 42：A/B 位拆分解析器是「验证失败→已知」的高性价比路径，解析失败保持如实标注（模块 6）
- **现象**：38 个「验证失败」全是分数掺杂成分（`Ge0.93Ti0.01Bi0.06Te` 类）OQMD 直查超时，判定覆盖率被卡死
- **解决**：`parent_parser.parse_integer_parent()` 从分数宿主拆整数母体——AX 型（阴离子下标 1、阳离子总数≈1）取主阳离子（下标占比最大者）→ `GeTe`；A2X3 型（阴离子下标 3、阳离子总数≈2）→ `Sb2Te3`；`_ANIONS` 白名单（Te/Se/S/As/P/Br/Cl/I/F/O/N）防误判；**解析失败返回 None，仍判「验证失败」如实标注，不伪装结论**；VerificationResult 新增 `parent_formula` 字段留痕
- **注意**：母体解析是「同一材料不同表示」的归一化问题——oracle 真值表（verification_oracle.py）host 表同步索引 `parent_formula`，真值覆盖 182→220 条；分数宿主「重验为已知」的同时保留原始宿主记录，验证失败 38→0

### 经验 43：搜索-验证闭环「反例提取 → 剪枝器回喂 → 审计留痕」是迭代搜索的骨架（模块 5/6）
- **现象**：10 个「反例」（母体在库但热力学不稳定）只在验证报告里躺着，搜索还在继续生成同母体候选
- **解决**：`feedback.py::extract_negative_hosts()` 从验证产物提取反例母体（SiGe/Cu2Se）→ `ga_search(..., negative_hosts)` 每代强制淘汰（`c.verdict="drop"`）+ `LLMRoles.prune` system/user 提示 LLM 优先淘汰，审计 `action="prune_feedback"` 留痕；`run_search.py` 默认加载、`--no-feedback` 关闭
- **注意**：闭环回喂要「双保险」——LLM 提示是引导、规则强制淘汰是兜底（LLM 可能不听话）；`extract_disputes()` 同步提取跨库分歧供相图核对，两类反馈各走各的通道

### 经验 44：消融负增益要归因到「评分真值覆盖」，不要直接断定「LLM 融合无用」（模块 5 阶段 4）
- **现象**：VerificationOracle（OQMD 验证真值作评分代理）重跑后 full 0.803 / rule 0.933 / llm 0.836，**LLM 融合增益 -13.98%、GA 演化增益 -3.97%**（规则评分时代 GA +70.41% 的主收益也转负）
- **根因**：rule 臂恒 0.933（GeTe/PbTe/Bi2Te3 命中已验证「已知」），full/llm 臂产出的新颖母体不在 oracle 真值表 → 分数被「未知」压低——**负增益是真值表覆盖不足，不是 LLM 无能**
- **解决**：验证失败重验（经验 42）扩大真值表后重跑 → GA 演化增益 +2.65% **由负转正**、LLM 融合增益 -8.93% 负值收窄；科学解读链条 = 真值表扩大 → 搜索多样性可被评分 → 融合增益回归
- **注意**：消融报告里负增益必须写明归因（00-rules 7.3 负结果同样记录）；「严苛评分代理」的定义本身就是复赛创新性素材——以数据库真值为锚、LLM 分数为预测，两者差异即 LLM 增量

### 经验 45：跨库分歧做「相图级核对」再归因，条目级亚稳相 ≠ 相图级不稳定（模块 6）
- **现象**：GeTe 在 OQMD 稳定（hull=0.002）但 MP 中 mp-1080459 不稳定（hull=0.028）——两库竞争相集合/DFT 设置不同，直接拿条目级 hull 对比会误判分歧
- **解决**：`check_mp_phase_diagram.py` 用 `MPRester.get_entries_in_chemsys(chemsys)` + `pymatgen.analysis.phase_diagram.PhaseDiagram` 算相图级 hull → **GeTe hull=0.0 稳定**（分解产物 GeTe 1.000 mol），分歧归因「条目级亚稳相 vs 相图级判定」粒度差异，分歧消除
- **注意**：跨库稳定性比较先确认「比较口径」——条目级（单一 mp-id）还是相图级（competition 相集合）；相图级才是热力学稳定性判定基准；分歧消除后要把核对结论（hull/分解产物/来源）写进报告作为交叉验证素材

### 经验 46：提交前 ruff 必须全量（src/tests/scripts），单文件检查会漏（贯穿全模块）
- **现象**：三轮深度开发后全量回归，`md_to_docx.py` 有 3 处 E501/W291（前几轮单文件检查没覆盖到 scripts/ 新文件）
- **解决**：收尾统一跑 `python -m ruff check src tests scripts`（+ `ruff format --check`），pytest 全量 `python -m pytest -q`
- **注意**：门禁 = ruff 全量零 error + pytest 全绿才允许更新计划/收工；新脚本文件（scripts/*.py）最容易漏检，纳入全量范围

## 2026-08-05 · 基本任务评测补强（字段级 F1 / Gap 新颖性复核 / 已知关系召回率）

### 经验 47：MCTS「文档声称三层决策树」与实现可能不一致，评测才能暴露（模块 5）
- **现象**：`mcts_search` docstring 写「host→dopant→concentration 三层决策树」，但 `is_leaf()` 在 `level>=2` 即返回 True、`_simulate()` 浓度固定 `CONC_GRID[2]=6.0`——浓度维度从未真正进入搜索，浓度≠6 的期望方案（已知关系召回率评测）恒 miss
- **根因**：早期实现为「host→dopant 两层 + 浓度后处理固定值」，docstring 提前宣告三层语义，代码未跟上；单测只测「输出非空」测不出维度缺失
- **解决**：`MCTSNode` 增加 `concentration` 字段 + `to_candidate()`；`_expand()` level 1 分支按 `8 dopant × 5 conc` 展开叶节点；`_simulate()` 返回 `(Candidate, score)`；新增回归单测「explore_top=8 时浓度集合 ≥2 个不同值」
- **注意**：**评测是架构声明的照妖镜**——召回率评测能定量证明「浓度是否可被搜索发现」；凡算法有「声称的能力」必须配「能证明该能力的评测/单测」，别只测 happy path

### 经验 48：召回率评测必须统一「探索轨迹」口径，否则 hit@3/5 对单候选算法失真（模块 5 评测）
- **现象**：旧口径下 MCTS/BO 的 `top_candidates` 仅 1 个候选 → hit@3/5 天然为 0（GA=0.2、其余全 0），评测反映的是「输出形态」而非「探索能力」
- **解决**：四算法统一增加 `explore_top: int = 0` 参数——>0 时 `top_candidates` 输出「搜索过程中评估过的候选全集（formula 去重、按评分降序）」前 explore_top 个；`eval_recall.py` 以 `explore_top=max(ks)` 调用；默认 0 保持原有 best 输出语义（API 兼容）
- **新口径结果**：ga recall@5=0.4 / mcts 0.2 / bo 0.0 / sr 0.2（对比旧口径仅 GA=0.2）——MCTS/SR 在 @3/@5 开始命中，BO 全 0 是其结构性局限（单 dopant 固定 + 仅浓度寻优，无法发现掺杂元素维度）
- **注意**：评测口径要先自问「指标要度量什么」——hit@k 度量的是「探索空间对期望方案的覆盖」就必须喂全探索轨迹；口径声明写进脚本 docstring，防止后人误解

### 经验 49：共享 SearchLog 会让单测 `steps[-1]` 指向后一次调用，断言失真（测试规范）
- **现象**：`test_mcts_explore_top_default_single_best` 中 single/multi 两次 `mcts_search` 共享同一 `LLMRoles(log=SearchLog())`，断言 `single.search_log.steps[-1].n_candidates == 1` 失败——steps[-1] 实际是 multi 的 done 记录（5）
- **根因**：SearchLog 是调用间共享的可变对象，第二次调用 append 后 `steps[-1]` 漂移；算法本身无 bug（top_candidates 长度断言通过）
- **解决**：单测为每次搜索创建独立 `LLMRoles(..., log=SearchLog())`，并注释说明原因；断言 `len(finding.top_candidates)` 与 log 步骤同时校验
- **注意**：凡被测对象内部有「追加式日志容器」且测试会多次调用，每次调用必须隔离实例；否则「测的是最后一次调用的副作用」

### 经验 50：Gap 新颖性人工复核要能「先回查后出清单」，让判定有真实检索证据可依（模块 3 评测）
- **现象**：默认复核清单 29 条 `verification` 全为 None → 启发式建议全「需人工确认」，人工复核无抓手，新颖性准确率评测无法推进
- **解决**：`scripts/review_gap_novelty.py` 增加 `--verify` 模式——逐条 `SciverseClient.semantic_search(query, top_k=5, mode="fast")`（查询 = 主化学式 + Gap 陈述，控 200 字符），命中判定与 `gap_agent._verify_novelty` 一致（≥2 已知 / =1 部分已知 / 0 新知），`verification` 写回 gaps.json + 生成清单；SciverseError 降级留痕不中断
- **实跑**：29/29 成功；启发式建议「新知 20 / 已知 9」vs 当前 novelty「部分已知 14 / 新知 15」——两者不一致条目（部分已知被回查判为 0/≥2 命中）是人工复核重点
- **注意**：人工复核工具默认给不出证据时，先提供「带检索证据的启发式建议」再让专家复核，比让专家从零判断高效；判定仍标注「仅供参考，需人工复核」不越权

### 经验 51：评测产出按「一次一文件 + 时间戳」落盘，新旧口径可对比（贯穿评测）
- **现象**：召回率评测重跑后 `results/eval/` 同时有 `recall_20260805T064338.json`（旧口径）与 `recall_20260805T070151.json`（新口径），天然形成「口径修正前后」对比证据
- **解决**：`scripts/eval_recall.py` / `eval_extraction_f1.py` 文件名带 `%Y%m%dT%H%M%S` 时间戳；不覆盖旧结果
- **注意**：评测文件保留历史版本 = 免费获得消融对比；复赛报告可直接引用「口径修正 → 指标提升」过程证明评测严谨性

## 2026-08-05 · 五次深度开发（BO 召回率增强 / known_facts 扩充 / LLM 模式召回率）

### 经验 52：二维期望方案的召回要靠「外层遍历维度 + 内层寻优」，固定某一维是结构性缺陷（模块 5）
- **现象**：known_facts 是 host + dopant + concentration 三维期望方案；BO v1 固定单 dopant（rng 选 1 个）只调浓度轴 → 掺杂元素维度永不可达，召回率恒 0
- **解决**：v2「dopant 外层遍历 × 浓度 BO 内层寻优」——每个候选掺杂元素独立跑浓度 BO（初始点全覆盖 + 二次代理 + UCB 采集），探索轨迹合并为 dopant × 浓度二维覆盖；`bo_search(dopants=None → DOPANT_POOL[:10])` 默认覆盖热电常见位点（含 Cd/Se），`dopants` 参数可限定搜索空间（评测控成本）
- **效果**：BO coverage 0 → **0.688**（四算法最高，GA 0.250 / MCTS 0.375 / SR 0.125）；新增单测 `test_bo_search_dopant_dimension`（explore_top=10 dopants_seen ≥2）防回归
- **注意**：期望方案有几个维度，搜索空间就要有几个「可被搜索发现」的维度；算法声称覆盖的维度必须有评测/单测证明（延续经验 47 的「评测是架构声明的照妖镜」）

### 经验 53：分数只存 single 字段会让「排序」静默退化为「插入序」，比没分数更隐蔽（模块 5）
- **现象**：规则分支 `cand.scores = {"scientific": round(score, 2)}` 丢弃 feasibility——rule_score 对同一 dopant 各浓度点返回相同 scientific（只随浓度区间分档），score_avg 全部相等 → 排序退化为评估插入序（先评估的 Ti 排前面），`test_bo_search_dopant_dimension` 前 10 全是 Ti
- **根因**：BO/MCTS 收敛路径依赖 `score_avg()` 区分候选优劣；丢弃 feasibility 后同 dopant 内部失去排序信息，表面「有分数」实则无区分度
- **解决**：规则分支统一 `cand.scores = sc`（scientific + feasibility 全保留，score_avg 含两者均值）；BO 与 MCTS 同步修复（mcts_search._simulate 同一 bug）
- **注意**：凡排序依赖 `score_avg()`，必须确认 scores dict 保存了「影响区分度的全部维度」；排序退化是隐蔽 bug（结果非错但质量崩塌），靠「断言 dopant 多样性」类单测才能暴露

### 经验 54：召回率双口径 hit@k（排序质量）× coverage（探索覆盖率）分离，量化评分-期望错配（模块 5 评测）
- **现象**：BO coverage 0.688 但 hit@3/hit@5=0.062——期望浓度 1-2 的方案被 rule_score 偏好浓度 3-8 的评分排到 top-k 之外，「探索到了但没排进前列」
- **设计**：`eval_recall.py` 双口径——hit@k 在「完整探索轨迹（explore_top=10000 去重、按评分降序）取前 k」判定（排序质量）；coverage 在完整轨迹全量判定（探索覆盖率）；两口径差异 = 评分偏好 vs 期望浓度错配的量化
- **注意**：coverage 是「搜索空间能力」指标、hit@k 是「推荐质量」指标，二者缺一不可；只报 hit@k 会低估搜索空间覆盖（BO v2 的改进在 coverage 上体现），只报 coverage 会掩盖评分器系统性偏差（下一步调 rule_score 浓度偏好或上 LLM 评估器）

### 经验 55：LLM 评估器是批量接口，单点调用会放大评测成本；评测要有预算参数（模块 5 评测）
- **现象**：BO LLM 模式 `_evaluate` 对每点调 `roles.evaluate([cand])` → 每元素 19 点 × 5 元素 × 16 条 known_facts ≈ 1500 次 LLM 调用（10 元素全量 3040 次），耗时不可接受
- **解决**：重构 `_evaluate_batch` 批量评估——LLM 模式一次 `roles.evaluate(cands)` 评估一批浓度点（候选缺失降级规则），每元素调用 19→4 次；`eval_recall.py` 新增 `--bo-dopants` 预算参数（LLM 模式 5 控成本），规则模式 sanity 验证行为不变
- **注意**：LLM 模式评测前先估算调用规模（调用次数 = 采样点数 × 元素数 × 期望集条数），评估器接口支持批量就批量用；批量评估的降级语义与单点一致（formula 未返回 → 规则兜底）

### 经验 56：单次 LLM 秒级 ≠ 评测总时长秒级；长评测必须预估调用数并输出进度（模块 5 评测）
- **现象**：`eval_recall.py --llm` 全量跑 20+ 分钟无任何输出，用户反馈「外接大模型应秒级响应，肯定代码有问题」
- **排查**：实测单次调用 2.7s（3 候选批量）/ 8.2s（10 候选批量），返回正常——代码无死锁；真因是评测脚本把「known_facts × dopant 池 × 每元素批次」循环放大到 320 次调用（16 条 × 5 元素 × 4 批），且脚本只在全部结束后 print，期间零输出造成「卡死」误判
- **解决**：① `--max-facts` 子集参数（跑通验证用 1 条，单次正常搜索量级 = 1 fact × 5 元素 × 4 批 = 20 次评估 ≈ 90s）；② LLM 模式逐条进度打印（fact id + 算法 + 耗时 + 命中），防误判
- **注意**：单次 BO 搜索 20 次 LLM 评估是「正常用量」，评测循环放大才是长尾；面向用户的运行时长认知 = 调用数 × 单次耗时，预估后决定全量还是子集；任何 >1 分钟的评测命令都要先给进度输出

## 通用约定

- 证据链是赛题红线：每个结论必须关联 EvidenceChain（source/doc_id/page/text/score/fetched_at）
- 所有网络/API 调用 try/except + 可读错误 + 降级策略，禁止裸 `except: pass`
- 审计日志：AuditLogger 追加式 JSONL 写 `results/logs/{agent}_{YYYYMMDD}.jsonl`
- 配置与密钥走环境变量或凭据文件，禁止硬编码入库；`.env`、`*.key`、credentials.json 加入 `.gitignore`

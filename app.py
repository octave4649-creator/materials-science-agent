"""材料科学文献驱动的科学发现智能体 — 本地 Web 演示（Streamlit）。

聚合展示项目各模块成果（知识抽取 / Gap 识别 / 路线A搜索 / 数据库交叉验证 /
评测指标 / 调研报告），并支持交互执行路线 A 搜索（规则模式默认，快；LLM 模式可选）。

设计语言：商务蓝白极简风（参考微信原生设计语言的克制、
Apple Health 的卡片式信息层级与 Notion 的留白排版美学）。

启动:
    streamlit run app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
EVAL_DIR = RESULTS_DIR / "eval"
FINDINGS_DIR = RESULTS_DIR / "findings"
VALIDATION_DIR = RESULTS_DIR / "validation"
REPORTS_DIR = RESULTS_DIR / "reports"

st.set_page_config(
    page_title="材料科学文献智能体",
    page_icon=":material/science:",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------- 全局样式 ----------

_PRIMARY = "#1A5F9E"
_BG = "#F7F9FC"
_TEXT = "#1F2D3D"
_MUTED = "#8C9AA8"
_GREEN = "#4ECDC4"
_ORANGE = "#FF8C42"
_RADIUS = "12px"
_SHADOW = "0 4px 20px rgba(26,95,158,0.08)"
_BORDER = "#E3EBF3"

_CSS = f"""
<style>
/* ---------- 基础 ---------- */
html, body, [class*="css"] {{
    font-family: "PingFang SC", "Microsoft YaHei", "Source Han Sans SC",
                 "Helvetica Neue", sans-serif;
    color: {_TEXT};
}}
.stApp {{ background: {_BG}; }}
/* 顶栏：取消装饰带占用，让导航区有足够视觉空间 */
[data-testid="stDecoration"] {{ display: none; height: 0 !important; min-height: 0 !important; }}
[data-testid="stAppViewBlockContainer"],
[data-testid="stMainBlockContainer"],
.block-container {{
    padding-top: 2.6rem;
    padding-bottom: 3rem;
    max-width: 1440px;
}}
/* 隐藏 Streamlit 默认工具条 / 菜单 */
#MainMenu, footer {{ visibility: hidden; }}
[data-testid="stToolbar"] {{ display: none; }}
/* 侧边栏顶部：给标题留白，避免顶部分界不清 */
[data-testid="stSidebarHeader"] {{ min-height: 0 !important; }}

/* ---------- 标题层级 ---------- */
h1, h2, h3 {{ color: {_TEXT}; letter-spacing: 0.2px; }}
h1 {{ font-size: 24px; font-weight: 700; }}
h2 {{ font-size: 18px; font-weight: 700; }}
h3 {{ font-size: 16px; font-weight: 600; }}
p, li {{ font-size: 14px; line-height: 1.7; }}

/* ---------- KPI 指标卡（Apple Health 卡片层级） ---------- */
[data-testid="stMetric"] {{
    background: #FFFFFF;
    border: 1px solid {_BORDER};
    border-radius: {_RADIUS};
    box-shadow: {_SHADOW};
    padding: 16px 20px;
}}
[data-testid="stMetricLabel"] {{
    color: {_MUTED};
    font-size: 12px;
    font-weight: 500;
}}
[data-testid="stMetricValue"] {{
    color: {_PRIMARY};
    font-size: 26px;
    font-weight: 700;
    line-height: 1.3;
}}
[data-testid="stMetricDelta"] {{ color: {_MUTED}; font-size: 12px; }}

/* ---------- 侧边栏 ---------- */
[data-testid="stSidebar"] {{
    background: #FFFFFF;
    border-right: 1px solid {_BORDER};
}}
[data-testid="stSidebar"] .block-container {{ padding-top: 1.4rem; }}

/* ---------- Tab（顶部导航栏） ---------- */
[data-testid="stTabs"] {{
    position: relative;
    padding-bottom: 10px;
}}
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    gap: 6px;
    background: #FFFFFF;
    border: 1px solid {_BORDER};
    border-radius: {_RADIUS};
    box-shadow: {_SHADOW};
    padding: 8px 10px;
    min-height: 52px;
    align-items: center;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    border-radius: 8px;
    font-size: 14px;
    padding: 8px 20px;
    min-height: 36px;
    min-width: auto;
    color: {_MUTED};
}}
/* 选中态：深海蓝字 + 冰川白浅背景 */
[data-testid="stTabs"] [data-baseweb="tab-list"] [aria-selected="true"] {{
    color: {_PRIMARY};
    font-weight: 600;
    background: rgba(26, 95, 158, 0.08);
}}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {{
    color: {_PRIMARY};
}}
/* 保证 Tab 内 markdown 容器 / p / div 文字正常不塌陷 */
[data-testid="stTabs"] [data-baseweb="tab"] div,
[data-testid="stTabs"] [data-baseweb="tab"] p {{
    color: inherit !important;
    font-size: inherit !important;
    line-height: 1.5 !important;
    margin: 0 !important;
    padding: 0 !important;
    display: block !important;
}}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
    display: none; /* 隐藏默认底部蓝色细线，改用卡片背景 */
}}

/* ---------- 容器 / 展开器 / 表格 ---------- */
[data-testid="stExpander"] {{
    background: #FFFFFF;
    border: 1px solid {_BORDER};
    border-radius: {_RADIUS};
    box-shadow: {_SHADOW};
}}
[data-testid="stExpander"] summary {{ font-size: 14px; font-weight: 600; color: {_PRIMARY}; }}
[data-testid="stDataFrame"] {{
    background: #FFFFFF;
    border: 1px solid {_BORDER};
    border-radius: {_RADIUS};
    overflow: hidden;
    box-shadow: {_SHADOW};
}}

/* ---------- 按钮 / 输入控件 ---------- */
.stButton > button, .stFormSubmitButton > button {{
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
}}
.stButton > button[kind="primary"] {{ background: {_PRIMARY}; }}
[data-baseweb="select"] > div, [data-baseweb="input"] > div {{
    border-radius: 8px;
}}
[data-testid="stSlider"] {{ padding-top: 6px; }}

/* ---------- 信息提示条 ---------- */
[data-testid="stInfo"], [data-testid="stWarning"], [data-testid="stError"] {{
    border-radius: {_RADIUS};
    font-size: 14px;
}}
[data-testid="stInfo"] {{ background: rgba(26, 95, 158, 0.06); border: 1px solid {_BORDER}; }}
[data-testid="stWarning"] {{ background: rgba(255, 140, 66, 0.08); }}
[data-testid="stError"] {{ background: rgba(217, 83, 79, 0.08); }}

/* ---------- 自定义徽章 / 流程条 ---------- */
.ms-pill {{
    display: inline-block;
    padding: 2px 12px;
    border-radius: 999px;
    font-size: 12px;
    line-height: 22px;
    font-weight: 500;
    white-space: nowrap;
    vertical-align: middle;
}}
.ms-pill-blue   {{ color: {_PRIMARY}; background: rgba(26, 95, 158, 0.10); }}
.ms-pill-green  {{ color: #1B8C84;  background: rgba(78, 205, 196, 0.14); }}
.ms-pill-orange {{ color: #C76A1F;  background: rgba(255, 140, 66, 0.14); }}
.ms-pill-gray   {{ color: {_MUTED}; background: rgba(140, 154, 168, 0.12); }}
.ms-pill-red    {{ color: #C0392B;  background: rgba(217, 83, 79, 0.12); }}
.ms-arrow {{ color: #A9BDD2; font-weight: 600; padding: 0 6px; }}
.ms-card {{
    background: #FFFFFF;
    border: 1px solid {_BORDER};
    border-radius: {_RADIUS};
    box-shadow: {_SHADOW};
    padding: 18px 22px;
}}
.ms-card-title {{ font-size: 14px; font-weight: 700; color: {_TEXT}; margin-bottom: 10px; }}
.ms-stat-row {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 7px 0; border-bottom: 1px solid #EEF3F8; font-size: 14px;
}}
.ms-stat-row:last-child {{ border-bottom: none; }}
.ms-stat-name {{ color: {_TEXT}; }}
.ms-stat-num {{ color: {_PRIMARY}; font-weight: 700; font-size: 16px; }}
</style>
"""


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _pill(text: str, color: str = "blue") -> str:
    """生成徽章 HTML（蓝 / 绿 / 橙 / 灰 / 红 五态）。"""
    return f'<span class="ms-pill ms-pill-{color}">{text}</span>'


def _stat_card(title: str, items: list[tuple[str, int]]) -> None:
    """渲染统计卡：标题 + 名称/数量行（用于 Gap 分布等）。"""
    rows = "".join(
        '<div class="ms-stat-row">'
        f'<span class="ms-stat-name">{name}</span>'
        f'<span class="ms-stat-num">{n}</span></div>'
        for name, n in items
    )
    st.markdown(
        f'<div class="ms-card"><div class="ms-card-title">{title}</div>{rows}</div>',
        unsafe_allow_html=True,
    )


# ---------- 数据加载 ----------

def _load_json(path: Path, default=None):
    """读取 JSON 文件，缺失返回 default。"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _list_json(dir_path: Path, pattern: str) -> list[Path]:
    """列出目录下匹配的文件，按修改时间倒序。"""
    if not dir_path.exists():
        return []
    files = sorted(dir_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files


# ---------- 总览 ----------

_PIPELINE = ["文献检索", "知识抽取", "Gap 识别", "构效发现", "交叉验证", "调研报告"]


def render_overview() -> None:
    st.markdown(
        f"""
        <div style="padding: 6px 0 2px;">
          <div style="font-size: 26px; font-weight: 700; color: {_TEXT};
                      letter-spacing: 0.5px;">
            材料科学文献驱动的科学发现智能体
          </div>
          <div style="font-size: 14px; color: {_MUTED}; margin-top: 6px; line-height: 1.8;">
            面向赛道三·方向三：从文献出发 → 知识抽取 → Research Gap 识别 →
            搜索算法 × LLM 构效关系发现 → 数据库交叉验证 → 结构化调研报告。
            所有结论附带可审计证据链（来源 / DOI / 页码）。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pills = _pill(_PIPELINE[0], "blue")
    for step in _PIPELINE[1:]:
        pills += '<span class="ms-arrow">→</span>' + _pill(step, "blue")
    st.markdown(
        f'<div style="padding: 14px 0 4px;">{pills}</div>',
        unsafe_allow_html=True,
    )

    kb = _load_json(DATA_DIR / "knowledge_base.json", [])
    gaps = _load_json(DATA_DIR / "gaps.json", {})
    findings = _list_json(FINDINGS_DIR, "finding_*.json")
    validations = _list_json(VALIDATION_DIR, "validation_*.json")
    reports = _list_json(REPORTS_DIR, "report_*.md")
    evals = _list_json(EVAL_DIR, "*.json")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("知识抽取记录", len(kb))
    c2.metric("Research Gap", gaps.get("n_entries", 0))
    c3.metric("构效关系发现", len(findings))
    c4.metric("数据库验证", len(validations))
    c5.metric("调研报告", len(reports))
    c6.metric("评测产物", len(evals))

    if gaps.get("known_facts"):
        n = len(gaps["known_facts"])
        st.markdown(
            f'<div class="ms-card" style="margin-top: 14px;">'
            f'<span class="ms-pill ms-pill-green">评测期望集</span>'
            f'<span style="font-size: 14px; color: {_TEXT}; margin-left: 10px;">'
            f'<b>{n} 条</b>已知关系——人工策展的热电领域已报道掺杂构效关系，'
            '用于四算法召回率评测（hit@k 排序质量 + coverage 探索覆盖率）。'
            f'</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="color: {_MUTED}; font-size: 12px; margin-top: 16px;">'
        "模块导航：使用顶部 Tab 切换——知识库 / Gap 清单 / 路线A搜索 / "
        "数据库验证 / 评测指标 / 调研报告。"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------- 知识抽取 ----------

def render_knowledge_base() -> None:
    st.markdown(
        '<div class="ms-card"><div class="ms-card-title">知识抽取结果</div>'
        "<div style=\"font-size: 13px; color: #8C9AA8;\">"
        "字段对齐 04-literature-agent.md 知识抽取 Schema"
        "（成分 / 结构 / 性能 / 方法 / 合成条件）。"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.space("small")
    kb = _load_json(DATA_DIR / "knowledge_base.json", [])
    if not kb:
        st.warning("知识库为空，请先运行 scripts/run_extraction.py")
        return
    rows = []
    for item in kb:
        rec = item.get("record", item)
        mat = rec.get("material", {})
        props = rec.get("properties", []) or []
        prop_str = "; ".join(
            f"{p.get('name')}={p.get('value')}{p.get('unit') or ''}" for p in props
        )
        syn = rec.get("synthesis", {}) or {}
        src = rec.get("source", {}) or {}
        rows.append({
            "材料/公式": mat.get("formula", ""),
            "性能": prop_str,
            "合成条件": f"{syn.get('temperature') or '-'}°C, {syn.get('duration') or '-'}h",
            "方法数": len(rec.get("methods", []) or []),
            "来源": src.get("doi") or src.get("doc_id", "")[:12],
            "置信度": rec.get("confidence"),
        })
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(f"共 {len(rows)} 条抽取记录，每条附带证据链（doc_id 可回溯）。")


# ---------- Gap 识别 ----------

def render_gaps() -> None:
    st.markdown(
        '<div class="ms-card"><div class="ms-card-title">Research Gap 识别结果</div>'
        "<div style=\"font-size: 13px; color: #8C9AA8;\">"
        "基于检索证据的覆盖率分析 / 矛盾检测 / 连接发现，并回查 Sciverse 确认新颖性。"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.space("small")
    gaps = _load_json(DATA_DIR / "gaps.json", {})
    gap_list = gaps.get("gaps", [])
    if not gap_list:
        st.warning("Gap 清单为空，请先运行 scripts/run_gap.py")
        return
    type_cnt: dict[str, int] = {}
    novelty_cnt: dict[str, int] = {}
    for g in gap_list:
        gt = g.get("gap_type", "-")
        nv = g.get("novelty", "-")
        type_cnt[gt] = type_cnt.get(gt, 0) + 1
        novelty_cnt[nv] = novelty_cnt.get(nv, 0) + 1

    c1, c2 = st.columns(2)
    with c1:
        _stat_card("Gap 类型分布", list(type_cnt.items()))
    with c2:
        _stat_card("新颖性判定分布", list(novelty_cnt.items()))

    st.space("medium")
    st.markdown(
        '<div class="ms-card"><div class="ms-card-title">Gap 清单（前 50 条）</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    rows = [{
        "类型": g.get("gap_type", ""),
        "新颖性": g.get("novelty", ""),
        "置信度": g.get("confidence"),
        "体系": ", ".join(g.get("formulas", []) or []),
        "陈述": g.get("statement", ""),
        "可操作性": g.get("operability", "")[:60],
        "证据数": len(g.get("evidence_ids", []) or []),
    } for g in gap_list[:50]]
    st.dataframe(rows, width="stretch", hide_index=True)

    with st.expander("查看 Sciverse 新颖性回查详情"):
        for i, g in enumerate(gap_list[:20], 1):
            tag = _pill(g.get("gap_type", "-"), "blue") + " " + _pill(
                g.get("novelty", "-"),
                "green" if g.get("novelty") == "新知" else "orange",
            )
            st.markdown(
                f"<div style='font-size: 14px; margin: 8px 0;'>{tag} "
                f"<b>{g.get('statement', '')}</b></div>",
                unsafe_allow_html=True,
            )
            if g.get("verification"):
                st.markdown(f"- 验证：{g['verification']}")
            if g.get("operability"):
                st.markdown(f"- 可操作：{g['operability']}")


# ---------- 路线 A 搜索 ----------

def render_search() -> None:
    st.markdown(
        '<div class="ms-card"><div class="ms-card-title">路线 A：构效关系发现'
        "（搜索算法 × LLM）</div>"
        "<div style=\"font-size: 13px; color: #8C9AA8;\">"
        "搜索算法（GA / MCTS / BO / 符号回归）为骨架，LLM 参与假设生成、"
        "科学合理性评估与搜索空间引导，产出可解释构效关系。"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.space("small")
    tab_run, tab_findings = st.tabs(["交互执行", "历史发现"])

    with tab_run:
        c1, c2, c3, c4 = st.columns(4)
        algo = c1.selectbox("搜索算法", ["ga", "mcts", "bo", "sr"])
        use_llm = c2.selectbox(
            "评估模式", ["规则模式（快速）", "LLM 融合（较慢）"]
        )
        top_n = c3.slider("搜索 Gap 数量", 1, 5, 1)
        generations = c4.slider("迭代轮数", 1, 8, 2)

        from src.agent.search_agent import SearchAgent
        from src.common.llm import llm_available, model_name

        llm_on = use_llm == "LLM 融合（较慢）"
        if llm_on and not llm_available():
            st.error(
                "未配置 LLM Key（LLM_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY），"
                "请配置后重试或使用规则模式。"
            )
        elif llm_on:
            st.info(
                f"LLM 可用（模型 {model_name()}），三角色融合开启。"
                "LLM 评估逐点调用，可能需要数分钟。"
            )

        if st.button("运行搜索", type="primary"):
            with st.spinner(f"正在执行 {algo} 搜索（{top_n} 条 Gap）…"):
                agent = SearchAgent()
                results = agent.run(
                    top_n=top_n, generations=generations, pop_size=10,
                    use_llm=llm_on, algo=algo,
                )
            for i, res in enumerate(results, 1):
                f = res.finding
                st.markdown(f"**发现 {i}：{f.relation}**")
                st.markdown(f"- 假设：{f.hypothesis}")
                st.markdown(f"- 机制：{f.mechanism}")
                st.markdown(
                    f"- 置信度：{f.confidence}｜LLM 调用 {f.search_log.llm_calls} 次 / "
                    f"失败 {f.search_log.llm_failures} 次"
                )
                cands = ", ".join(c.formula for c in f.top_candidates[:5])
                st.markdown(f"- Top 候选：{cands}")
                if res.out_path:
                    st.markdown(f"- 落盘：`{res.out_path}`")
                st.divider()

    with tab_findings:
        files = _list_json(FINDINGS_DIR, "finding_*.json")
        if not files:
            st.warning("暂无历史发现，先在上方执行搜索。")
            return
        selected = st.selectbox("选择发现文件", [p.name for p in files], index=0)
        data = _load_json(FINDINGS_DIR / selected, {})
        if not data:
            st.warning("文件读取失败")
            return
        tag = _pill(data.get("novelty", "-"), "orange") + " " + _pill(
            f"置信度 {data.get('confidence', '-')}", "blue"
        )
        st.markdown(
            f"<div style='margin: 4px 0 8px;'>{tag}</div>", unsafe_allow_html=True
        )
        st.markdown(f"**关系**：{data.get('relation', '-')}")
        st.markdown(f"**假设**：{data.get('hypothesis', '-')}")
        st.markdown(f"**机制**：{data.get('mechanism', '-')}")
        cands = data.get("top_candidates", [])
        if cands:
            st.markdown("**Top 候选**")
            rows = [{
                "公式": c.get("formula", ""),
                "宿主": c.get("host", ""),
                "掺杂": c.get("dopant", ""),
                "浓度%": c.get("concentration"),
                "来源": c.get("source", ""),
                "评分": round(
                    sum((c.get("scores") or {}).values())
                    / max(len(c.get("scores") or {}), 1),
                    3,
                ),
            } for c in cands[:20]]
            st.dataframe(rows, width="stretch", hide_index=True)


# ---------- 数据库交叉验证 ----------

_VERDICT_COLOR = {
    "已知": "blue",
    "新知": "green",
    "反例": "orange",
    "验证失败": "gray",
}


def render_validation() -> None:
    st.markdown(
        '<div class="ms-card"><div class="ms-card-title">数据库交叉验证'
        "（OQMD / Materials Project）</div>"
        "<div style=\"font-size: 13px; color: #8C9AA8;\">"
        "对搜索发现的候选材料，在 OQMD / MP 数据库查询热力学稳定性与带隙，"
        "区分「新知」与「已知」。"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.space("small")
    files = _list_json(VALIDATION_DIR, "validation_*.json")
    if not files:
        st.warning("暂无验证结果，请先运行 scripts/run_validation.py")
        return
    verdicts: list[dict] = []
    for p in files:
        data = _load_json(p, {})
        for r in data.get("results", []) or []:
            verdicts.append({
                "源发现": data.get("source_finding", "-"),
                "候选": r.get("candidate_formula", ""),
                "宿主": r.get("host", ""),
                "掺杂": r.get("dopant", ""),
                "判定": r.get("verdict", ""),
                "依据": r.get("reason", "")[:80],
                "DB": ", ".join({e.get("db", "") for e in r.get("entries", []) or []}),
            })
    if not verdicts:
        st.warning("验证明细为空")
        return
    vcnt: dict[str, int] = {}
    for v in verdicts:
        vcnt[v["判定"]] = vcnt.get(v["判定"], 0) + 1
    pills = "".join(
        _pill(f"{k} {n}", _VERDICT_COLOR.get(k, "gray")) + " "
        for k, n in vcnt.items()
    )
    st.markdown(
        f"<div style='margin: 6px 0 10px;'>"
        f"<span style='font-size: 14px; font-weight: 600; color: {_TEXT};'>"
        f"验证 {len(verdicts)} 个候选</span>　{pills}</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(verdicts, width="stretch", hide_index=True)
    with st.expander("验证明细（含 DB 证据）"):
        for p in files[:10]:
            data = _load_json(p, {})
            st.markdown(f"**{p.name}**（来源 {data.get('source_finding', '-')}）")
            for r in (data.get("results", []) or [])[:5]:
                reason = r.get("reason", "")[:120]
                vtag = _pill(
                    r.get("verdict", "-"), _VERDICT_COLOR.get(r.get("verdict", ""), "gray")
                )
                st.markdown(
                    f"<div style='font-size: 14px; margin: 6px 0;'>{vtag} "
                    f"<b>{r.get('candidate_formula')}</b> — {reason}</div>",
                    unsafe_allow_html=True,
                )
                for chk in (r.get("checks", []) or []):
                    db_val = chk.get("db_value")
                    st.markdown(
                        f"  - [{chk.get('property')}] {db_val} → "
                        f"一致={chk.get('consistent')}"
                    )


# ---------- 评测指标 ----------

def _render_recall(data: dict) -> None:
    algo_rows = []
    for algo, s in (data.get("algo_summary") or {}).items():
        algo_rows.append({
            "算法": algo,
            **{f"recall@{k}": s.get(f"recall@{k}") for k in data.get("ks", [1, 3, 5])},
            "coverage": s.get("coverage"),
            "候选均值": s.get("n_candidates_avg"),
        })
    st.markdown(
        f'<div class="ms-card"><div class="ms-card-title">已知关系召回率评测</div>'
        f'<div style="font-size: 13px; color: {_MUTED};">'
        f"期望集 {data.get('n_facts')} 条｜LLM：{data.get('llm_on')}"
        f"（{data.get('llm_model') or '规则'}）</div></div>",
        unsafe_allow_html=True,
    )
    st.space("small")
    st.dataframe(algo_rows, width="stretch", hide_index=True)
    per_fact = data.get("per_fact", [])
    if per_fact:
        st.markdown("**逐条命中明细**")
        rows = []
        for f in per_fact:
            exp = f"{f.get('host')}-{f.get('dopant')} {f.get('concentration')}%"
            row = {"ID": f.get("id"), "期望方案": exp}
            for algo, s in f.items():
                if isinstance(s, dict) and ("coverage" in s or "hit@" in str(s)):
                    row[f"{algo} cov"] = "Y" if s.get("coverage") else "N"
                    row[f"{algo} @3"] = "Y" if s.get("hit@3") else "N"
            rows.append(row)
        st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(
        "双口径：hit@k 度量评分排序质量；coverage 度量探索覆盖率——"
        "分离可量化「探索到了但未排进 top-k」的评分-期望错配。"
    )


def render_eval() -> None:
    st.markdown(
        '<div class="ms-card"><div class="ms-card-title">评测指标'
        "（results/eval/）</div>"
        "<div style=\"font-size: 13px; color: #8C9AA8;\">"
        "评测链路：extraction_f1（字段级 F1）/ recall（已知关系召回率）/"
        "gap_novelty_review（Gap 新颖性复核）。"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.space("small")
    files = _list_json(EVAL_DIR, "*.json")
    if not files:
        st.warning("暂无评测产物")
        return
    selected = st.selectbox("选择评测文件", [p.name for p in files], index=0)
    data = _load_json(EVAL_DIR / selected, {})
    if not data:
        st.warning("文件读取失败")
        return
    if "algo_summary" in data:
        _render_recall(data)
    else:
        st.json(data)


# ---------- 调研报告 ----------

def render_reports() -> None:
    st.markdown(
        '<div class="ms-card"><div class="ms-card-title">调研报告</div>'
        "<div style=\"font-size: 13px; color: #8C9AA8;\">"
        "结构化文献调研报告：检索策略 / 知识抽取 / Research Gap 清单 / 文献综述。"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.space("small")
    md_files = _list_json(REPORTS_DIR, "report_*.md")
    if not md_files:
        st.warning("暂无报告，请先运行 scripts/run_report.py")
        return
    selected = st.selectbox("选择报告", [p.name for p in md_files], index=0)
    md_path = REPORTS_DIR / selected
    text = md_path.read_text(encoding="utf-8")
    st.markdown(text)

    html_path = md_path.with_suffix(".html")
    if html_path.exists():
        with st.expander("查看 HTML 渲染版"):
            st.iframe(html_path, height=800)


# ---------- 入口 ----------

def main() -> None:
    _inject_css()
    with st.sidebar:
        st.markdown(
            f"<div style='font-size: 16px; font-weight: 700; color: {_PRIMARY};"
            " letter-spacing: 0.3px;'>材料科学文献智能体</div>",
            unsafe_allow_html=True,
        )
        st.caption("赛道三·方向三 · 本地演示 Demo")
        st.markdown(
            f"<div style='border-top: 1px solid {_BORDER}; margin: 10px 0;'></div>",
            unsafe_allow_html=True,
        )
        st.markdown("**模块导航**")
        st.caption("使用顶部 Tab 切换查看各模块成果：")
        st.caption("知识库 · Gap 清单 · 路线A搜索 · 数据库验证 · 评测指标 · 调研报告")
        st.markdown("**交互演示**")
        st.caption("路线 A 支持交互执行：选择算法（GA/MCTS/BO/SR）")
        st.caption("与评估模式（规则 / LLM 融合）后点击「运行搜索」。")
        st.markdown(
            f"<div style='border-top: 1px solid {_BORDER}; margin: 10px 0;'></div>",
            unsafe_allow_html=True,
        )
        st.caption("数据来源：data/ 与 results/（本地生成，可追溯证据链）")

    tabs = st.tabs(
        ["总览", "知识库", "Gap 清单", "路线A搜索", "数据库验证", "评测指标", "调研报告"]
    )
    with tabs[0]:
        render_overview()
    with tabs[1]:
        render_knowledge_base()
    with tabs[2]:
        render_gaps()
    with tabs[3]:
        render_search()
    with tabs[4]:
        render_validation()
    with tabs[5]:
        render_eval()
    with tabs[6]:
        render_reports()


if __name__ == "__main__":
    main()

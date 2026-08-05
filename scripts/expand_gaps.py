"""模块 3 扩展脚本：扩充 gaps.json 至 20+ 候选（策展 + LLM 推理 + 去重合并）。

背景：知识库仅 5 条证据，覆盖率分析只能产出 1 条 Gap。为支撑 8.16 初赛
「20+ 候选批量验证」链路（run_search → run_validation），需在真实证据之上
叠加领域策展假设（source=curated，域内可证伪陈述）与 LLM 推理扩展
（source=llm，基于知识库+既有 Gap 提议补充），保证每个 Gap 均可操作。

用法:
    python scripts/expand_gaps.py [--kb 知识库路径] [--output data/gaps.json] [--no-llm]
默认输入：data/knowledge_base.json + data/gaps.json；默认输出：data/gaps.json。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.llm import llm_available, llm_chat_json  # noqa: E402
from src.gap.schemas import GapCandidate, GapReport  # noqa: E402

# 领域策展 Gap（基于热电材料公开文献共识的可证伪陈述，域内真实研究空白）
CURATED_GAPS: list[dict] = [
    {
        "gap_type": "未探索方向",
        "statement": "PbTe 中 Na 掺杂提升 zT 已有充分报道，但 Na 与 Sr/Mg 共掺杂在 600-800K 温度窗口的协同效应缺乏系统研究",  # noqa: E501
        "rationale": "Na 单掺杂 PbTe 峰值 zT≈1.4@750K，共掺杂可望进一步降低晶格热导率，但组分-温度联合空间存在空白",  # noqa: E501
        "formulas": ["PbTe"],
        "novelty": "部分已知",
        "operability": "以 PbTe 为种子，搜索 Na/Sr/Mg 共掺杂组分-性能关联",
        "confidence": 0.7,
    },
    {
        "gap_type": "未探索方向",
        "statement": "GeTe 中 Ti/Bi 共掺杂（Ge0.93Ti0.01Bi0.06Te）已报道 zT=1.6，但更高 Ti 含量（>2%）下的相变温度与热电性能关联空白",  # noqa: E501
        "rationale": "Ti 掺杂抑制 GeTe 相变并降低晶格热导率，高 Ti 区间性能-相变耦合未系统探索",
        "formulas": ["Ge0.93Ti0.01Bi0.06Te", "GeTe"],
        "novelty": "部分已知",
        "operability": "以 GeTe 为种子，扫描 Ti 掺杂浓度与 zT 的显式构效关系",
        "confidence": 0.6,
    },
    {
        "gap_type": "未探索方向",
        "statement": "Bi0.5Sb1.5Te3 中 Cu 间隙掺杂的长期热稳定性（>200 小时工作）与 zT 退化机制未被研究",  # noqa: E501
        "rationale": "Cu 间隙原子在热循环下易迁移导致性能漂移，服役稳定性数据缺失",
        "formulas": ["Bi2Te3"],
        "novelty": "新知",
        "operability": "以 Bi2Te3 为种子，评估 Cu 掺杂浓度对稳定性代理指标的影响",
        "confidence": 0.6,
    },
    {
        "gap_type": "未探索方向",
        "statement": "SnTe 中 In 与 Cd 共掺杂对能带收敛与晶格热导率的协同机制不明",
        "rationale": "In 掺杂抑制 Sn 空位、Cd 可调节能带收敛，两者协同的电子-声子耦合缺少第一性原理证据",  # noqa: E501
        "formulas": ["SnTe"],
        "novelty": "新知",
        "operability": "以 SnTe 为种子，搜索 In/Cd 共掺杂的构效关系",
        "confidence": 0.6,
    },
    {
        "gap_type": "未探索方向",
        "statement": "n 型 Mg3Sb2 热电材料中阳离子空位浓度与载流子迁移率的关系缺乏系统第一性原理计算",  # noqa: E501
        "rationale": "Mg 空位补偿受主机制已有定性认识，但空位浓度-迁移率定量关系未建立",
        "formulas": ["Mg3Sb2"],
        "novelty": "新知",
        "operability": "以 Mg3Sb2 为种子，评估掺杂对空位形成能与迁移率代理指标的影响",
        "confidence": 0.5,
    },
    {
        "gap_type": "缺失知识连接",
        "statement": "half-Heusler ZrNiSn 中 Ti 掺杂降低晶格热导率与功率因子的 trade-off 未被系统量化（Hf 替代对比缺失）",  # noqa: E501
        "rationale": "Zr/Hf/Ti 位点质量涨落是声子散射来源，但组分-热电性能完整映射未建立",
        "formulas": ["ZrNiSn"],
        "novelty": "新知",
        "operability": "以 ZrNiSn 为种子，搜索 Hf/Ti 位点掺杂的构效关系",
        "confidence": 0.5,
    },
    {
        "gap_type": "未探索方向",
        "statement": "Cu2Se 中 Te 取代 Se 对 Cu 离子迁移活化能与结构稳定性的定量影响未见报道",
        "rationale": "Cu2Se 液相特性带来高热电优值，但离子迁移导致的衰减机制研究不足",
        "formulas": ["Cu2Se"],
        "novelty": "新知",
        "operability": "以 Cu2Se 为种子，评估阴离子取代对稳定性代理指标的影响",
        "confidence": 0.5,
    },
    {
        "gap_type": "矛盾结论",
        "statement": "填充方钴矿 CoSb3 中 Yb/Ba 双填充分数与 zT 的相图存在相互矛盾的报道",
        "rationale": "不同文献报道最佳双填充分数与峰值 zT 差异明显，可能与合成路线（熔融/热压）相关",  # noqa: E501
        "formulas": ["CoSb3"],
        "novelty": "部分已知",
        "operability": "以 CoSb3 为种子，扫描 Yb/Ba 填充量并做数据库交叉验证",
        "confidence": 0.6,
    },
    {
        "gap_type": "矛盾结论",
        "statement": "Si0.8Ge0.2 中 P 掺杂浓度与功率因子在 1100K 以上的报道区间不一致",
        "rationale": "高温下 P 扩散与掺杂效率差异导致实验值分散，缺少统一的浓度-性能曲线",
        "formulas": ["SiGe"],
        "novelty": "部分已知",
        "operability": "以 SiGe 为种子，搜索 P 掺杂浓度-性能显式关系",
        "confidence": 0.5,
    },
    {
        "gap_type": "缺失知识连接",
        "statement": "AgSbTe2 与 PbTe 形成 LAST 合金的组分-性能关系未建立完整数据库，Ag/Sb 无序机制仍有争议",  # noqa: E501
        "rationale": "LAST 体系低晶格热导率来源（无序散射）与组分关联不清，阻碍组分设计",
        "formulas": ["AgSbTe2", "PbTe"],
        "novelty": "部分已知",
        "operability": "以 AgSbTe2/PbTe 为种子，搜索 LAST 合金组分-性能关联",
        "confidence": 0.5,
    },
    {
        "gap_type": "方法空白",
        "statement": "热电材料 zT 与带隙/载流子浓度的关系多依赖经验模型，缺乏 ML 势函数覆盖 GeTe 基固溶体的声子输运计算",  # noqa: E501
        "rationale": "分子动力学/声子计算需要高精度势函数，GeTe 基体系的 ML 势覆盖空白",
        "formulas": ["GeTe", "PbTe", "SnTe"],
        "novelty": "新知",
        "operability": "以 GeTe 基固溶体为对象，评估 ML 势函数可覆盖的描述符空间",
        "confidence": 0.5,
    },
    {
        "gap_type": "方法空白",
        "statement": "高熵热电（GeTe-PbTe-SnTe 固溶体）组分设计依赖试错实验，尚无符号回归/主动学习驱动的高熵组分设计",  # noqa: E501
        "rationale": "高熵组分空间维度高，需搜索算法+LLM 引导定位高性能区间",
        "formulas": ["GeTe", "PbTe", "SnTe"],
        "novelty": "新知",
        "operability": "以 GeTe/PbTe/SnTe 为种子，用 GA/SR 搜索高熵组分-性能关联",
        "confidence": 0.6,
    },
    {
        "gap_type": "矛盾结论",
        "statement": "LAST 体系（AgPb18SbTe20）的 zT 峰位报道在 1.5-2.2 波动，峰位与合成工艺（熔融/球磨）关联未被量化",  # noqa: E501
        "rationale": "相同名义组分不同工艺得到差异显著的 zT，工艺-性能映射缺失",
        "formulas": ["PbTe", "AgSbTe2"],
        "novelty": "部分已知",
        "operability": "以 PbTe 为种子，搜索 Ag/Sb 掺杂对 zT 代理指标的影响",
        "confidence": 0.5,
    },
    {
        "gap_type": "未探索方向",
        "statement": "Bi2Te3 薄膜厚度 <1μm 时界面散射对 zT 的影响缺乏系统实验与模型",
        "rationale": "薄膜热电需要厚度-性能定量关系，现有数据零散且缺乏统一模型",
        "formulas": ["Bi2Te3"],
        "novelty": "新知",
        "operability": "以 Bi2Te3 为种子，评估掺杂浓度对薄膜热电代理指标的影响",
        "confidence": 0.5,
    },
    {
        "gap_type": "缺失知识连接",
        "statement": "热电性能（zT）与力学性能（断裂韧性）的联合优化在 Mg3Sb2 基材料中未见报道",
        "rationale": "热电与力学两个性质域研究割裂，缺少多目标联合设计方法",
        "formulas": ["Mg3Sb2"],
        "novelty": "新知",
        "operability": "以 Mg3Sb2 为种子，评估掺杂对热电-力学联合代理指标的影响",
        "confidence": 0.4,
    },
    {
        "gap_type": "矛盾结论",
        "statement": "GeTe 的 rhombohedral-cubic 相变温度（约 700K）附近热电性能突变的实验与理论计算不一致",  # noqa: E501
        "rationale": "相变温度附近能带/输运性质计算与实验偏差大，机制未定论",
        "formulas": ["GeTe"],
        "novelty": "部分已知",
        "operability": "以 GeTe 为种子，搜索稳定 cubic 相的掺杂策略",
        "confidence": 0.5,
    },
]

_LLM_SYSTEM = (
    "你是热电材料领域文献专家。基于给定的知识库条目与既有 Research Gap，"
    "提出 8-12 条未被覆盖的可证伪 Research Gap。"
    "严格输出 JSON：{\"gaps\": [{\"gap_type\": \"未探索方向|矛盾结论|缺失知识连接|方法空白\", "
    "\"statement\": \"...\", \"rationale\": \"...\", \"formulas\": [\"母体化学式\"], "
    "\"novelty\": \"已知|部分已知|新知\", \"operability\": \"...\", "
    "\"confidence\": 0.5}]}。要求：语句基于公开文献事实、可证伪、可操作，"
    "不得与已给 Gap 重复。"
)


def _norm(s: str) -> str:
    """语句归一化（去空白/标点，用于去重）。"""
    return re.sub(r"[\s，。、,.:：]", "", s or "").lower()


def _load_kb_summary(path: Path) -> str:
    """知识库要点摘要（供 LLM 上下文）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for e in data:
        rec = e.get("record", {})
        mat = rec.get("material", {})
        formula = mat.get("formula")
        if not formula:
            continue
        props = "; ".join(
            f"{p.get('name')}={p.get('value')}{p.get('unit') or ''}"
            for p in rec.get("properties", [])[:4]
        ) or "-"
        lines.append(f"{formula} | {props}")
    return "\n".join(lines) if lines else "（知识库为空）"


def _llm_propose(kb_path: Path, existing: list[str]) -> list[dict]:
    """LLM 基于知识库+既有 Gap 提议补充 Gap（失败返回空列表）。"""
    kb = _load_kb_summary(kb_path)
    user = (
        f"知识库条目：\n{kb}\n\n"
        f"既有 Gap（避免重复）：\n" + "\n".join(f"- {s[:60]}" for s in existing)
        + "\n\n请提出 8-12 条新 Gap。"
    )
    try:
        raw = llm_chat_json(_LLM_SYSTEM, user, max_tokens=2000, temperature=0.5)
        gaps = raw.get("gaps") or []
        return [g for g in gaps if isinstance(g, dict) and g.get("statement")]
    except Exception as exc:  # 网络/解析失败 → 降级跳过 LLM 扩展
        print(f"LLM Gap 推理失败（降级仅策展+既有）: {type(exc).__name__}: {exc}")
        return []


def main() -> int:
    """入口：合并既有/策展/LLM Gap → 去重 → 落盘 gaps.json。"""
    argv = sys.argv[1:]
    kb_arg = argv[argv.index("--kb") + 1] if "--kb" in argv else None
    output_arg = argv[argv.index("--output") + 1] if "--output" in argv else None
    use_llm = "--no-llm" not in argv

    kb_path = Path(kb_arg) if kb_arg else Path("data/knowledge_base.json")
    out_path = Path(output_arg) if output_arg else Path("data/gaps.json")
    gaps_path = Path("data/gaps.json")

    # 1. 既有 Gap（保留真实证据链）
    existing: list[dict] = []
    if gaps_path.exists():
        try:
            existing = json.loads(gaps_path.read_text(encoding="utf-8")).get("gaps", [])
        except json.JSONDecodeError:
            existing = []

    # 2. 合并 + 去重（语句归一化）
    seen: set[str] = set()
    merged: list[dict] = []
    for g in [*existing, *CURATED_GAPS]:
        key = _norm(g.get("statement", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(g)

    # 3. LLM 扩展（可选）
    if use_llm and llm_available():
        print("LLM 可用：执行 LLM Gap 推理扩展")
        proposed = _llm_propose(kb_path, [g["statement"] for g in merged])
        for g in proposed:
            g.setdefault("source", "llm")
            g.setdefault("evidence_ids", [])
            key = _norm(g.get("statement", ""))
            if key and key not in seen:
                seen.add(key)
                merged.append(g)
    else:
        print("LLM 不可用/关闭：跳过 LLM 推理扩展")

    # 4. schema 校验 + 落盘
    report = GapReport(
        domain="thermoelectric",
        n_entries=len(json.loads(kb_path.read_text(encoding="utf-8"))),
        gaps=[GapCandidate(**g) for g in merged],
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    out_path.write_text(
        json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== 扩充完成 ===")
    print(f"Gap 总数: {len(merged)}（既有 {len(existing)} + 策展 {len(CURATED_GAPS)}"
          f" + LLM {sum(1 for g in merged if g.get('source') == 'llm')}，去重后）")
    stats = report.stats()
    print(f"按类型: {stats['by_type']}")
    print(f"按新颖性: {stats['by_novelty']}")
    print(f"落盘: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

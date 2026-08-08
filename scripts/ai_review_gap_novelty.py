"""基本任务评测②扩展：Gap 新颖性「AI 专业批注建议版」生成。

对齐 `.trae/rules/04-literature-agent.md` 4.3 与 `review_gap_novelty.py` 的人工复核流程。
本脚本把「人工复核」负担降为「人工核对」：基于**路线 A 数据库交叉验证证据链**
（`results/consensus/consensus_verify_*.json`，12 共识候选 → 已知 9/反例 3）
与热电材料领域知识，为每条 Gap 给出 `ai_reviewer_note`（判定建议 + 理由），
写入独立文件 `gap_novelty_review.ai2.json`（不改主清单、不改 gaps.json）。

用法（人工核对后）：
    1. 运行本脚本生成建议版：python scripts/ai_review_gap_novelty.py
    2. 人工打开 gap_novelty_review.ai2.json 逐条核对，将认可的条目
       review_status 改 reviewed（或直接复制建议到主清单）
    3. 执行写回：python scripts/review_gap_novelty.py --write-back <review.json>
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_EVAL_ROOT = Path(__file__).resolve().parents[1] / "results" / "eval"
DEFAULT_REVIEW = _EVAL_ROOT / "gap_novelty_review.json"
DEFAULT_OUT = _EVAL_ROOT / "gap_novelty_review.ai2.json"

# idx → (建议判定, 理由)。结合 consensus_verify 证据链（c1）与热电领域知识。
# 证据链引用：Cu2Se-Te5%/Si0.8Ge0.2-P2% 被 OQMD 判定「反例」（DFT 亚稳 vs 实验应用），
# CoSb3-Yb0.2Ba0.10%/ZrNiSn-Hf5% 等判定「已知」（母体在库且稳定）。
AI_SUGGESTIONS: dict[int, tuple[str, str]] = {
    0: (
        "新知",
        "Ge0.93Ti0.01Bi0.06Te 特定配比报道极少"
        "（c1 验证 GeTe 族母体已知，但该三元配比的系统性能研究缺失）；"
        "heuristic 建议一致",
    ),
    1: (
        "部分已知",
        "PbTe 掺 Na 已知充分（c1 验证 PbTe 族候选多为已知），"
        "但 Na 与 Sr/Mg 共掺杂的 600-800K 协同效应仅少量文献；"
        "heuristic 建议「已知」过于激进",
    ),
    2: ("新知", "高 Ti 含量（>2%）GeTe 的相变-性能关联确实空白；GeTe 已知不覆盖该浓度区间"),
    3: (
        "部分已知",
        "Cu 掺杂 Bi2Te3 提升 zT 有文献，但 >200h 长期热稳定性与退化机制缺系统研究；"
        "Sciverse 0 命中主要因 chunk 语料覆盖有限",
    ),
    4: (
        "已知",
        "SnTe 中 In 掺杂（能带收敛）与 Cd 共掺杂均有文献"
        "（c1 验证 SnTe 母体已知）；heuristic 命中 5 条一致",
    ),
    5: (
        "部分已知",
        "n 型 Mg3Sb2 空位-载流子迁移率有第一性原理工作"
        "（c1 验证 Mg3Sb2-Na2% 已知），但阳离子空位浓度的系统扫描缺失",
    ),
    6: (
        "已知",
        "half-Heusler ZrNiSn 的 Ti/Hf 掺杂文献极多"
        "（c1 验证 ZrNiSn-Hf5%/Ti5% 均判定已知）；trade-off 虽未完全量化但已被充分研究",
    ),
    7: (
        "部分已知",
        "Cu2(Se,Te) 固溶体研究存在（c1 验证 Cu2Se-Te5% 被判「反例」——"
        "OQMD hull=0.125 亚稳，提示 DFT 稳定性存疑），"
        "Te 取代对迁移活化能的定量影响未被系统覆盖",
    ),
    8: (
        "已知",
        "填充方钴矿 CoSb3 的 Yb/Ba 双填充文献海量"
        "（c1 验证 CoSb3-Yb0.2Ba0.10% 判定已知）；矛盾结论恰说明已被充分研究，"
        "属「争议集中点」而非空白",
    ),
    9: (
        "已知",
        "SiGe 基合金 P 掺杂是成熟体系（c1 验证 Si0.8Ge0.2-P2%×2 均判定反例"
        "——hull=0.512 亚稳）；1100K 报道区间不一致属已知争议",
    ),
    10: (
        "已知",
        "LAST（AgPb18SbTe20/AgSbTe2-PbTe）体系 2004 年起大量研究，"
        "组分-性能数据库已建立；无序机制争议存在但非空白",
    ),
    11: (
        "部分已知",
        "ML 势函数（MACE/NequIP 等）已应用于热电声子输运，"
        "但 GeTe 基固溶体的完整覆盖缺失；heuristic 命中 2 条偏保守",
    ),
    12: (
        "部分已知",
        "高熵热电设计已有主动学习工作（如 NPJ Comput Mater），"
        "但符号回归驱动的组分设计少见",
    ),
    13: (
        "已知",
        "LAST 体系 zT 峰位 1.5-2.2 波动是公认文献现象"
        "（熔融/球磨工艺差异已被报道）；heuristic 命中 5 条一致",
    ),
    14: ("部分已知", "Bi2Te3 薄膜界面散射研究较多，但 <1μm 厚度的系统 zT 模型仍缺"),
    15: (
        "新知",
        "Mg3Sb2 基 zT-断裂韧性联合优化确实未见报道"
        "（c1 验证 Mg3Sb2 母体已知，但力学-热电耦合维度空白）",
    ),
    16: (
        "已知",
        "GeTe 约 700K 相变附近的输运反常被大量实验与计算研究"
        "（c1 验证 GeTe 母体已知）；理论-实验不一致本身是被反复讨论的主题",
    ),
    17: (
        "新知",
        "Ge0.93Ti0.01Bi0.06Te 有效质量- Seebeck 解耦的单独研究缺失"
        "（与 idx0/2 同一三元配比空白族）",
    ),
    18: (
        "已知",
        "Cu 掺杂 Bi2Te3 在块体（增强）与薄膜（抑制/相反）的相反报道"
        "已被文献记录，属已知争议",
    ),
    19: ("新知", "Ca5In2Sb6 研究总量少，In 空位- zT 定量关系空白"),
    20: (
        "新知",
        "ML 势函数预测掺杂 GeTe 相变温度的声子计算尚未开展"
        "（与 idx11 互补，聚焦相变温度）",
    ),
    21: (
        "部分已知",
        "Bi2Te3 系反位缺陷与 Te 化学计量已有文献，"
        "但 Bi0.5Sb1.5Te3 特定体系的系统扫描缺失",
    ),
    22: (
        "已知",
        "PbTe 掺 Na 最优浓度 0.5-2at% 波动是成熟争议"
        "（SPS vs 熔融工艺差异已知）；heuristic 命中 4 条一致",
    ),
    23: ("新知", "Ca5In2Sb6/Bi2Te3 异质结界面能带对齐未见报道（Ca5In2Sb6 本属少研究体系）"),
    24: ("新知", "主动学习优化 GeTe 基 Ti/Bi 掺杂比例的研究未见报道（与 idx12 同类但聚焦 GeTe）"),
    25: ("部分已知", "Te 空位对 Bi2Te3 κL 的贡献有报道，但 300-500K 定量分离缺系统研究"),
    26: ("已知", "GeTe 掺 Bi 对相变温度影响的矛盾报道（升降之争）已被文献记录，属已知争议"),
    27: ("新知", "Ca5In2Sb6 的 zT-带隙关系未建立（少研究体系）"),
    28: (
        "部分已知",
        "高分辨 STEM/TEM 对 Bi2Te3 系反位缺陷已有直接成像工作，"
        "但浓度定量统计（Te 空位 vs 反位）未见系统报道",
    ),
}


def build_ai_review(review_path: Path) -> dict:
    """主复核清单 → AI 专业建议版（不改主清单）。

    参数:
        review_path: review_gap_novelty.py 生成的主复核清单路径。

    返回:
        AI 建议版 dict：每条例项新增 ai_reviewed/ai_reviewer_note 字段，
        review_status 保持 pending（写回仍由人工核对后触发）。
    """
    review = json.loads(review_path.read_text(encoding="utf-8"))
    items: list[dict] = []
    for item in review.get("items", []):
        idx = item.get("idx")
        entry = dict(item)
        suggestion = AI_SUGGESTIONS.get(idx)
        if suggestion:
            entry["ai_reviewed"] = True
            entry["ai_suggested_novelty"] = suggestion[0]
            entry["ai_reviewer_note"] = suggestion[1]
        else:
            entry["ai_reviewed"] = False
            entry["ai_reviewer_note"] = "无 AI 建议（请在人工复核时单独判断）"
        items.append(entry)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instruction": (
            "AI 专业批注建议版：ai_suggested_novelty/ai_reviewer_note 基于路线 A "
            "数据库交叉验证证据链（results/consensus/consensus_verify_*.json）与热电领域知识给出，"
            "供人工核对。核对方式：认可的条目复制建议到主清单（confirmed_novelty + "
            "review_status=reviewed + reviewer_note），或直接在建议版上修改后写回。"
            "完成写回：python scripts/review_gap_novelty.py --write-back <review.json>"
        ),
        "source_review": str(review_path),
        "n_gaps": review.get("n_gaps"),
        "n_ai_suggested": sum(1 for i in items if i.get("ai_reviewed")),
        "items": items,
    }


def main() -> None:
    """生成 AI 专业批注建议版（不修改主清单与 gaps.json）。"""
    review_path = Path(DEFAULT_REVIEW)
    if not review_path.exists():
        raise SystemExit(f"未找到主复核清单：{review_path}，请先运行 scripts/review_gap_novelty.py")
    out = build_ai_review(review_path)
    DEFAULT_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"AI 建议覆盖：{out['n_ai_suggested']}/{out['n_gaps']} 条 Gap → {DEFAULT_OUT}")
    print("人工核对后写回：python scripts/review_gap_novelty.py --write-back <已核对清单>")


if __name__ == "__main__":
    main()

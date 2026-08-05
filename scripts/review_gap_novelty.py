"""基本任务评测②：29 条 Gap 新颖性人工复核材料生成 + 批注写回。

对齐 `.trae/rules/04-literature-agent.md` 第 4.3 节（新颖性评估）与
`src/agent/gap_agent.py` `_verify_novelty` 的「判定仅供参考，需人工复核」留痕。

两个模式：
1. 生成模式（默认）：读 data/gaps.json → 生成复核清单
   `results/eval/gap_novelty_review.json`，每条含 statement/formulas/当前新颖性/
   Sciverse 回查留痕/启发式建议判定/理由，供人工批注
2. 回查模式（--verify）：先对每条 Gap 跑 Sciverse semantic_search 回查
   （top5 含主化学式命中数 → 已知/部分已知/新知启发式），verification 写回
   gaps.json 并生成清单——人工复核有真实检索证据可依（默认模式无回查时
   启发式全部「需人工确认」）
3. 写回模式（--write-back <review.json>）：读人工批注后的清单
   （review_status="reviewed" + confirmed_novelty）→ 更新 data/gaps.json 的
   novelty 字段并加 novelty_confirmed/reviewed_at 标记

启发式建议（基于现有回查留痕，非最终判定）：
- verification 为 null（未回查）→ 需人工确认
- 回查失败降级 → 需人工确认
- 命中数 0 → 新知（建议）；1 → 部分已知（建议）；≥2 → 已知（建议）

用法:
    python scripts/review_gap_novelty.py [--verify]
        [--gaps data/gaps.json] [--out results/eval/gap_novelty_review.json]
    python scripts/review_gap_novelty.py --write-back results/eval/gap_novelty_review.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DATA_DIR
from src.retrieval.sciverse_client import SciverseClient, SciverseError

DEFAULT_GAPS = DATA_DIR / "gaps.json"
_EVAL_ROOT = Path(__file__).resolve().parents[1] / "results" / "eval"
DEFAULT_REVIEW = _EVAL_ROOT / "gap_novelty_review.json"
_VALID_NOVELTY = {"新知", "部分已知", "已知"}
_HIT_RE = re.compile(r"(\d+) 条片段含")


def _heuristic(item: dict) -> tuple[str, str]:
    """基于回查留痕给出建议判定与理由（启发式，需人工复核）。"""
    verification = item.get("verification")
    if not verification:
        return "需人工确认", "无 Sciverse 回查留痕（verification=null），依据不足"
    if "回查失败" in verification:
        return "需人工确认", f"Sciverse 回查失败降级：{verification[:120]}"
    m = _HIT_RE.search(verification)
    if not m:
        return "需人工确认", f"回查留痕无法解析：{verification[:120]}"
    hits = int(m.group(1))
    if hits >= 2:
        return "已知", f"Sciverse top5 命中 {hits} 条含主化学式，覆盖度较高"
    if hits == 1:
        return "部分已知", "Sciverse top5 仅 1 条含主化学式，边界情形"
    return "新知", "Sciverse top5 无含主化学式的片段，覆盖度低"


def _load_gaps(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_review(gaps: dict) -> dict:
    """gaps.json → 人工复核清单。"""
    items: list[dict] = []
    for idx, g in enumerate(gaps.get("gaps", [])):
        suggestion, reason = _heuristic(g)
        items.append(
            {
                "idx": idx,
                "gap_type": g.get("gap_type"),
                "statement": g.get("statement"),
                "formulas": g.get("formulas", []),
                "current_novelty": g.get("novelty"),
                "source": g.get("source"),
                "evidence_count": len(g.get("evidence_ids") or []),
                "verification": g.get("verification"),
                "heuristic_suggestion": suggestion,
                "suggestion_reason": reason,
                "review_status": "pending",
                "confirmed_novelty": None,
                "reviewer_note": None,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "instruction": (
            "对每条 Gap 复核新颖性：比较 heuristic_suggestion 与你的专业判断，"
            "在 confirmed_novelty 填「新知/部分已知/已知」，review_status 改 reviewed，"
            "reviewer_note 写理由。完成后运行 --write-back 写回 gaps.json。"
            "证据链建议：已知/部分已知需能指出具体文献；新知需确认 Sciverse/知识库均未覆盖。"
        ),
        "gaps_path": str(DEFAULT_GAPS),
        "n_gaps": len(gaps.get("gaps", [])),
        "items": items,
    }


def _novelty_query(gap: dict) -> str:
    """构造回查查询：主化学式 + Gap 陈述（控长度，与 gap_agent 一致）。"""
    prefix = f"{gap['formulas'][0]} " if gap.get("formulas") else ""
    return f"{prefix}{gap.get('statement') or ''}"[:200]


async def verify_gaps(gaps: dict) -> tuple[dict, int, int]:
    """逐条 Sciverse 回查，verification 写回 gaps（含降级留痕）。

    返回 (gaps, n_ok, n_failed)。判定规则与 gap_agent._verify_novelty 一致：
    top5 片段含主化学式 ≥2 → 已知；=1 → 部分已知；0 → 新知（仅供参考）。
    """
    client = SciverseClient()
    n_ok, n_failed = 0, 0
    for g in gaps.get("gaps", []):
        try:
            result = await client.semantic_search(_novelty_query(g), top_k=5, mode="fast")
        except SciverseError as exc:
            n_failed += 1
            g["verification"] = f"Sciverse 回查失败（降级，默认新颖性）：{str(exc)[:120]}"
            continue
        hits = result.get("hits", [])
        formula = g.get("formulas") or [None]
        matched = sum(
            1 for hit in hits
            if formula[0] and formula[0] in (hit.get("chunk") or "")
        )
        g["verification"] = (
            f"Sciverse 回查 top5：{matched} 条片段含 {formula[0] or '无化学式'}，"
            "判定仅供参考，需人工复核"
        )
        n_ok += 1
    return gaps, n_ok, n_failed


def write_back(review_path: Path, gaps: dict) -> tuple[dict, int]:
    """人工批注 → 写回 gaps.json（novelty + novelty_confirmed + reviewed_at）。"""
    review = json.loads(review_path.read_text(encoding="utf-8"))
    reviewed_at = datetime.now(timezone.utc).isoformat()
    updated = 0
    gaps_list = gaps.get("gaps", [])
    for item in review.get("items", []):
        if item.get("review_status") != "reviewed":
            continue
        confirmed = item.get("confirmed_novelty")
        if confirmed not in _VALID_NOVELTY:
            continue
        idx = item.get("idx")
        if not isinstance(idx, int) or not (0 <= idx < len(gaps_list)):
            continue
        gaps_list[idx]["novelty"] = confirmed
        gaps_list[idx]["novelty_confirmed"] = True
        gaps_list[idx]["reviewed_at"] = reviewed_at
        gaps_list[idx]["reviewer_note"] = item.get("reviewer_note")
        updated += 1
    gaps["novelty_reviewed"] = updated
    return gaps, updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Gap 新颖性人工复核")
    parser.add_argument("--gaps", type=str, default=str(DEFAULT_GAPS), help="gaps.json 路径")
    parser.add_argument("--out", type=str, default=str(DEFAULT_REVIEW), help="复核清单输出路径")
    parser.add_argument("--verify", action="store_true",
                        help="先对每条 Gap 跑 Sciverse 回查，verification 写回 gaps.json")
    parser.add_argument("--write-back", type=str, default=None,
                        help="读取已批注清单并写回 gaps.json（人工批注后执行）")
    args = parser.parse_args()

    gaps_path = Path(args.gaps)
    gaps = _load_gaps(gaps_path)

    if args.write_back:
        gaps, updated = write_back(Path(args.write_back), gaps)
        gaps_path.write_text(
            json.dumps(gaps, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已写回 {updated} 条复核判定 → {gaps_path}")
        return

    if args.verify:
        gaps, n_ok, n_failed = asyncio.run(verify_gaps(gaps))
        gaps_path.write_text(
            json.dumps(gaps, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Sciverse 回查完成：成功 {n_ok} 条，失败 {n_failed} 条 → 已写回 {gaps_path}")
        # 打印启发式判定分布（含失败降级条数）
        dist: dict[str, int] = {}
        for g in gaps.get("gaps", []):
            sug, _ = _heuristic(g)
            dist[sug] = dist.get(sug, 0) + 1
        print(f"启发式判定分布：{dist}（仅供参考，需人工复核）")

    review = build_review(gaps)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    # 汇总：当前新颖性 vs 启发式建议分布
    current: dict[str, int] = {}
    suggested: dict[str, int] = {}
    for item in review["items"]:
        cur = item["current_novelty"] or "未知"
        current[cur] = current.get(cur, 0) + 1
        sug = item["heuristic_suggestion"]
        suggested[sug] = suggested.get(sug, 0) + 1
    print(f"Gap 总数：{review['n_gaps']}")
    print(f"当前新颖性分布：{current}")
    print(f"启发式建议分布：{suggested}")
    print(f"复核清单已生成：{out_path}")
    print("人工批注后执行：python scripts/review_gap_novelty.py --write-back <review.json>")


if __name__ == "__main__":
    main()

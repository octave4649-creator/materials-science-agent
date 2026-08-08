"""基本任务评测①辅助：AI 预填 gold 草稿，降低人工标注成本。

流程定位（对齐 `.trae/rules/00-project-rules.md` 7.2 与 `eval_extraction_f1.py`）：
1. 人工标注是最终评测依赖，但 9 条 chunk 全空标注成本高
2. 本脚本用 LLM 五段式抽取为每条 chunk 预填 gold（AI 初稿）
3. 输出 `data/eval/extraction_gold.prefill.json`（**不覆盖** extraction_gold.json）：
   每条含 chunk + ai_gold + instruction，人工逐条核对（重点去除 LLM 幻觉字段：
   未提及信息留 null/[]）后将 ai_gold 复制为 gold、保存为 extraction_gold.json，
   再运行 `python scripts/eval_extraction_f1.py --gold data/eval/extraction_gold.json`
   得最终字段级 F1

口径说明：AI 预填草稿仅供人工快速确认，不直接作为 gold（否则评测退化为
LLM 抽 vs LLM 抽，F1 虚高）；人工核对是评测可信度的前提。

用法:
    python scripts/prefill_gold.py [--template data/eval/extraction_gold_template.json]
        [--out data/eval/extraction_gold.prefill.json]
输出: data/eval/extraction_gold.prefill.json（AI 预填草稿）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.extraction_agent import _SYSTEM_PROMPT, ExtractionAgent  # noqa: E402
from src.common.config import DATA_DIR  # noqa: E402
from src.common.llm import llm_available, llm_chat_json, model_name  # noqa: E402

GOLD_TEMPLATE = DATA_DIR / "eval" / "extraction_gold_template.json"
GOLD_PREFILL = DATA_DIR / "eval" / "extraction_gold.prefill.json"
_CHUNK_LIMIT = 6000  # 与 extraction_agent / eval_extraction_f1 的输入截断一致


def _load_items(template_path: Path) -> list[dict]:
    """读取标注模板 items（chunk + 空 gold）。"""
    data = json.loads(template_path.read_text(encoding="utf-8"))
    return data.get("items", [])


def _prefill_one(chunk: str) -> dict | None:
    """LLM 五段式抽取单条 chunk → gold 骨架（宽松对齐，允许 null）。

    与主链路 `_parse_llm_output` 不同：gold 草稿场景容忍 `formula: null`
    （chunk 无明确材料时 LLM 输出 null 是合法 gold，人工可补填/确认空），
    因此不走 `ExtractionRecord.model_validate` 严格校验（其 formula 必填）。
    """
    raw = llm_chat_json(_SYSTEM_PROMPT, ExtractionAgent._user_prompt(chunk[: _CHUNK_LIMIT]))
    if not raw or "material" not in raw:
        return None
    material = raw.get("material") or {}
    structure = material.get("structure") if isinstance(material, dict) else None
    structure = structure if isinstance(structure, dict) else {}
    synthesis = raw.get("synthesis") if isinstance(raw.get("synthesis"), dict) else {}
    return {
        "material": {
            "formula": material.get("formula") if isinstance(material, dict) else None,
            "composition": material.get("composition") if isinstance(material, dict) else None,
            "structure": {
                "space_group": structure.get("space_group"),
                "lattice": structure.get("lattice"),
                "phase": structure.get("phase"),
            },
        },
        "properties": raw.get("properties") or [],
        "methods": raw.get("methods") or [],
        "synthesis": {
            "precursors": synthesis.get("precursors"),
            "temperature": synthesis.get("temperature"),
            "atmosphere": synthesis.get("atmosphere"),
            "duration": synthesis.get("duration"),
        },
    }


def main() -> None:
    """入口：读模板 → LLM 预填 → 输出 AI 草稿（不覆盖 extraction_gold.json）。"""
    parser = argparse.ArgumentParser(description="AI 预填 gold 草稿（供人工核对）")
    parser.add_argument("--template", type=str, default=str(GOLD_TEMPLATE))
    parser.add_argument("--out", type=str, default=str(GOLD_PREFILL))
    args = parser.parse_args()

    if not llm_available():
        raise SystemExit("LLM 未配置（LLM_API_KEY/OPENAI_API_KEY/DEEPSEEK_API_KEY），无法预填")

    template_path = Path(args.template)
    items = _load_items(template_path)
    if not items:
        raise SystemExit(f"{template_path} 无 items")

    prefilled: list[dict] = []
    n_ok = n_empty = 0
    for it in items:
        chunk = (it.get("chunk") or "").strip()
        if not chunk:
            continue
        ai_gold = _prefill_one(chunk)
        if ai_gold is None:
            n_empty += 1
        else:
            n_ok += 1
        prefilled.append(
            {
                "idx": it.get("idx"),
                "doc_id": it.get("doc_id"),
                "chunk": chunk[:800],
                "ai_gold": ai_gold,
                "instruction": (
                    "人工核对：仅保留 chunk 中明确提到的信息；LLM 可能幻觉，"
                    "未提及字段请改回 null/[]。核对后将 ai_gold 复制为 gold，"
                    "保存为 data/eval/extraction_gold.json 后运行 "
                    "python scripts/eval_extraction_f1.py --gold data/eval/extraction_gold.json"
                ),
            }
        )

    payload = {
        "dataset": "extraction_f1_prefill",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "llm_model": model_name(),
        "n_items": len(prefilled),
        "n_ok": n_ok,
        "n_empty": n_empty,
        "note": "AI 预填草稿，非最终 gold；人工核对后另存为 extraction_gold.json",
        "items": prefilled,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"AI 预填草稿已生成：{out_path}（{n_ok} 条成功，{n_empty} 条空）")
    print("下一步：人工逐条核对 ai_gold → 另存为 data/eval/extraction_gold.json → "
          "python scripts/eval_extraction_f1.py --gold data/eval/extraction_gold.json")


if __name__ == "__main__":
    main()

"""基本任务评测①：LLM 抽取 vs 规则抽取 字段级 F1 对比。

对齐 `.trae/rules/00-project-rules.md` 7.2 与 `DEVELOPMENT-GUIDE.md` 6.1
「抽取质量：字段级 F1、准确率（对照人工标注的抽取结果）」。

评测口径：
- 输入：检索产物（results/retrieval_*.json，默认最新）中按 doc_id 去重取前 N 条 chunk
- 双路径：LLM 抽取（五段式 schema，`_SYSTEM_PROMPT`）vs 规则抽取（`rule_based_extract`）
- gold 来源（两种模式）：
  - `--gold data/eval/extraction_gold.json`：人工标注 gold → 直接算 F1
  - 缺省：以 LLM 抽取为「参考 gold」（provisional），量化规则式相对 LLM 的字段损失，
    同时生成 `data/eval/extraction_gold_template.json` 标注模板供人工填写
- 字段对齐语义：规则式不产出的字段（structure/methods/atmosphere/duration）
  按「空-空跳过、gold 有 pred 无 → fn」处理，见 src/evaluation/f1.py

用法:
    python scripts/eval_extraction_f1.py [检索产物.json] [--limit 10] [--gold 文件]
输出: results/eval/extraction_f1_<ts>.json（含 per_field/micro/macro/per_sample）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.extraction_agent import _SYSTEM_PROMPT, ExtractionAgent
from src.common.config import DATA_DIR
from src.common.llm import llm_available, llm_chat_json, model_name
from src.evaluation.f1 import extraction_f1
from src.extraction.extractor import rule_based_extract

EVAL_DIR = Path(__file__).resolve().parents[1] / "results" / "eval"
GOLD_TEMPLATE = DATA_DIR / "eval" / "extraction_gold_template.json"
GOLD_PATH = DATA_DIR / "eval" / "extraction_gold.json"
_CHUNK_LIMIT = 6000  # 与 extraction_agent 的输入截断一致


def _latest_retrieval() -> Path:
    """results/ 下最新的热电领域 retrieval_*.json（按 mtime；无热电文件则最新任意）。"""
    files = sorted(
        Path(__file__).resolve().parents[1].glob("results/retrieval_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise SystemExit("未找到 results/retrieval_*.json，请先运行 scripts/run_retrieval.py")
    for f in files:
        try:
            query = json.loads(f.read_text(encoding="utf-8")).get("query", "")
        except (OSError, json.JSONDecodeError):
            continue
        if "thermoelectric" in str(query).lower():
            return f
    return files[0]


def _empty_pred() -> dict:
    """抽取失败（LLM schema 失败 / 规则未检出）时的空预测记录。"""
    return {
        "material": {"formula": None, "composition": None,
                     "structure": {"space_group": None, "lattice": None, "phase": None}},
        "properties": [],
        "methods": [],
        "synthesis": {"precursors": None, "temperature": None,
                      "atmosphere": None, "duration": None},
    }


def _llm_extract(agent: ExtractionAgent, text: str, doc_id: str, doi: str | None, page) -> dict:
    """LLM 抽取路径：复用 extraction_agent 的 prompt/解析（不落库不验证）。"""
    raw = llm_chat_json(_SYSTEM_PROMPT, agent._user_prompt(text))
    rec = agent._parse_llm_output(raw, doc_id=doc_id, doi=doi, page=page)
    return rec.model_dump() if rec is not None else _empty_pred()


def _rule_extract(text: str, doc_id: str) -> dict:
    """规则式抽取路径（降级实现，不落库）。"""
    rec = rule_based_extract(text, doc_id=doc_id)
    return rec.model_dump() if rec is not None else _empty_pred()


def _load_gold(path: Path) -> list[dict] | None:
    """加载人工 gold（items[].gold 列表）。"""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return [item["gold"] for item in data.get("items", [])]


def _write_gold_template(items: list[dict]) -> None:
    """生成人工标注模板（chunk 前 800 字符 + 空 gold 五段式）。"""
    GOLD_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset": "extraction_f1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "instruction": (
            "对每条 chunk 标注 gold 抽取结果（五段式 schema）。只标 chunk 中明确提到的信息，"
            "未提及字段留 null/[]。填写完成后保存为 data/eval/extraction_gold.json 再运行本脚本。"
            "properties.name 建议使用 zT/band gap/Seebeck coefficient/thermal conductivity/"
            "electrical conductivity/power factor 等标准名。"
        ),
        "items": [
            {
                "idx": item["idx"],
                "doc_id": item["doc_id"],
                "chunk": item["chunk"][:800],
                "gold": {
                    "material": {
                        "formula": None, "composition": None,
                        "structure": {"space_group": None, "lattice": None, "phase": None},
                    },
                    "properties": [],
                    "methods": [],
                    "synthesis": {"precursors": None, "temperature": None,
                                  "atmosphere": None, "duration": None},
                },
            }
            for item in items
        ],
    }
    GOLD_TEMPLATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"gold 标注模板已生成：{GOLD_TEMPLATE}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 抽取 vs 规则抽取字段级 F1 评测")
    parser.add_argument("retrieval", nargs="?", default=None, help="检索产物 JSON（默认最新）")
    parser.add_argument("--limit", type=int, default=10,
                        help="参与评测的 chunk 数（按 doc_id 去重）")
    parser.add_argument("--gold", type=str, default=None,
                        help="人工 gold 文件（默认 data/eval/extraction_gold.json）")
    args = parser.parse_args()

    retrieval_path = Path(args.retrieval) if args.retrieval else _latest_retrieval()
    data = json.loads(retrieval_path.read_text(encoding="utf-8"))
    papers = data.get("papers", [])
    # 按 doc_id 去重取前 limit 条
    seen: set[str] = set()
    samples: list[dict] = []
    for p in papers:
        doc_id = p.get("doc_id") or ""
        if doc_id in seen:
            continue
        seen.add(doc_id)
        samples.append(p)
        if len(samples) >= args.limit:
            break
    if not samples:
        raise SystemExit(f"检索产物 {retrieval_path} 无 papers 数据")

    gold_path = Path(args.gold) if args.gold else GOLD_PATH
    gold = _load_gold(gold_path)
    llm_ok = llm_available()
    mode = "gold" if gold is not None else ("llm_reference" if llm_ok else "unavailable")

    agent = ExtractionAgent()
    gold_records: list[dict] = []
    pred_records: list[dict] = []
    per_sample_meta: list[dict] = []
    llm_fail = rule_fail = 0
    for i, paper in enumerate(samples):
        text = (paper.get("chunk") or "")[:_CHUNK_LIMIT]
        doc_id = paper.get("doc_id")
        doi = paper.get("doi")
        page = paper.get("page_no")
        meta = {"idx": i, "doc_id": doc_id, "chunk": text[:200]}
        # 双路径抽取
        if mode == "unavailable":
            rule_pred = _rule_extract(text, doc_id)
            pred_records.append(rule_pred)
            rule_fail += 1 if _is_empty(rule_pred) else 0
        else:
            try:
                llm_pred = _llm_extract(agent, text, doc_id, doi, page)
            except Exception as exc:
                llm_fail += 1
                llm_pred = _empty_pred()
                meta["llm_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            rule_pred = _rule_extract(text, doc_id)
            rule_fail += 1 if _is_empty(rule_pred) else 0
            if mode == "llm_reference":
                gold_records.append(llm_pred)
            pred_records.append(rule_pred)
            meta["llm_extracted"] = not _is_empty(llm_pred)
            meta["rule_extracted"] = not _is_empty(rule_pred)
        per_sample_meta.append(meta)

    if mode == "unavailable":
        _write_gold_template(per_sample_meta)
        print("LLM 不可用：仅生成 gold 标注模板，未运行对比评测（配置 LLM key 后重跑）")
        return

    result = extraction_f1(gold_records, pred_records)
    result.update(
        {
            "mode": mode,
            "n_samples": len(samples),
            "retrieval_path": str(retrieval_path),
            "llm_available": llm_ok,
            "llm_model": model_name() if llm_ok else None,
            "llm_fail": llm_fail,
            "rule_fail": rule_fail,
            "samples_meta": per_sample_meta,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "note": (
                "gold 模式：对照人工标注；llm_reference 模式：以 LLM 输出为参考 gold，"
                "衡量规则式相对 LLM 的字段损失（provisional，待人工 gold 替换）"
                if mode == "llm_reference" else "对照人工 gold"
            ),
        }
    )
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / f"extraction_f1_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台汇总
    print(f"模式：{mode}｜样本：{len(samples)}｜LLM 失败：{llm_fail}｜规则未检出：{rule_fail}")
    print(f"{'字段':<12}{'TP':>4}{'FP':>4}{'FN':>4}{'P':>8}{'R':>8}{'F1':>8}")
    for field, m in result["per_field"].items():
        print(f"{field:<12}{m['tp']:>4}{m['fp']:>4}{m['fn']:>4}"
              f"{m['precision']:>8.4f}{m['recall']:>8.4f}{m['f1']:>8.4f}")
    micro = result["micro"]
    macro = result["macro"]
    print(f"{'micro':<12}{'':>12}{'':>4}{'':>4}{micro['precision']:>8.4f}{micro['recall']:>8.4f}{micro['f1']:>8.4f}")
    print(f"{'macro':<12}{'':>12}{'':>4}{'':>4}{macro['precision']:>8.4f}{macro['recall']:>8.4f}{macro['f1']:>8.4f}")
    print(f"结果落盘：{out_path}")
    if mode == "llm_reference":
        _write_gold_template(per_sample_meta)


def _is_empty(rec: dict) -> bool:
    """判断抽取记录是否为空（未检出任何信息）。"""
    material = rec.get("material") or {}
    return not material.get("formula") and not rec.get("properties") and not rec.get("methods")


if __name__ == "__main__":
    main()

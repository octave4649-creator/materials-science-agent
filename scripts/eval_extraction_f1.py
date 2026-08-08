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


def _is_thermo_payload(payload: dict) -> bool:
    """判断检索产物是否热电领域（query 或任一论文标题含 thermoelectric）。"""
    if "thermoelectric" in str(payload.get("query") or "").lower():
        return True
    for p in (payload.get("papers") or [])[:20]:
        if "thermoelectric" in str(p.get("title") or "").lower():
            return True
    return False


def _latest_retrieval(gold: dict[str, dict] | None = None) -> Path:
    """选择检索产物，优先级：显式传参 > gold doc_id 命中数最多 > 最新热电 > 最新任意。

    参数:
        gold: 人工 gold（按 doc_id 索引）。gold 模式必须选与 gold 配对的产物，
              否则 doc_id 全不匹配 → 全部样本被跳过、F1 全 0（历史踩坑）。
    """
    files = sorted(
        Path(__file__).resolve().parents[1].glob("results/retrieval_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise SystemExit("未找到 results/retrieval_*.json，请先运行 scripts/run_retrieval.py")
    if gold:
        best, best_n = None, 0
        for f in files:
            try:
                papers = json.loads(f.read_text(encoding="utf-8")).get("papers", [])
            except (OSError, json.JSONDecodeError):
                continue
            n = sum(1 for p in papers if (p.get("doc_id") or "") in gold)
            if n > best_n:
                best, best_n = f, n
        if best is not None:
            if best_n < len(gold):
                print(f"警告：{best.name} 命中 {best_n}/{len(gold)} 条 gold，"
                      f"缺失样本将被跳过（gold_missing_skipped）")
            return best
        raise SystemExit("gold 文件的 doc_id 未命中任何检索产物，请显式指定检索产物 JSON")
    for f in files:
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _is_thermo_payload(payload):
            print(f"热电检索产物：{f.name}")
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


def _load_gold(path: Path) -> dict[str, dict] | None:
    """加载人工 gold（items[].gold，按 doc_id 索引便于匹配）。"""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    gold_map: dict[str, dict] = {}
    for item in data.get("items", []):
        if item.get("doc_id"):
            gold_map[item["doc_id"]] = item["gold"]
    return gold_map


def _write_gold_template(samples: list[dict], llm_by_doc: dict[str, dict] | None = None) -> None:
    """生成人工标注模板（完整 chunk + 空 gold 五段式，可选 AI 预填）。

    参数:
        samples: 检索产物样本（含完整 chunk / doc_id，已 doc_id 去重）。
        llm_by_doc: {doc_id: LLM 抽取结果}，非空时用 LLM 输出预填 gold
                    （provisional，标注 ai_prefilled=true，人工仅需复核修正）。

    过滤空 chunk 样本（无证据片段无法标注），跳过数量在控制台留痕。
    """
    valid = [s for s in samples if (s.get("chunk") or "").strip()]
    n_skipped = len(samples) - len(valid)
    GOLD_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for i, s in enumerate(valid):
        doc_id = s.get("doc_id")
        prefill = (llm_by_doc or {}).get(doc_id or "")
        gold = _empty_pred()
        prefilled = False
        if prefill and not _is_empty(prefill):
            gold = prefill
            prefilled = True
        item: dict = {
            "idx": i,
            "doc_id": doc_id,
            "chunk": s["chunk"][:800],
            "gold": gold,
            "ai_prefilled": prefilled,
        }
        if prefilled:
            item["prefill_note"] = (
                "AI 预填：gold 初稿来自 LLM 抽取结果（provisional），"
                "请对照 chunk 原文复核修正后保存为 data/eval/extraction_gold.json"
            )
        items.append(item)
    payload = {
        "dataset": "extraction_f1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "instruction": (
            "对每条 chunk 复核 gold 抽取结果（五段式 schema）。只保留 chunk 中明确提到的信息，"
            "未提及字段留 null/[]。ai_prefilled=true 的条目为 AI 预填初稿，请对照原文复核修正。"
            "填写完成后保存为 data/eval/extraction_gold.json 再运行本脚本。"
            "properties.name 建议使用 zT/band gap/Seebeck coefficient/thermal conductivity/"
            "electrical conductivity/power factor 等标准名。"
        ),
        "n_skipped_no_chunk": n_skipped,
        "items": items,
    }
    GOLD_TEMPLATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    n_prefill = sum(1 for it in items if it.get("ai_prefilled"))
    print(f"gold 标注模板已生成：{GOLD_TEMPLATE}（{len(valid)} 条可标注，"
          f"跳过 {n_skipped} 条无 chunk 样本；AI 预填 {n_prefill} 条）")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 抽取 vs 规则抽取字段级 F1 评测")
    parser.add_argument("retrieval", nargs="?", default=None, help="检索产物 JSON（默认最新）")
    parser.add_argument("--limit", type=int, default=10,
                        help="参与评测的 chunk 数（按 doc_id 去重）")
    parser.add_argument("--gold", type=str, default=None,
                        help="人工 gold 文件（默认 data/eval/extraction_gold.json）")
    parser.add_argument("--ai-prefill", action="store_true",
                        help="模板生成时用 LLM 抽取结果预填 gold（provisional，人工复核修正）")
    args = parser.parse_args()

    gold_path = Path(args.gold) if args.gold else GOLD_PATH
    gold = _load_gold(gold_path)
    if gold is not None and not gold:
        gold = None  # gold 文件存在但无有效条目 → 视作未标注
    retrieval_path = Path(args.retrieval) if args.retrieval else _latest_retrieval(gold)
    data = json.loads(retrieval_path.read_text(encoding="utf-8"))
    papers = data.get("papers", [])
    # 按 doc_id 去重取前 limit 条（优先有 chunk 证据片段的论文，保证可标注）
    seen: set[str] = set()
    samples: list[dict] = []
    for p in sorted(
        papers, key=lambda x: 0 if (x.get("chunk") or "").strip() else 1
    ):
        doc_id = p.get("doc_id") or ""
        if doc_id in seen:
            continue
        seen.add(doc_id)
        samples.append(p)
        if len(samples) >= args.limit:
            break
    if not samples:
        raise SystemExit(f"检索产物 {retrieval_path} 无 papers 数据")

    llm_ok = llm_available()
    mode = "gold" if gold is not None else ("llm_reference" if llm_ok else "unavailable")

    agent = ExtractionAgent()
    gold_records: list[dict] = []
    pred_records: list[dict] = []
    llm_records: list[dict] = []  # gold 模式下 LLM 路径预测（与规则式并列对比）
    llm_by_doc: dict[str, dict] = {}  # llm_reference 模式：doc_id → LLM 抽取（供 AI 预填模板）
    per_sample_meta: list[dict] = []
    llm_fail = rule_fail = gold_missing_skipped = 0
    for i, paper in enumerate(samples):
        text = (paper.get("chunk") or "")[:_CHUNK_LIMIT]
        doc_id = paper.get("doc_id")
        doi = paper.get("doi")
        page = paper.get("page_no")
        meta = {"idx": i, "doc_id": doc_id, "chunk": text[:200]}
        # gold 模式：只评 gold 覆盖的样本（缺失 doc_id 跳过并留痕，不记空分）
        if mode == "gold" and (doc_id or "") not in (gold or {}):
            gold_missing_skipped += 1
            continue
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
            llm_by_doc[doc_id or ""] = llm_pred  # 供 --ai-prefill 模板预填
            if mode == "gold":
                gold_rec = gold.get(doc_id or "")
                if gold_rec is None:
                    meta["gold_missing"] = True
                    gold_rec = _empty_pred()
                gold_records.append(gold_rec)
                llm_records.append(llm_pred)  # LLM 路径与规则式并列对比
            elif mode == "llm_reference":
                gold_records.append(llm_pred)
            pred_records.append(rule_pred)
            meta["llm_extracted"] = not _is_empty(llm_pred)
            meta["rule_extracted"] = not _is_empty(rule_pred)
        per_sample_meta.append(meta)

    if mode == "unavailable":
        _write_gold_template(samples)
        print("LLM 不可用：仅生成 gold 标注模板，未运行对比评测（配置 LLM key 后重跑）")
        return

    result = extraction_f1(gold_records, pred_records)
    result.update(
        {
            "mode": mode,
            "n_samples": len(samples),
            "n_evaluated": len(gold_records),
            "gold_missing_skipped": gold_missing_skipped,
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
    if mode == "gold" and llm_ok and llm_records:
        result["llm_vs_gold"] = extraction_f1(gold_records, llm_records)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVAL_DIR / f"extraction_f1_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台汇总
    print(f"模式：{mode}｜样本：{len(samples)}（评估 {len(gold_records)}，"
          f"gold 缺失跳过 {gold_missing_skipped}）｜LLM 失败：{llm_fail}｜规则未检出：{rule_fail}")
    print(f"{'字段':<12}{'TP':>4}{'FP':>4}{'FN':>4}{'P':>8}{'R':>8}{'F1':>8}")
    for field, m in result["per_field"].items():
        print(f"{field:<12}{m['tp']:>4}{m['fp']:>4}{m['fn']:>4}"
              f"{m['precision']:>8.4f}{m['recall']:>8.4f}{m['f1']:>8.4f}")
    micro = result["micro"]
    macro = result["macro"]
    print(f"{'micro':<12}{'':>12}{'':>4}{'':>4}{micro['precision']:>8.4f}{micro['recall']:>8.4f}{micro['f1']:>8.4f}")
    print(f"{'macro':<12}{'':>12}{'':>4}{'':>4}{macro['precision']:>8.4f}{macro['recall']:>8.4f}{macro['f1']:>8.4f}")
    if mode == "gold" and "llm_vs_gold" in result:
        llm_m = result["llm_vs_gold"]
        print(
            f"LLM vs gold：micro F1={llm_m['micro']['f1']:.4f}"
            f"｜macro F1={llm_m['macro']['f1']:.4f}"
        )
    print(f"结果落盘：{out_path}")
    if mode == "llm_reference":
        _write_gold_template(samples, llm_by_doc if args.ai_prefill else None)


def _is_empty(rec: dict) -> bool:
    """判断抽取记录是否为空（未检出任何信息）。"""
    material = rec.get("material") or {}
    return not material.get("formula") and not rec.get("properties") and not rec.get("methods")


if __name__ == "__main__":
    main()

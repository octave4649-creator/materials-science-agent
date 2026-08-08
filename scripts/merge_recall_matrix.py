"""基本任务评测③辅助：四算法召回率统一对比矩阵合并。

背景（对齐五次深度开发「LLM 模式召回率」）：`eval_recall.py` 每次运行输出单算法
结果（results/eval/recall_*.json，含 algo_summary）。夜间批量把四算法 × 规则/LLM
模式跑完后，本脚本合并为统一对比矩阵，供实验报告与复赛答辩直接引用。

聚合规则：
- 每份 recall_*.json 提取 (algo, llm_on) 与 algo_summary
- 同一 (algo, llm_on) 出现多份文件时，取 n_facts 最大者（全量优先）；
  并列时取文件名时间戳最新者，其余文件在 detail 中留痕
- 输出：控制台 Markdown 表格 + results/eval/recall_matrix_<ts>.json

用法:
    python scripts/merge_recall_matrix.py [--inputs 文件1 文件2 ...]
        [--out results/eval/recall_matrix.json] [--no-print]
输出: results/eval/recall_matrix_<ts>.json（含 matrix / detail / 缺失算法提示）

复赛夜间批量命令（四算法 × 规则/LLM 统一口径）:
    # 1) 召回率全量 16 条 LLM 模式（每算法一条；BO 用 --bo-dopants 5 控成本）
    python scripts/eval_recall.py --algo ga --llm
    python scripts/eval_recall.py --algo mcts --llm
    python scripts/eval_recall.py --algo bo --llm --bo-dopants 5
    python scripts/eval_recall.py --algo sr --llm
    # 2) 合并统一对比矩阵（规则模式 16 条基线已存在，自动并入）
    python scripts/merge_recall_matrix.py
    # 3) OQMD 全库验证扩面（oracle 真值表自动纳入：VerificationOracle.load()
    #    扫描全部 validation 产物，无需新代码）
    python scripts/run_search.py --top-n 29 --generations 2 --pop-size 10
    python scripts/run_validation.py            # 全量验证（或 --limit N 增量）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_EVAL_DIR = Path(__file__).resolve().parents[1] / "results" / "eval"
_ALGOS = ("ga", "mcts", "bo", "sr")
_ALGO_NAMES = {"ga": "GA", "mcts": "MCTS", "bo": "BO", "sr": "SR"}


def _algos_of(payload: dict) -> list[str]:
    """从 algo_summary 推断算法列表（`--algo all` 的文件含全部四算法）。"""
    summary = payload.get("algo_summary") or {}
    return [a for a in _ALGOS if a in summary]


def _ts(p: Path) -> str:
    """从文件名提取时间戳（如 recall_20260805T070151.json → 20260805T070151）。"""
    return p.stem.replace("recall_", "")


def _collect(inputs: list[Path]) -> dict[tuple[str, bool], dict]:
    """扫描 recall 文件 → {(algo, llm_on): 选中文件解析结果}（n_facts 最大优先）。

    多算法文件（`--algo all`）按算法拆分为独立记录；同 (algo, llm_on) 多份文件
    取 n_facts 最大者，并列取文件名时间戳最新者。
    """
    records: dict[tuple[str, bool], dict] = {}
    for p in inputs:
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        algos = _algos_of(payload)
        if not algos:
            continue
        llm_on = bool(payload.get("llm_on"))
        n_facts = int(payload.get("n_facts") or 0)
        summary = payload.get("algo_summary") or {}
        for algo in algos:
            key = (algo, llm_on)
            cur = records.get(key)
            if cur is None or n_facts > cur["n_facts"] or (
                n_facts == cur["n_facts"] and _ts(p) > cur["file_ts"]
            ):
                records[key] = {
                    "algo": algo,
                    "llm_on": llm_on,
                    "n_facts": n_facts,
                    "model": payload.get("llm_model"),
                    "summary": summary.get(algo, {}),
                    "file": p.name,
                    "file_ts": _ts(p),
                }
    return records


def _matrix_row(rec: dict) -> dict:
    """单算法行 → 矩阵列（recall@1/3/5/coverage/n_candidates_avg）。"""
    s = rec["summary"]
    return {
        "algo": rec["algo"],
        "algo_name": _ALGO_NAMES.get(rec["algo"], rec["algo"]),
        "mode": "LLM" if rec["llm_on"] else "规则",
        "model": rec["model"],
        "n_facts": rec["n_facts"],
        "recall@1": round(float(s.get("recall@1", 0.0)), 4),
        "recall@3": round(float(s.get("recall@3", 0.0)), 4),
        "recall@5": round(float(s.get("recall@5", 0.0)), 4),
        "coverage": round(float(s.get("coverage", 0.0)), 4),
        "n_candidates_avg": round(float(s.get("n_candidates_avg", 0.0)), 2),
        "file": rec["file"],
    }


def _print_table(rows: list[dict]) -> None:
    """控制台 Markdown 表格输出。"""
    header = ("算法 | 模式 | 模型 | n_facts | recall@1 | recall@3 | recall@5 | "
              "coverage | n_cand_avg | 文件")
    print(header)
    print("--- | --- | --- | --- | --- | --- | --- | --- | --- | ---")
    for r in rows:
        print(
            f"{r['algo_name']} | {r['mode']} | {r['model'] or '-'} | {r['n_facts']} | "
            f"{r['recall@1']:.3f} | {r['recall@3']:.3f} | {r['recall@5']:.3f} | "
            f"{r['coverage']:.3f} | {r['n_candidates_avg']} | {r['file']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="四算法召回率统一对比矩阵合并")
    parser.add_argument("--inputs", nargs="*", default=None,
                        help="recall_*.json 路径（默认扫描 results/eval/recall_*.json）")
    parser.add_argument("--out", type=str, default=None,
                        help="输出路径（默认 results/eval/recall_matrix_<ts>.json）")
    parser.add_argument("--no-print", action="store_true", help="仅落盘不打印表格")
    args = parser.parse_args()

    inputs = [Path(p) for p in args.inputs] if args.inputs else sorted(
        _EVAL_DIR.glob("recall_*.json")
    )
    if not inputs:
        raise SystemExit("未找到 recall_*.json，请先运行 scripts/eval_recall.py")

    records = _collect(inputs)
    if not records:
        raise SystemExit("recall 文件中均无法识别算法名（algo_summary 缺失）")

    rows = sorted(
        (_matrix_row(rec) for rec in records.values()),
        key=lambda r: (not r["mode"] == "LLM", _ALGOS.index(r["algo"])),
    )
    _print_table(rows)
    missing = [a for a in _ALGOS if (a, True) not in records]
    if missing:
        print(f"\n缺 LLM 模式算法：{['/'.join(_ALGO_NAMES[m] for m in missing)]} "
              f"（运行 python scripts/eval_recall.py --algo <name> --llm 补齐）")

    payload = {
        "dataset": "recall_matrix",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_algo_mode": len(rows),
        "matrix": rows,
        "detail": {f"{k[0]}_{'llm' if k[1] else 'rule'}": v for k, v in records.items()},
        "missing_llm": missing,
        "note": "四算法召回率统一对比矩阵：同一 (algo, mode) 多份文件取 n_facts 最大者；"
                "hit@k 度量评分排序质量，coverage 度量探索覆盖率（两口径分离）",
    }
    out_path = Path(args.out) if args.out else (
        _EVAL_DIR / f"recall_matrix_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n对比矩阵已落盘：{out_path}")


if __name__ == "__main__":
    main()

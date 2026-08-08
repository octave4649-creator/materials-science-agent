"""OQMD 真值表自动扩面 CLI：聚合母体池 → OQMD 批量直查 → oracle 真值表落盘。

背景（进度计划「复赛深化剩余①」）：oracle 真值表目前仅来自历史
validation_*.json（220 条 / 15 母体，取决于搜索候选是否被验证）。本脚本
从 gaps.json（gaps[].formulas + known_facts[].host）与 findings 产物
（top_candidates[].host）**主动聚合全部母体池**，对整数母体批量 OQMD 直查，
自动纳入 oracle 真值表——不依赖候选是否被搜索覆盖，扩面即重跑消融的
「真值表覆盖偏置」缓解（LLM 融合增益 -8.93% 的成因修复路径）。

用法:
    python scripts/expand_oracle_truth.py [--gaps data/gaps.json]
        [--findings results/findings] [--out results/oracle]
        [--limit 3] [--timeout 15]
输出: results/oracle/oracle_truth_<ts>.json（结构对齐 validation 产物，
      VerificationOracle.load_oracle_truth 直接读取）
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DATA_DIR, RESULTS_DIR
from src.validation.oqmd_client import OQMDClient
from src.validation.parent_parser import parse_integer_parent, parse_variable_parent

GAPS_PATH = DATA_DIR / "gaps.json"
FINDINGS_DIR = RESULTS_DIR / "findings"
OUT_DIR = RESULTS_DIR / "oracle"


def _integer_formula(text: str) -> str:
    """文本 → 可直查整数成分：整数式原样；分数/变量式解析名义母体。

    返回 None 表示无法得到整数成分（不查询，留痕验证失败）。
    """
    t = (text or "").strip()
    if not t:
        return ""
    if "0." in t:  # 分数掺杂式 → 名义母体
        return parse_integer_parent(t) or ""
    if "x" in t or "y" in t:  # 变量式占位 → 名义母体
        return parse_variable_parent(t) or ""
    return t


def collect_host_pool(gaps_path: Path, findings_dir: Path) -> list[str]:
    """聚合母体池（去重保序）：gaps formulas + known_facts host + findings host。"""
    pool: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        t = (text or "").strip()
        if t and t not in seen:
            seen.add(t)
            pool.append(t)

    gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
    for g in gaps.get("gaps") or []:
        for f in g.get("formulas") or []:
            add(_integer_formula(f))
    for kf in gaps.get("known_facts") or []:
        add(_integer_formula(kf.get("host") or ""))
    if findings_dir.is_dir():
        for path in sorted(findings_dir.glob("finding_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for cand in data.get("top_candidates") or []:
                add(_integer_formula(cand.get("host") or ""))
    return [h for h in pool if h]


def expand_oracle(gaps_path: Path, findings_dir: Path, out_dir: Path, limit: int) -> Path:
    """母体池 → OQMD 批量直查 → oracle 真值表落盘，返回产物路径。"""
    hosts = collect_host_pool(gaps_path, findings_dir)
    client = OQMDClient()
    results: list[dict] = []
    failures: list[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    for host in hosts:
        try:
            entries = client.query_formation_energy(host, limit=limit)
        except Exception as exc:  # noqa: BLE001 - 单母体失败不中断批量
            failures.append(f"{host}: {exc}")
            continue
        if not entries:
            failures.append(f"{host}: 未收录/无法查询")
            results.append(
                {
                    "candidate_formula": host, "host": host,
                    "parent_formula": None, "verdict": "验证失败",
                    "reason": "OQMD 未收录或查询失败（如实留痕）", "entries": [],
                }
            )
            continue
        best = min(
            entries,
            key=lambda e: (e.stability if e.stability is not None else 1e9,
                           e.delta_e if e.delta_e is not None else 1e9),
        )
        stable = best.is_stable
        if stable is None:
            verdict = "验证失败"
        elif stable:
            verdict = "已知"
        else:
            verdict = "反例"
        results.append(
            {
                "candidate_formula": host, "host": host,
                "parent_formula": host, "verdict": verdict,
                "reason": (
                    f"OQMD 自动扩面直查：hull={best.stability} eV/atom, "
                    f"delta_e={best.delta_e} eV/atom（{verdict}）"
                ),
                "entries": [e.model_dump() for e in entries],
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"oracle_truth_{ts}.json"
    out_path.write_text(
        json.dumps(
            {
                "generated_at": ts,
                "source": "oracle_expansion",
                "n_hosts": len(hosts),
                "n_results": len(results),
                "n_failures": len(failures),
                "failures": failures[:50],
                "results": results,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return out_path


def main() -> int:
    """入口：聚合母体池 → OQMD 直查 → 落盘 + 控制台汇总。"""
    argv = sys.argv[1:]
    gaps_path = Path(argv[argv.index("--gaps") + 1]) if "--gaps" in argv else GAPS_PATH
    findings_dir = (
        Path(argv[argv.index("--findings") + 1]) if "--findings" in argv else FINDINGS_DIR
    )
    out_dir = Path(argv[argv.index("--out") + 1]) if "--out" in argv else OUT_DIR
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 3

    hosts = collect_host_pool(gaps_path, findings_dir)
    print(f"母体池：{len(hosts)} 个整数母体（去重后）")
    for i, h in enumerate(hosts, 1):
        print(f"  {i:>2}. {h}")
    out_path = expand_oracle(gaps_path, findings_dir, out_dir, limit)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    verdicts: dict[str, int] = {}
    for r in data["results"]:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
    print(f"\nOQMD 直查完成：{data['n_results']} 结果 / {data['n_failures']} 失败")
    print(f"判定分布：{verdicts}")
    print(f"oracle 真值表落盘：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

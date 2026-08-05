"""验证 Agent（模块 6）：对路线 A 候选做数据库交叉验证。

流水线位置：搜索 Agent（模块 5，findings）→ 验证 Agent（本模块）→ 报告（模块 4）。
输入：results/findings/finding_*.json 的 top_candidates。
输出：results/validation/validation_*.json（三类判定 + 证据链），审计日志落 results/logs/。

判定逻辑（对齐 `.trae/rules/03-materials-databases.md` 7.2）：
- 母体在库且稳定（hull ≤ 0.1 且 delta_e < 0）→ 已知（基础体系已收录）
- 母体在库但热力学不稳定 → 反例（与预期矛盾，负结果也入库）
- 母体不在库 → 新知（库中无此体系，掺杂方案为潜在新发现）
- 查询失败/分数成分无法直查 → 验证失败（明确标注，不伪装结论）
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.config import RESULTS_DIR
from src.common.logging import AuditLogger
from src.validation.mp_client import mp_available, query_summary
from src.validation.oqmd_client import OQMDClient
from src.validation.parent_parser import parse_integer_parent
from src.validation.schemas import DBEntry, PropertyCheck, VerificationResult

# 分数成分正则（母体为分数掺杂公式时 OQMD 直查受限）
_FRACTION_RE = re.compile(r"\d\.\d")


def _default_findings_dir() -> Path:
    """默认发现目录。"""
    return RESULTS_DIR / "findings"


def _default_output_dir() -> Path:
    """默认验证结果目录。"""
    return RESULTS_DIR / "validation"


def _validate_candidate(
    cand: dict[str, Any],
    oqmd: OQMDClient,
    *,
    use_mp: bool,
) -> VerificationResult:
    """对单个候选做数据库交叉验证（OQMD 必查，MP 可用时增强）。"""
    formula = cand.get("formula", "")
    host = cand.get("host", "") or ""
    dopant = cand.get("dopant")
    conc = cand.get("concentration")
    entries: list[DBEntry] = []
    checks: list[PropertyCheck] = []

    # 分数母体（已掺杂公式）直查受限 → A/B 位拆分解析整数母体后重验
    parent: str | None = None
    if _FRACTION_RE.search(host):
        parent = parse_integer_parent(host)
        if parent is None:
            return VerificationResult(
                candidate_formula=formula,
                host=host,
                dopant=dopant,
                concentration=conc,
                verdict="验证失败",
                reason=(
                    f"母体 {host} 为分数掺杂成分且无法解析出整数母体，"
                    "OQMD 直查易超时（见 exp.md）；需提供纯母体化学式后重验"
                ),
                novel_dopant=bool(dopant),
            )
        query_formula = parent
    else:
        query_formula = host

    # 1) OQMD 主路径（分数宿主走解析出的整数母体）
    oqmd_entry = oqmd.best_entry(query_formula)
    if oqmd_entry is not None:
        entries.append(oqmd_entry)

    # 2) MP 增强路径（有 Key 时）
    if use_mp:
        hits = query_summary(query_formula)
        if hits is not None:
            for h in hits[:3]:
                entries.append(
                    DBEntry(
                        db="mp",
                        formula=h.get("formula") or query_formula,
                        entry_id=h.get("material_id"),
                        delta_e=h.get("formation_energy_per_atom"),
                        stability=h.get("energy_above_hull"),
                        band_gap=h.get("band_gap"),
                        is_stable=h.get("is_stable"),
                        source_url=f"https://next-gen.materialsproject.org/materials/{h.get('material_id')}",
                    )
                )

    if not entries:
        # 库中未收录 → 新知
        checks.append(
            PropertyCheck(
                property="existence",
                expected=None,
                db_value=None,
                consistent=True,
                note=(
                    f"OQMD{'/MP' if use_mp else ''} 均未收录母体 {query_formula}，"
                    "成分空间未被数据库覆盖"
                ),
            )
        )
        return VerificationResult(
            candidate_formula=formula,
            host=host,
            parent_formula=parent,
            dopant=dopant,
            concentration=conc,
            verdict="新知",
            reason=(
                f"母体 {query_formula} 不在数据库中，掺杂方案 {formula} "
                "为库外假设，需实验/更高精度验证"
            ),
            checks=checks,
            entries=[],
            novel_dopant=bool(dopant),
        )

    # 库中存在 → 稳定性判定
    best = entries[0]
    stable = best.is_stable
    if stable is None:
        hull = best.stability if best.stability is not None else 0.0
        delta_e = best.delta_e if best.delta_e is not None else 0.0
        stable = hull <= 0.1 and delta_e < 0
    checks.append(
        PropertyCheck(
            property="stability",
            expected="热力学稳定（hull≤0.1 eV/atom）",
            db_value=(
                f"hull={best.stability:.3f} eV/atom, "
                f"delta_e={best.delta_e:.3f} eV/atom" if best.stability is not None
                else "无 hull 数据"
            ),
            consistent=bool(stable),
            note=f"来源 {best.db}（{best.formula}）",
        )
    )
    if best.band_gap is not None:
        checks.append(
            PropertyCheck(
                property="band_gap",
                expected=None,
                db_value=f"{best.band_gap:.2f} eV",
                consistent=True,
                note="DFT 带隙仅供参考（泛函低估 30-50%，见 03-materials-databases.md）",
            )
        )

    verdict = "已知" if stable else "反例"
    reason = (
        f"母体 {query_formula} 在 {best.db} 中已收录且热力学稳定，基础体系得到支撑"
        if stable else
        f"母体 {query_formula} 在 {best.db} 中热力学不稳定（hull 或形成能为正），"
        "该掺杂方向与数据库结论矛盾，建议评估替代母体"
    )
    if parent:
        reason += f"；{host} 为分数掺杂宿主，按 A/B 位拆分解析整数母体 {parent} 后重验"
    if dopant and stable:
        verdict = "已知"
        reason += f"；掺杂成分 {formula} 为库外扩展（novel_dopant）"
    return VerificationResult(
        candidate_formula=formula,
        host=host,
        parent_formula=parent,
        dopant=dopant,
        concentration=conc,
        verdict=verdict,
        reason=reason,
        checks=checks,
        entries=entries,
        novel_dopant=bool(dopant),
    )


class ValidationAgent:
    """数据库交叉验证 Agent（OQMD 主 + MP 增强）。"""

    def __init__(
        self,
        *,
        findings_dir: str | Path | None = None,
        output_dir: str | Path | None = None,
        logger: AuditLogger | None = None,
    ) -> None:
        """初始化。

        参数:
            findings_dir: 模块 5 发现目录（默认 results/findings/）
            output_dir: 验证结果目录（默认 results/validation/）
            logger: 审计日志器
        """
        self.findings_dir = Path(findings_dir) if findings_dir else _default_findings_dir()
        self.output_dir = Path(output_dir) if output_dir else _default_output_dir()
        self.logger = logger or AuditLogger("validation_agent")

    def run(self, *, use_mp: bool | None = None, limit: int | None = None) -> list[Path]:
        """对 findings 的 top 候选执行交叉验证并落盘。

        参数:
            use_mp: 是否启用 MP（默认按 mp_available 自动）
            limit: 最多验证的 finding 文件数（None = 全部）

        返回:
            落盘的验证结果文件列表。
        """
        if not self.findings_dir.exists():
            self.logger.log("validation_none", "success",
                            output_summary={"reason": f"无 findings 目录: {self.findings_dir}"})
            return []
        files = sorted(self.findings_dir.glob("finding_*.json"))
        if not files:
            self.logger.log("validation_none", "success",
                            output_summary={"reason": "无 finding_*.json"})
            return []
        if limit:
            files = files[:limit]
        use_mp = mp_available() if use_mp is None else use_mp
        oqmd = OQMDClient()
        self.logger.log(
            "validation_start",
            "success",
            input_summary={"n_findings": len(files), "use_mp": use_mp},
        )
        written: list[Path] = []
        for f in files:
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            candidates = payload.get("top_candidates") or []
            results = [
                _validate_candidate(c, oqmd, use_mp=use_mp).to_dict()
                for c in candidates
            ]
            self.output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            out_path = self.output_dir / f"validation_{ts}_{len(written) + 1}.json"
            out_path.write_text(
                json.dumps(
                    {
                        "source_finding": f.name,
                        "gap_statement": payload.get("gap_statement"),
                        "evidence_ids": payload.get("evidence_ids") or [],
                        "results": results,
                        "generated_at": ts,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            with self.logger.step(
                "validation_finding", input_summary={"file": f.name}
            ):
                pass
            self.logger.log(
                "validation_finding_done",
                "success",
                output_summary={
                    "file": f.name,
                    "n_candidates": len(results),
                    "verdicts": [r["verdict"] for r in results],
                    "out": str(out_path),
                },
            )
            written.append(out_path)
        return written

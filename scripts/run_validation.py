"""模块 6 演示脚本：findings → 数据库交叉验证（OQMD 主 + MP 增强）。

用法:
    python scripts/run_validation.py [--findings results/findings]
                                     [--limit 3] [--no-mp]
默认输入：results/findings/finding_*.json；默认输出：results/validation/validation_*.json。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.validation_agent import ValidationAgent  # noqa: E402
from src.common.logging import AuditLogger  # noqa: E402
from src.validation.mp_client import mp_available  # noqa: E402


def main() -> int:
    """入口。"""
    argv = sys.argv[1:]
    findings_arg = (
        argv[argv.index("--findings") + 1] if "--findings" in argv else None
    )
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    use_mp = False if "--no-mp" in argv else None

    agent = ValidationAgent(findings_dir=findings_arg)
    print(f"输入 findings: {agent.findings_dir}")
    mp_status = "关闭" if use_mp is False else (
        "可用" if mp_available() else "未配置 Key，跳过"
    )
    print(f"MP 增强: {mp_status}")
    paths = agent.run(use_mp=use_mp, limit=limit)
    if not paths:
        print("未找到可验证的 findings，请先运行 scripts/run_search.py")
        return 1
    for p in paths:
        print(f"落盘: {p}")
    print(f"日志: results/logs/{AuditLogger('validation_agent').agent}_*.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""模块 4 演示脚本：检索/知识库/Gap 产物 → 结构化调研报告（Markdown/HTML）。

用法:
    python scripts/run_report.py [--retrieval 检索输出.json] [--kb 知识库路径]
                          [--gaps Gap报告.json] [--validation-dir 验证目录] [--no-llm]
默认输入：results/ 最新 retrieval_*.json + data/knowledge_base.json + data/gaps.json。
默认验证目录：results/validation/（模块 6 产物，缺失时验证章节输出占位说明）。
默认输出：results/reports/report_{时间戳}.md/.html/.meta.json。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.report_agent import (
    DEFAULT_VALIDATION_DIR,
    ReportAgent,
)
from src.common.llm import llm_available, model_name


def _arg(argv: list[str], name: str) -> str | None:
    """取命令行参数值（--name value）。"""
    return argv[argv.index(name) + 1] if name in argv else None


def main() -> None:
    """入口：解析参数 → 生成报告 → 打印自检与输出路径。"""
    argv = sys.argv[1:]
    use_llm = "--no-llm" not in argv

    print("=== 模块 4 报告生成 ===")
    if llm_available():
        print(f"LLM 可用（模型 {model_name()}），摘要将 LLM 润色")
    else:
        print("LLM 不可用（摘要用规则式）")

    agent = ReportAgent(
        retrieval_path=_arg(argv, "--retrieval"),
        kb_path=_arg(argv, "--kb"),
        gaps_path=_arg(argv, "--gaps"),
        validation_dir=_arg(argv, "--validation-dir") or DEFAULT_VALIDATION_DIR,
    )
    result = agent.run(use_llm=use_llm)
    doc = result.document

    print("\n=== 结构化自检清单 ===")
    for check, passed in doc.meta.self_check.items():
        print(f"[{'✓' if passed else '✗'}] {check}")

    print("\n=== 报告统计 ===")
    print(f"领域        : {doc.meta.domain}")
    print(f"文献数      : {doc.meta.n_papers}")
    print(f"知识库条目  : {doc.meta.n_kb_entries}")
    print(f"Gap 数      : {doc.meta.n_gaps}")
    print(f"摘要来源    : {'LLM' if result.llm_abstract else '规则式'}")
    print(f"输入快照    : {doc.meta.input_hashes}")

    print("\n=== 输出文件 ===")
    for path in (result.md_path, result.html_path, result.meta_path):
        print(f"- {path}")
    print("\n日志: results/logs/report_agent_*.jsonl")


if __name__ == "__main__":
    main()

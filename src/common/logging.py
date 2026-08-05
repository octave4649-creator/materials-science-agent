"""统一 JSON 审计日志。

Agent 日志规范（00-project-rules.md 4.3）：每步记录
{ts, agent, action, input_summary, output_summary, duration_ms, status}，
工具调用序列单独记录，用于审计与消融实验。
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from src.common.config import LOG_DIR


def _ts() -> str:
    """UTC 毫秒级时间戳。"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class AuditLogger:
    """追加式 JSON 日志器（每次写文件独立打开，简单线程安全）。"""

    def __init__(self, agent: str, log_dir: Path = LOG_DIR) -> None:
        self.agent = agent
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, record: dict[str, Any]) -> None:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        path = self.log_dir / f"{self.agent}_{date}.jsonl"
        record.setdefault("ts", _ts())
        record.setdefault("agent", self.agent)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log(
        self,
        action: str,
        status: str,
        input_summary: Any = None,
        output_summary: Any = None,
        duration_ms: float | None = None,
        **extra: Any,
    ) -> None:
        """写一条日志。status 取 success / error / skipped 等。"""
        record: dict[str, Any] = {"action": action, "status": status}
        if input_summary is not None:
            record["input_summary"] = input_summary
        if output_summary is not None:
            record["output_summary"] = output_summary
        if duration_ms is not None:
            record["duration_ms"] = round(duration_ms, 1)
        record.update(extra)
        self._write(record)

    @contextmanager
    def step(self, action: str, input_summary: Any = None) -> Iterator[None]:
        """记录一个操作的耗时与成败（异常也会记录后抛出）。"""
        start = time.perf_counter()
        try:
            yield
            self.log(
                action,
                "success",
                input_summary=input_summary,
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:  # 审计层兜底，任何异常都要留痕
            self.log(
                action,
                "error",
                input_summary=input_summary,
                duration_ms=(time.perf_counter() - start) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

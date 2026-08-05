"""MinerU 解析管线：PDF → Markdown。

主环境 Python 3.14 无 mineru wheel（官方支持 ≤3.13），故通过子进程调用
独立 Python 环境中的 mineru CLI（如 miniconda 3.13），Python 路径由环境变量
MINERU_PYTHON 指定（默认取 PATH 中的 python）。

解析结果落盘到 `data/parsed/`，返回 Markdown 文本供抽取 Agent 使用。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.common.config import DATA_DIR

# mineru CLI 输出目录：data/parsed
PARSED_DIR = DATA_DIR / "parsed"


class MineruError(Exception):
    """MinerU 解析异常。"""


class MineruParser:
    """MinerU PDF 解析器（子进程封装）。"""

    def __init__(self, python_bin: str | None = None, timeout: int = 900) -> None:
        """初始化。

        参数:
            python_bin: 安装 mineru 的 Python 解释器路径（默认取 MINERU_PYTHON 或 "python"）
            timeout: 单篇解析超时（秒），默认 15 分钟（首次需下载模型）
        """
        self.python_bin = python_bin or os.getenv("MINERU_PYTHON", "python")
        self.timeout = timeout

    def available(self) -> bool:
        """mineru 是否可用（子进程探测 import）。"""
        try:
            result = subprocess.run(
                [self.python_bin, "-c", "import mineru"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _mineru_exe(self) -> str:
        """定位 mineru CLI 可执行文件。

        mineru 包无 ``__main__``（``python -m mineru`` 不可用），需调用
        控制台脚本。优先取 python_bin 同环境 Scripts 下的 mineru(.exe)，
        找不到时回退 PATH 中的 ``mineru``。
        """
        scripts = Path(self.python_bin).parent / "Scripts"
        for cand in (scripts / "mineru.exe", scripts / "mineru"):
            if cand.is_file():
                return str(cand)
        return "mineru"

    def parse_pdf(self, pdf_path: str | Path, *, out_dir: str | Path | None = None) -> str:
        """解析单篇 PDF，返回 Markdown 文本。

        参数:
            pdf_path: PDF 文件路径
            out_dir: 输出目录（默认 data/parsed）

        返回:
            Markdown 文本。

        异常:
            MineruError: mineru 不可用 / 文件不存在 / 解析失败 / 超时
        """
        pdf = Path(pdf_path)
        if not pdf.is_file():
            raise MineruError(f"PDF 不存在: {pdf}")
        out = Path(out_dir) if out_dir else PARSED_DIR
        out.mkdir(parents=True, exist_ok=True)
        if not self.available():
            raise MineruError(
                f"mineru 不可用（python_bin={self.python_bin}），"
                "请配置 MINERU_PYTHON 指向安装 mineru 的解释器，或先安装 mineru"
            )
        cmd = [
            self._mineru_exe(),
            "-p",
            str(pdf),
            "-o",
            str(out),
            "-b",
            "pipeline",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=self.timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise MineruError(f"mineru 解析超时（{self.timeout}s）: {pdf.name}") from exc
        except OSError as exc:
            raise MineruError(f"mineru 启动失败: {exc}") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout)[-500:]
            raise MineruError(f"mineru 解析失败（exit={proc.returncode}）: {tail}")
        # 读取输出 markdown（mineru 输出结构：out/<pdf名>/<pdf名>.md 或 out/<pdf名>.md）
        stem = pdf.stem
        candidates = [
            out / f"{stem}.md",
            out / stem / f"{stem}.md",
            out / stem / "content.json",
        ]
        for cand in candidates:
            if cand.is_file():
                return cand.read_text(encoding="utf-8")
        # 兜底：递归查找该目录下最近的 .md
        md_files = sorted(out.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if md_files:
            return md_files[0].read_text(encoding="utf-8")
        raise MineruError(f"mineru 解析完成但未找到输出文件: {pdf.name}")

    def parse_batch(
        self, pdf_paths: list[str | Path], *, out_dir: str | Path | None = None
    ) -> dict[str, str]:
        """批量解析多篇 PDF，返回 {pdf_name: markdown}。"""
        return {Path(p).name: self.parse_pdf(p, out_dir=out_dir) for p in pdf_paths}

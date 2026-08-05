"""MinerU 解析管线测试（mock 子进程，不依赖真实 mineru）。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.extraction.mineru_pipeline import MineruError, MineruParser


def test_available_false_for_missing_python() -> None:
    """python_bin 指向不存在的解释器 → 不可用。"""
    parser = MineruParser(python_bin="nonexistent-python-xyz")
    assert parser.available() is False


def test_parse_missing_pdf_raises() -> None:
    """PDF 不存在抛 MineruError。"""
    parser = MineruParser(python_bin="python")
    with pytest.raises(MineruError, match="PDF 不存在"):
        parser.parse_pdf("no_such_file.pdf")


def test_parse_unavailable_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mineru 不可用时抛可读错误。"""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    parser = MineruParser(python_bin="nonexistent-python-xyz")
    monkeypatch.setattr(parser, "available", lambda: False)
    with pytest.raises(MineruError, match="mineru 不可用"):
        parser.parse_pdf(pdf)


def test_parse_success_returns_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mock 子进程成功 → 返回 markdown 内容。"""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    out_dir = tmp_path / "parsed"
    out_dir.mkdir()
    md = out_dir / "paper.md"
    md.write_text("# Title\n\nSome content", encoding="utf-8")

    parser = MineruParser(python_bin="python")
    monkeypatch.setattr(parser, "available", lambda: True)
    # 模拟 subprocess.run 成功退出

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args[0], 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("src.extraction.mineru_pipeline.subprocess.run", fake_run)

    result = parser.parse_pdf(pdf, out_dir=out_dir)
    assert "# Title" in result


def test_parse_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """子进程非零退出 → 抛 MineruError。"""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    parser = MineruParser(python_bin="python")
    monkeypatch.setattr(parser, "available", lambda: True)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args[0], 1, stdout=b"", stderr=b"boom")

    monkeypatch.setattr("src.extraction.mineru_pipeline.subprocess.run", fake_run)
    with pytest.raises(MineruError, match="mineru 解析失败"):
        parser.parse_pdf(pdf, out_dir=tmp_path)

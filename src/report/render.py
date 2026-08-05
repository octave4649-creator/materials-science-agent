"""报告渲染：ReportDocument → Markdown / HTML。

决策 1（task_plan）：Markdown 为主 + HTML 增强。
Markdown 由章节拼接（标题 + 正文），HTML 用受控子集转换器渲染
（仅处理本报告生成器产出的语法：标题/表格/列表/加粗/行内码/分割线/斜体），
不引入第三方依赖，保证可复现（经验：避免新增不确定性依赖）。
"""
from __future__ import annotations

import html as _html
import re

from src.report.schemas import ReportDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_LIST_RE = re.compile(r"^[-*]\s+(.+)$")


def render_markdown(doc: ReportDocument) -> str:
    """渲染为 Markdown（章节按 SECTION_ORDER 顺序拼接）。"""
    lines = [f"# {doc.title}", ""]
    for section in doc.sections:
        lines.append(f"## {section.title}")
        lines.append("")
        lines.append(section.content.rstrip())
        lines.append("")
    return "\n".join(lines)


def _inline(text: str) -> str:
    """行内元素转 HTML：加粗 / 斜体 / 行内码 / 链接。"""
    text = _html.escape(text)
    text = _CODE_RE.sub(r"<code>\1</code>", text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _ITALIC_RE.sub(r"<em>\1</em>", text)
    text = _LINK_RE.sub(r'<a href="\2">\1</a>', text)
    return text


def _table(lines: list[str]) -> str:
    """Markdown 表格 → HTML table（首行为表头，忽略分隔行）。"""
    rows = [ln.strip().strip("|") for ln in lines if ln.strip()]
    if not rows:
        return ""
    header = [_inline(c.strip()) for c in rows[0].split("|")]
    body: list[str] = []
    for row in rows[2:]:  # 跳过表头 + 分隔行
        cells = [_inline(c.strip()) for c in row.split("|")]
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    head = "<tr>" + "".join(f"<th>{c}</th>" for c in header) + "</tr>"
    return f"<table><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"


def render_html(doc: ReportDocument) -> str:
    """渲染为 HTML（受控 markdown 子集转换）。"""
    body: list[str] = [f"<h1>{_html.escape(doc.title)}</h1>"]
    for section in doc.sections:
        body.append(f"<h2>{_html.escape(section.title)}</h2>")
        paragraphs = section.content.rstrip().split("\n\n")
        for para in paragraphs:
            lines = para.split("\n")
            stripped = [ln.strip() for ln in lines]
            if all(ln.startswith("|") for ln in stripped if ln):
                body.append(_table(lines))
            elif len(lines) > 1 and all(_LIST_RE.match(ln) for ln in stripped if ln):
                items = "".join(
                    "<li>" + _inline(_LIST_RE.sub("\\1", ln).strip()) + "</li>"
                    for ln in stripped
                )
                body.append(f"<ul>{items}</ul>")
            elif len(lines) == 1:
                ln = lines[0]
                if _HEADING_RE.match(ln):
                    match = _HEADING_RE.match(ln)
                    lvl = min(len(match.group(1)), 6)
                    title = _inline(_HEADING_RE.sub("\\2", ln))
                    body.append(f"<h{lvl}>{title}</h{lvl}>")
                elif ln.strip() == "---":
                    body.append("<hr/>")
                else:
                    body.append(f"<p>{_inline(ln)}</p>")
            else:
                body.append("<p>" + "<br/>".join(_inline(ln) for ln in stripped) + "</p>")
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
        "<title>{}</title></head><body>{}</body></html>"
    ).format(_html.escape(doc.title), "\n".join(body))

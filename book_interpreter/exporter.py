"""将解读结果导出为 Markdown / HTML 报告。"""

from __future__ import annotations

import html

from .models import Interpretation


def export_markdown(interp: Interpretation) -> str:
    """生成 Markdown 格式的解读报告。"""
    book = interp.book
    lines = [
        f"# 《{book.title}》解读报告",
        "",
        "## 全书概述",
        "",
        interp.overview or "（暂无）",
        "",
        "## 章节摘要",
        "",
    ]
    for chapter in book.chapters:
        lines.append(f"### {chapter.title}")
        lines.append("")
        lines.append(chapter.summary or "（暂无摘要）")
        lines.append("")

    lines.append("## 核心观点")
    lines.append("")
    if interp.key_points:
        for i, point in enumerate(interp.key_points, 1):
            lines.append(f"{i}. {point}")
    else:
        lines.append("（暂无）")
    lines.append("")

    lines.append("## 金句摘录")
    lines.append("")
    if interp.quotes:
        for quote in interp.quotes:
            lines.append(f"- {quote}")
    else:
        lines.append("（暂无）")
    lines.append("")

    return "\n".join(lines)


def export_html(interp: Interpretation) -> str:
    """生成 HTML 格式的解读报告。"""
    book = interp.book
    title = html.escape(book.title)

    chapters_html = []
    for chapter in book.chapters:
        chapters_html.append(
            f"<h2>{html.escape(chapter.title)}</h2>"
            f"<p>{html.escape(chapter.summary or '（暂无摘要）')}</p>"
        )

    points_html = "".join(
        f"<li>{html.escape(p)}</li>" for p in interp.key_points
    ) or "<li>（暂无）</li>"
    quotes_html = "".join(
        f"<li>{html.escape(q)}</li>" for q in interp.quotes
    ) or "<li>（暂无）</li>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>《{title}》解读报告</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         max-width: 800px; margin: 40px auto; padding: 0 20px;
         line-height: 1.7; color: #333; }}
  h1 {{ color: #1a1a1a; border-bottom: 3px solid #4a90d9; padding-bottom: 10px; }}
  h2 {{ color: #2c3e50; margin-top: 32px; }}
  .overview {{ background: #f5f8fc; padding: 16px 20px; border-radius: 8px; }}
  li {{ margin: 6px 0; }}
</style>
</head>
<body>
<h1>《{title}》解读报告</h1>

<h2>全书概述</h2>
<div class="overview"><p>{html.escape(interp.overview or '（暂无）')}</p></div>

<h2>章节摘要</h2>
{''.join(chapters_html)}

<h2>核心观点</h2>
<ul>{points_html}</ul>

<h2>金句摘录</h2>
<ul>{quotes_html}</ul>
</body>
</html>
"""


def export(interp: Interpretation, fmt: str = "md") -> str:
    """按指定格式导出解读报告（md 或 html）。"""
    fmt = fmt.lower()
    if fmt == "md" or fmt == "markdown":
        return export_markdown(interp)
    if fmt == "html":
        return export_html(interp)
    raise ValueError(f"不支持的导出格式: {fmt}")

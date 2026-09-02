"""导出器测试。"""

import pytest

from book_interpreter.exporter import export, export_html, export_markdown
from book_interpreter.models import Book, Chapter, Interpretation


def _make_interp() -> Interpretation:
    book = Book(
        title="测试书",
        chapters=[Chapter(title="第一章", content="内容", order=0, summary="本章摘要")],
    )
    return Interpretation(
        book=book,
        overview="全书概述",
        key_points=["观点一", "观点二"],
        quotes=["金句一", "金句二"],
    )


def test_export_markdown_contains_sections():
    md = export_markdown(_make_interp())
    assert "《测试书》解读报告" in md
    assert "全书概述" in md and "全书概述" in md
    assert "章节摘要" in md
    assert "核心观点" in md
    assert "金句摘录" in md
    assert "本章摘要" in md
    assert "观点一" in md and "金句一" in md


def test_export_html_contains_sections():
    html = export_html(_make_interp())
    assert "<html" in html
    assert "《测试书》解读报告" in html
    assert "全书概述" in html
    assert "章节摘要" in html
    assert "核心观点" in html
    assert "金句摘录" in html


def test_export_html_escapes_content():
    interp = _make_interp()
    interp.book.title = "书<书名>"
    interp.overview = "含 <script>alert(1)</script> 的内容"
    html = export_html(interp)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_export_format_dispatch():
    interp = _make_interp()
    assert export(interp, "md") == export_markdown(interp)
    assert export(interp, "markdown") == export_markdown(interp)
    assert export(interp, "HTML") == export_html(interp)


def test_export_unsupported_format():
    with pytest.raises(ValueError):
        export(_make_interp(), "pdf")

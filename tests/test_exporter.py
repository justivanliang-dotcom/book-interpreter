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
    assert "章节浓缩" in md
    assert "核心观点" in md
    assert "金句摘录" in md
    assert "本章摘要" in md
    assert "观点一" in md and "金句一" in md


def test_export_html_contains_sections():
    html = export_html(_make_interp())
    assert "<html" in html
    assert "《测试书》解读报告" in html
    assert "全书概述" in html
    assert "章节浓缩" in html
    assert "核心观点" in html
    assert "金句摘录" in html


def test_export_skips_empty_chapter_summaries():
    book = Book(
        title="测试书",
        chapters=[
            Chapter(title="第一章", content="内容", order=0, summary="本章摘要"),
            Chapter(title="第二章", content="内容", order=1, summary=""),
        ],
    )
    interp = Interpretation(book=book, overview="概述")
    md = export_markdown(interp)
    assert "第一章" in md and "本章摘要" in md
    assert "第二章" not in md
    html = export_html(interp)
    assert "第二章" not in html


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

"""多格式文本提取测试。"""

import io

import pytest

from book_interpreter.loaders import (
    SUPPORTED_EXTENSIONS,
    UnsupportedFormatError,
    extract_text,
    html_to_text,
)
from tests.conftest import simple_pdf


def _make_epub(tmp_path, title="测试书", body="第一章 内容"):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-123")
    book.set_title(title)
    ch = epub.EpubHtml(title="第一章", file_name="chap1.xhtml", lang="zh")
    ch.content = f"<html><body><h1>第一章</h1><p>{body}</p></body></html>"
    book.add_item(ch)
    book.toc = (ch,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    path = tmp_path / "book.epub"
    epub.write_epub(str(path), book)
    return path


def test_supported_extensions():
    assert SUPPORTED_EXTENSIONS == {
        ".txt", ".md", ".markdown", ".pdf", ".epub", ".mobi", ".azw3",
    }


def test_extract_text_txt_utf8():
    text = extract_text("book.txt", "第一章\n正文内容。".encode("utf-8"))
    assert "第一章" in text


def test_extract_text_txt_gbk():
    text = extract_text("book.txt", "第一章\n正文内容。".encode("gb18030"))
    assert "第一章" in text


def test_extract_text_txt_utf16_bom():
    text = extract_text("book.txt", "第一章\n正文内容。".encode("utf-16"))
    assert "第一章" in text


def test_extract_text_markdown():
    text = extract_text("book.md", "# 测试书\n\n## 第一章\n内容".encode("utf-8"))
    assert "# 测试书" in text


def test_extract_text_pdf():
    text = extract_text("book.pdf", simple_pdf("Chapter 1 Test Content " * 4))
    assert "Chapter 1 Test Content" in text


def test_extract_text_pdf_empty_raises():
    # 无文本页的 PDF 应报可读错误
    writer = __import__("pypdf").PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(UnsupportedFormatError, match="扫描版|加密"):
        extract_text("book.pdf", buf.getvalue())


def test_extract_text_epub(tmp_path):
    path = _make_epub(tmp_path)
    text = extract_text("book.epub", path.read_bytes())
    assert "第一章" in text
    assert "第一章 内容" in text


def test_extract_text_mobi(monkeypatch, tmp_path):
    import mobi

    html_dir = tmp_path / "out"
    html_dir.mkdir()
    html = html_dir / "book.html"
    html.write_text(
        "<html><body><h1>第一章</h1><p>MOBI 内容。</p></body></html>",
        encoding="utf-8",
    )

    def fake_extract(_path):
        return str(html_dir), str(html)

    monkeypatch.setattr(mobi, "extract", fake_extract)
    text = extract_text("book.mobi", b"fake mobi bytes")
    assert "第一章" in text
    assert "MOBI 内容" in text


def test_extract_text_azw3(monkeypatch, tmp_path):
    import mobi

    html_dir = tmp_path / "out"
    html_dir.mkdir()
    html = html_dir / "book.html"
    html.write_text("<html><body><h1>第一章</h1><p>AZW3 内容。</p></body></html>", encoding="utf-8")

    def fake_extract(_path):
        return str(html_dir), str(html)

    monkeypatch.setattr(mobi, "extract", fake_extract)
    text = extract_text("book.azw3", b"fake azw3 bytes")
    assert "AZW3 内容" in text


def test_extract_text_unsupported_extension():
    with pytest.raises(UnsupportedFormatError, match="不支持的格式"):
        extract_text("book.docx", b"hello")


def test_html_to_text_skips_script():
    html = (
        "<html><head><script>var x = 1;</script><style>p{color:red}</style></head>"
        "<body><h1>第一章</h1><p>内容甲</p><p>内容乙</p></body></html>"
    )
    text = html_to_text(html)
    assert "第一章" in text
    assert "内容甲" in text
    assert "内容乙" in text
    assert "script" not in text
    assert "color" not in text

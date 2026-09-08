"""多格式文本提取测试。"""

import io
from types import SimpleNamespace

import pytest

from book_interpreter.loaders import (
    SUPPORTED_EXTENSIONS,
    UnsupportedFormatError,
    _entry_title,
    _flatten_toc,
    _html_first_heading,
    _html_title,
    extract_text,
    html_to_text,
)
from tests.conftest import simple_pdf


def _make_epub(tmp_path, title="测试书", chapters=("第一章 标题",)):
    """构造带目录的 EPUB，章节标题存于目录与正文。"""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-123")
    book.set_title(title)
    items = []
    for i, ch_title in enumerate(chapters, 1):
        ch = epub.EpubHtml(title=ch_title, file_name="chap%d.xhtml" % i, lang="zh")
        ch.content = f"<html><body><h1>{ch_title}</h1><p>{ch_title} 的内容。</p></body></html>"
        book.add_item(ch)
        items.append(ch)
    book.toc = tuple(items)
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
    # 书名来自 EPUB 元数据，章节标题来自目录
    assert "# 测试书" in text
    assert "## 第一章 标题" in text
    assert "第一章 标题 的内容。" in text


def test_extract_text_epub_multi_chapters_order(tmp_path):
    path = _make_epub(tmp_path, chapters=("前言", "第一章 科学边界", "注释"))
    text = extract_text("book.epub", path.read_bytes())
    # 目录章节按顺序出现，标题完整而非正文拼凑
    assert text.index("## 前言") < text.index("## 第一章 科学边界") < text.index("## 注释")


def test_extract_text_epub_without_toc(tmp_path):
    """无目录的 EPUB 回退到按文档顺序组织章节。"""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("toc-less")
    book.set_title("无目录书")
    ch = epub.EpubHtml(title="正文一", file_name="main.xhtml", lang="zh")
    # ebooklib 序列化会丢弃 <head>/<title>，正文 h1 保留，作为标题兜底来源
    ch.content = "<html><body><h1>正文一</h1><p>正文内容。</p></body></html>"
    book.add_item(ch)
    book.toc = ()
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    path = tmp_path / "no_toc.epub"
    epub.write_epub(str(path), book)
    text = extract_text("no_toc.epub", path.read_bytes())
    assert "## 正文一" in text
    assert "正文内容。" in text


def test_html_title_and_heading_fallback():
    """标题提取优先级：<title> → 正文首个 h1-h6 → 文件名 → 未命名章节。"""
    assert _html_title("<html><head><title> 章 名 </title></head></html>") == "章 名"
    assert _html_title("<html><body>无标题</body></html>") == ""
    assert _html_first_heading('<html><body><h2>第一章</h2><p>正文</p></body></html>') == "第一章"
    assert _html_first_heading("<html><body><p>无标题正文</p></body></html>") == ""

    item = type("Item", (), {"title": "来自清单"})
    assert _entry_title(item, "<html><body><h1>来自正文</h1></body></html>", "a.xhtml") == "来自清单"
    assert _entry_title(None, "<html><body><h1>来自正文</h1></body></html>", "a.xhtml") == "来自正文"
    assert _entry_title(None, "<html><body><p>无标题</p></body></html>", "part0001.xhtml") == "part0001"
    assert _entry_title(None, "<html></html>", "") == "未命名章节"


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


def test_html_to_text_skips_head():
    """head 区内容（如 title）不应混入正文。"""
    html = (
        "<html><head><title>未知</title></head><body>"
        "<h1>第一章</h1><p>正文内容。</p></body></html>"
    )
    text = html_to_text(html)
    assert "未知" not in text
    assert "第一章" in text


def _link(title, href):
    return SimpleNamespace(title=title, href=href, file_name=None)


def test_flatten_toc_nested_sections():
    """嵌套 (Section, [children]) 目录应完整展开，子章节不丢失。

    对应《大学之路》合订本：下册目录以 Section 包裹子链接列表，
    旧逻辑把 (Section, [children]) 当作单个条目导致子章节全部丢失。
    """
    toc = [
        (_link("大学之路（上）", "cover.xhtml"), [
            _link("第一章", "chap1.xhtml"),
            (_link("第一章 大学的概念", "chap1.xhtml"), [
                _link("第一节", "chap1.xhtml#s1"),
                _link("第二节", "chap1.xhtml#s2"),
            ]),
        ]),
        (_link("大学之路(下)", "text00000.html"), [
            [(_link("内容提要", "text00002.html"), [
                _link("前言", "text00004.html"),
                (_link("第八章大都市里的常青藤大学", "text00006.html"), [
                    _link("第一节宾夕法尼亚大学", "text00006.html#toc_id_5"),
                ]),
            ])],
        ]),
    ]
    flat = _flatten_toc(toc)
    titles = [t for t, _ in flat]
    assert titles == [
        "大学之路（上）",
        "第一章",
        "第一章 大学的概念",
        "第一节",
        "第二节",
        "大学之路(下)",
        "内容提要",
        "前言",
        "第八章大都市里的常青藤大学",
        "第一节宾夕法尼亚大学",
    ]


def test_extract_epub_anchor_split(tmp_path):
    """同一文件被多个目录条目引用时按锚点切分，内容不重复。

    对应《大学之路》上册：第一章与各"第一节/第二节"指向同一
    xhtml 文件的不同锚点，旧逻辑把整章内容重复输出到每个子节。
    """
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("anchor-split")
    book.set_title("锚点书")
    ch = epub.EpubHtml(title="第一章", file_name="chap1.xhtml", lang="zh")
    ch.content = (
        "<html><head><title>第一章</title></head><body>"
        "<h2 id='s0'>第一章 大学的概念</h2><p>本章引言。</p>"
        "<h3 id='s1'>第一节 大学的历史</h3><p>第一节内容。</p>"
        "<h3 id='s2'>第二节 精英教育</h3><p>第二节内容。</p>"
        "<h3 id='s3'>结束语</h3><p>结束语内容。</p>"
        "</body></html>"
    )
    book.add_item(ch)
    book.toc = (
        (epub.Link("chap1.xhtml", "第一章 大学的概念", "c1"), [
            epub.Link("chap1.xhtml#s1", "第一节 大学的历史", "c2"),
            epub.Link("chap1.xhtml#s2", "第二节 精英教育", "c3"),
            epub.Link("chap1.xhtml#s3", "结束语", "c4"),
        ]),
    )
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    path = tmp_path / "anchor.epub"
    epub.write_epub(str(path), book)

    text = extract_text("anchor.epub", path.read_bytes())
    # 每个子节内容只出现一次，不再重复整章
    assert text.count("第一节内容") == 1
    assert text.count("第二节内容") == 1
    assert text.count("结束语内容") == 1
    assert "## 第一章 大学的概念" in text
    assert "## 第一节 大学的历史" in text
    assert "## 结束语" in text
    # head 中的 title 不应混入正文
    assert "未知" not in text

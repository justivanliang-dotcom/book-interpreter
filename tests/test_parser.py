"""解析器测试。"""

from book_interpreter.parser import parse_book, read_book_file


def test_read_book_file_uses_content_title(tmp_path):
    p = tmp_path / "book.md"
    p.write_text("# 内容标题\n\n## 第一章\n内容", encoding="utf-8")
    book = read_book_file(str(p))
    assert book.title == "内容标题"


def test_read_book_file_falls_back_to_filename(tmp_path):
    p = tmp_path / "我的书.txt"
    p.write_text("没有标题的正文内容。", encoding="utf-8")
    book = read_book_file(str(p))
    assert book.title == "我的书"


def test_parse_markdown_book():
    text = """# 测试之书

## 第一章 开始

这是第一章的内容。

## 第二章 深入

这是第二章的内容。
"""
    book = parse_book(text)
    assert book.title == "测试之书"
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "第一章 开始"
    assert "第一章的内容" in book.chapters[0].content
    assert book.chapters[1].title == "第二章 深入"


def test_parse_plain_text_chinese_chapters():
    text = """第一章 缘起
这是第一章内容。

第二章 发展
这是第二章内容。
"""
    book = parse_book(text)
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "第一章 缘起"
    assert book.chapters[1].title == "第二章 发展"


def test_parse_plain_text_english_chapters():
    text = """Chapter 1 The Beginning
Content one.

Chapter 2 The Middle
Content two.
"""
    book = parse_book(text)
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "Chapter 1 The Beginning"
    assert book.chapters[1].title == "Chapter 2 The Middle"


def test_parse_empty_text():
    book = parse_book("   ")
    assert book.title == "未命名书籍"
    assert book.chapters == []


def test_parse_book_with_explicit_title():
    book = parse_book("只有一段内容，没有标题。", title="指定书名")
    assert book.title == "指定书名"
    assert len(book.chapters) == 1


def test_full_text_property():
    book = parse_book("# 书\n\n## 章一\n内容一\n\n## 章二\n内容二")
    full = book.full_text
    assert "章一" in full and "内容一" in full
    assert "章二" in full and "内容二" in full

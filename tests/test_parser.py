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


def test_parse_plain_text_strips_toc():
    # 模拟《非暴力沟通》式结构：开头目录页 + 译序 + 正文章节
    text = (
        "第一章 让爱融入生活\n"
        "第二章 是什么蒙蔽了爱？\n"
        "第三章 区分观察和评论\n"
        "我曾以为，我的一生将致力于对生命的痛苦作出反应。\n"
        "第一章 让爱融入生活\n"
        "引言\n"
        "我相信，人天生热爱生命，乐于互助。\n"
    )
    book = parse_book(text, title="测试书")
    # 目录被移除，正文解析出：前言（译序）+ 第一章
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "前言"
    assert "我曾以为" in book.chapters[0].content
    assert "第一章" in book.chapters[1].title
    assert "我相信" in book.chapters[1].content


def test_parse_plain_text_strips_toc_with_book_title_prefix():
    # 目录前有书名短行
    text = (
        "非暴力沟通\n"
        "第一章 让爱融入生活\n"
        "第二章 是什么蒙蔽了爱？\n"
        "第三章 区分观察和评论\n"
        "我曾以为，我的一生将致力于对生命的痛苦作出反应。\n"
        "第一章 让爱融入生活\n"
        "引言\n"
        "我相信，人天生热爱生命，乐于互助。\n"
    )
    book = parse_book(text, title="测试书")
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "前言"
    assert "我曾以为" in book.chapters[0].content


def test_parse_plain_text_keeps_short_chapters_without_toc():
    # 正文开头即章节，且各章内容很短，不应被误判为目录
    text = (
        "第一章 缘起\n"
        "这是第一章内容。\n"
        "第二章 发展\n"
        "这是第二章内容。\n"
        "第三章 结局\n"
        "这是第三章内容。\n"
    )
    book = parse_book(text, title="测试书")
    assert len(book.chapters) == 3
    assert "这是第一章内容" in book.chapters[0].content
    assert "这是第二章内容" in book.chapters[1].content
    assert "这是第三章内容" in book.chapters[2].content

"""解析器测试。"""

from book_interpreter.parser import _is_markdown, parse_book, read_book_file


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


def test_parse_chapters_without_prefix_character():
    # 《马斯克原理》式格式：章节标记无"第"字（"一章 xxx"、"一部分 xxx"）
    text = (
        "一部分 追求目标\n"
        "一章 明确人生目标\n"
        "做有用的事，为未来而战。\n"
        "二章 像物理学家一样思考\n"
        "执着探寻真理。\n"
    )
    book = parse_book(text, title="测试书")
    titles = [c.title for c in book.chapters]
    assert titles == ["一部分 追求目标", "一章 明确人生目标", "二章 像物理学家一样思考"]
    assert "做有用的事" in book.chapters[1].content
    assert "执着探寻真理" in book.chapters[2].content


def test_parse_solo_front_and_back_sections():
    # "序"、"注释"、"致谢" 单独成行也应识别为章节，且不重复
    text = (
        "关于本书的说明\n"
        "本书内容说明。\n"
        "序\n"
        "这是序的内容。\n"
        "一章 明确人生目标\n"
        "正文内容。\n"
        "注释\n"
        "18. 引用数据。\n"
        "致谢\n"
        "感谢所有人。\n"
    )
    book = parse_book(text, title="测试书")
    titles = [c.title for c in book.chapters]
    assert titles == ["关于本书的说明", "序", "一章 明确人生目标", "注释", "致谢"]
    assert "引用数据" in book.chapters[titles.index("注释")].content
    assert titles.count("致谢") == 1


def test_line_chapter_marker_not_matching_body_text():
    # 正文中的"这一章讨论"、"两个部分"不应被误识别为章节标记
    text = (
        "这一章讨论人工智能的边界。\n"
        "全书分为两个部分。\n"
        "一章 真正的章节标题\n"
        "内容。\n"
    )
    book = parse_book(text, title="测试书")
    # 正文前缀成为"前言"，真正的章节标题是第二个章节
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "前言"
    assert "这一章讨论" in book.chapters[0].content
    assert "全书分为两个部分" in book.chapters[0].content
    assert book.chapters[1].title == "一章 真正的章节标题"


def test_is_markdown_not_fooled_by_hash_reference():
    # 书末注释行 "#18,\"Lex Fridman...\"" 以井号开头，不应误判为 Markdown
    text = (
        "马斯克原理\n"
        "第一章\n"
        "做有用的事。\n"
        '#18,"Lex Fridman,April 12,2019,YouTube video,32:44. [602]Musk(@elonmusk),Xaccount.\n'
    )
    assert _is_markdown(text) is False


def test_is_markdown_requires_two_headings():
    # 单个井号标题不算 Markdown（避免误判）；两个才算
    assert _is_markdown("# 单个标题\n正文。\n") is False
    assert _is_markdown("# 标题一\n正文。\n## 标题二\n内容。\n") is True


def test_strip_toc_skips_front_matter():
    # 版权页（含句号）+ "目 录" + 目录条目：目录应被移除，正文标题保留
    text = (
        "马斯克原理\n"
        "[美]埃里克·乔根森 著。版权所有。\n"
        "目 录\n"
        "CONTENTS\n"
        "序 IX\n"
        "第一章 缘起 003\n"
        "第二章 发展 018\n"
        "第三章 结局 033\n"
        "第一章 缘起\n"
        "这是正文。\n"
        "第二章 发展\n"
        "这是正文。\n"
    )
    book = parse_book(text, title="测试书")
    titles = [c.title for c in book.chapters]
    assert titles[0] == "前言"
    assert "序 IX" not in book.chapters[0].content
    assert "第一章 缘起" in titles
    assert "这是正文" in book.chapters[titles.index("第一章 缘起")].content


def test_parse_order_with_author():
    # "序 纳瓦尔·拉维坎特"（章节名+作者名）应识别为"序"章节
    text = (
        "关于本书的重要说明\n"
        "本书内容说明。\n"
        "序 纳瓦尔·拉维坎特\n"
        "这是序的正文。\n"
        "第一章 明确人生目标\n"
        "做有用的事。\n"
    )
    book = parse_book(text, title="测试书")
    titles = [c.title for c in book.chapters]
    assert "序 纳瓦尔·拉维坎特" in titles
    assert "这是序的正文" in book.chapters[titles.index("序 纳瓦尔·拉维坎特")].content


def test_parse_musk_style_book():
    # 《马斯克原理》式完整结构：版权页 + 目录 + 序 + 一章 + 注释 + 致谢
    text = (
        "The Book of ELON\n"
        "马斯克原理\n"
        "[美]埃里克·乔根森 著。版权所有。\n"
        "目 录\n"
        "关于本书的重要说明 VII\n"
        "序 IX\n"
        "第一部分 追求目标 003\n"
        "第一章 明确人生目标 003\n"
        "第二章 像物理学家一样思考 018\n"
        "注释 250\n"
        "致谢 254\n"
        "关于本书的重要说明\n"
        "本书用马斯克的原话呈现其思想精华。\n"
        "序 纳瓦尔·拉维坎特\n"
        "这是序的正文。\n"
        "第一部分 追求目标\n"
        "第一章 明确人生目标\n"
        "做有用的事，为未来而战。\n"
        "第二章 像物理学家一样思考\n"
        "执着探寻真理。\n"
        "#18,\"Lex Fridman,April 12,2019,YouTube video,32:44.\n"
        "[602]Musk(@elonmusk),Xaccount.\n"
        "致谢\n"
        "感谢所有支持者。\n"
    )
    book = parse_book(text)
    assert book.title == "马斯克原理"
    titles = [c.title for c in book.chapters]
    assert titles[0] == "关于本书的重要说明"
    assert "序 纳瓦尔·拉维坎特" in titles
    assert "第一章 明确人生目标" in titles
    assert "致谢" in titles
    assert "做有用的事" in book.chapters[titles.index("第一章 明确人生目标")].content
    assert "#18," in book.chapters[titles.index("致谢") - 1].content

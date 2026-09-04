"""解读器测试。"""

from book_interpreter.interpreter import (
    _parse_list,
    _parse_summary_with_sources,
    _retrieve_source,
    _split_paragraphs,
    extract_chapter_titles,
    generate_overview,
    interpret_book,
    summarize_chapter,
    summarize_chapter_with_sources,
)
from book_interpreter.models import Book, Chapter
from tests.conftest import FakeLLM


def _make_book() -> Book:
    return Book(
        title="测试书",
        chapters=[
            Chapter(title="第一章", content="第一章的内容。", order=0),
            Chapter(title="第二章", content="第二章的内容。", order=1),
        ],
    )


def _make_plain_book() -> Book:
    """纯文本书：标题与正文在同一行拼接。"""
    return Book(
        title="测试书",
        chapters=[
            Chapter(title="第1章 标题一正文一", content="第1章 标题一正文一\n内容一。", order=0),
            Chapter(title="第2章 标题二正文二", content="第2章 标题二正文二\n内容二。", order=1),
        ],
    )


def test_interpret_book_fills_all_fields(fake_llm):
    book = _make_book()
    interp = interpret_book(fake_llm, book)

    assert interp.overview
    assert len(interp.key_points) == 5
    assert len(interp.quotes) == 3
    assert book.chapters[0].summary
    assert book.chapters[1].summary


def test_interpret_book_refines_titles(fake_llm):
    book = _make_plain_book()
    interpret_book(fake_llm, book)
    assert book.chapters[0].title == "第1章 测试标题"
    assert book.chapters[1].title == "第2章 测试标题"


def test_interpret_book_skips_empty_chapter(fake_llm):
    book = Book(
        title="测试书",
        chapters=[
            Chapter(title="空章", content="   ", order=0),
            Chapter(title="有内容", content="真实内容。", order=1),
        ],
    )
    interp = interpret_book(fake_llm, book)
    assert book.chapters[0].title == "空章"
    assert book.chapters[0].summary == ""
    assert book.chapters[1].summary


class BadCountLLM(FakeLLM):
    def complete(self, prompt, system="", max_tokens=2000):
        if "开头行" in prompt:
            return "只有一行"
        return super().complete(prompt, system, max_tokens)


def test_extract_chapter_titles_fallback_on_bad_response():
    book = _make_plain_book()
    interpret_book(BadCountLLM(), book)
    assert book.chapters[0].title == "第1章 标题一正文一"
    assert book.chapters[1].title == "第2章 标题二正文二"


def test_extract_chapter_titles_skips_non_marker(fake_llm):
    book = _make_book()
    extract_chapter_titles(fake_llm, book)
    assert book.chapters[0].title == "第一章"
    assert book.chapters[1].title == "第二章"


def test_parse_list_various_formats():
    text = "1. 第一点\n2. 第二点\n- 第三点\n* 第四点\n• 第五点\n无前缀第六点"
    items = _parse_list(text)
    assert items == ["第一点", "第二点", "第三点", "第四点", "第五点", "无前缀第六点"]


def test_parse_list_empty():
    assert _parse_list("") == []
    assert _parse_list("  \n  ") == []


def test_summarize_chapter_by_ratio(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 约2000字
    # 10% → 约200字
    summarize_chapter(fake_llm, chapter.title, chapter.content, 0.1)
    assert "约 200 字" in fake_llm.calls[-1]
    assert "160~240" in fake_llm.calls[-1]
    # 50% → 约1000字
    summarize_chapter(fake_llm, chapter.title, chapter.content, 0.5)
    assert "约 1000 字" in fake_llm.calls[-1]


def test_summarize_chapter_full_returns_original(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 约2000字
    calls_before = len(fake_llm.calls)
    result = summarize_chapter(fake_llm, chapter.title, chapter.content, 1.0)
    assert result == chapter.content  # 100% 直接返回原文
    assert len(fake_llm.calls) == calls_before  # 不调用 LLM


def test_summarize_chapter_floor_100(fake_llm):
    chapter = Chapter(title="短章", content="内容" * 100, order=0)  # 200字
    summarize_chapter(fake_llm, chapter.title, chapter.content, 0.1)
    assert "约 100 字" in fake_llm.calls[-1]


def test_summarize_chapter_max_words_cap(fake_llm):
    chapter = Chapter(title="长章", content="内容" * 1000, order=0)  # 2000字
    summarize_chapter(fake_llm, chapter.title, chapter.content, 0.5, max_words=300)
    assert "约 300 字" in fake_llm.calls[-1]


def test_generate_overview_does_not_fill_chapter_summaries(fake_llm):
    book = _make_book()
    interp = generate_overview(fake_llm, book)
    assert interp.overview
    assert len(interp.key_points) == 5
    assert len(interp.quotes) == 3
    assert book.chapters[0].summary == ""
    assert book.chapters[1].summary == ""


def test_parse_summary_with_sources():
    text = (
        "【句】这是第一句摘要。\n"
        "【源】这是第一句对应的原文。\n"
        "【句】这是第二句摘要。\n"
        "【源】这是第二句对应的原文。\n"
    )
    sentences = _parse_summary_with_sources(text)
    assert sentences == [
        {"text": "这是第一句摘要。", "source": "这是第一句对应的原文。"},
        {"text": "这是第二句摘要。", "source": "这是第二句对应的原文。"},
    ]


def test_parse_summary_with_sources_missing_source():
    sentences = _parse_summary_with_sources("【句】只有摘要没有原文。\n")
    assert sentences == [{"text": "只有摘要没有原文。", "source": ""}]


class SourceLLM(FakeLLM):
    def complete(self, prompt, system="", max_tokens=2000):
        if "【句】" in prompt:
            return "【句】摘要句一。\n【源】原文句一。\n【句】摘要句二。\n【源】原文句二。\n"
        return super().complete(prompt, system, max_tokens)


def test_summarize_chapter_with_sources():
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)
    summary, sentences = summarize_chapter_with_sources(SourceLLM(), chapter.title, chapter.content, 0.1)
    assert summary == "摘要句一。摘要句二。"
    assert len(sentences) == 2
    assert sentences[0] == {"text": "摘要句一。", "source": "原文句一。"}
    assert sentences[1] == {"text": "摘要句二。", "source": "原文句二。"}


def test_summarize_chapter_with_sources_fallback(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)
    summary, sentences = summarize_chapter_with_sources(fake_llm, chapter.title, chapter.content, 0.1)
    # FakeLLM 不返回标记格式，fallback 为单个无来源句子
    assert len(sentences) == 1
    assert sentences[0]["source"] == ""
    assert summary == sentences[0]["text"]


def test_summarize_chapter_with_sources_full_returns_original(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)
    calls_before = len(fake_llm.calls)
    summary, sentences = summarize_chapter_with_sources(fake_llm, chapter.title, chapter.content, 1.0)
    assert summary == chapter.content
    assert sentences == [{"text": chapter.content, "source": chapter.content}]
    assert len(fake_llm.calls) == calls_before


def test_split_paragraphs():
    text = (
        "这是第一段比较长的内容，用来测试段落切分逻辑是否正确无误。\n\n"
        "这是第二段比较长的内容，同样用于测试段落切分的合并行为。\n短\n"
        "这是第三段比较长的内容，用于验证过短段落合并到前一段。"
    )
    paras = _split_paragraphs(text)
    assert len(paras) == 3
    assert "这是第二段比较长的内容，同样用于测试段落切分的合并行为。短" in paras[1]


def test_retrieve_source_finds_paragraph():
    content = (
        "人工智能正在改变世界。\n\n"
        "从制造业到服务业，AI 的应用无处不在。这场变革比工业革命更深远。\n\n"
        "企业必须拥抱变革。"
    )
    src = _retrieve_source(content, "AI 的应用无处不在，变革比工业革命更深远")
    assert "制造业" in src
    assert "工业革命" in src


class EllipsisLLM(FakeLLM):
    def complete(self, prompt, system="", max_tokens=2000):
        if "【句】" in prompt:
            return (
                "【句】人工智能正在深刻改变我们的世界，这场变革比工业革命更加深远。\n"
                "【源】原文开头……原文结尾。\n"
            )
        return super().complete(prompt, system, max_tokens)


def test_summarize_chapter_with_sources_replaces_ellipsis():
    content = (
        "第一段：人工智能正在深刻改变我们的世界，它不再只是实验室里的技术。\n\n"
        "第二段：从制造业到服务业，从医疗到教育，AI 的应用无处不在。这场变革比工业革命更加深远。\n\n"
        "第三段：企业必须拥抱这场变革，否则将被时代淘汰。"
    ) * 10
    chapter = Chapter(title="测试章", content=content, order=0)
    summary, sentences = summarize_chapter_with_sources(EllipsisLLM(), chapter.title, chapter.content, 0.5)
    assert len(sentences) == 1
    assert "…" not in sentences[0]["source"]
    assert "人工智能" in sentences[0]["source"]

"""解读器测试。"""

import re

from book_interpreter.interpreter import (
    _parse_list,
    _parse_summary_with_sources,
    _retrieve_context,
    _split_paragraphs,
    count_chars,
    explain_chapter_by_ratio,
    explain_chapter_plain,
    extract_chapter_titles,
    generate_overview,
    interpret_book,
    summarize_chapter,
    summarize_chapter_with_sources,
    summary_target_words,
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
    assert "180~220" in fake_llm.calls[-1]
    # 50% → 约1000字
    summarize_chapter(fake_llm, chapter.title, chapter.content, 0.5)
    assert "约 1000 字" in fake_llm.calls[-1]


def test_count_chars_ignores_whitespace():
    assert count_chars("hello world\n") == 10
    assert count_chars("内容 内容\n\n") == 4
    assert count_chars("") == 0


def test_summary_target_words():
    # 可见字数口径：2000 字 → 75% → 1500
    assert summary_target_words("内容" * 1000, 0.75) == 1500
    # 100% → 原文长度
    assert summary_target_words("内容" * 1000, 1.0) == 2000
    # 短内容按原文长度返回，不强行抬到 100 字下限
    assert summary_target_words("短", 0.1) == 1


class ShortThenLongLLM(FakeLLM):
    """第一次浓缩输出过短，重试时输出恰好达标的文本。"""

    def __init__(self):
        super().__init__()
        self.condense_calls = 0

    def complete(self, prompt, system="", max_tokens=2000):
        self.calls.append(prompt)
        if "浓缩" in prompt and "【句】" not in prompt:
            self.condense_calls += 1
            m = re.search(r"浓缩结果约 (\d+) 字", prompt)
            n = int(m.group(1)) if m else 100
            if self.condense_calls == 1:
                return "太短" * 10  # 20 字，远低于目标
            return "内容" * (n // 2)  # 恰好达标
        return super().complete(prompt, system, max_tokens)


def test_summarize_chapter_retries_when_too_short():
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    llm = ShortThenLongLLM()
    result = summarize_chapter(llm, chapter.title, chapter.content, 0.5)  # 目标1000字
    assert llm.condense_calls == 2  # 触发一次重试
    assert count_chars(result) == 1000  # 重试后字数达标
    assert "上次输出" in llm.calls[-1]  # 重试 prompt 带字数反馈


def test_summarize_chapter_no_retry_when_on_target(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    calls_before = len(fake_llm.calls)
    result = summarize_chapter(fake_llm, chapter.title, chapter.content, 0.5)
    # FakeLLM 返回恰好达标的文本，不应触发重试
    assert len(fake_llm.calls) == calls_before + 1
    assert count_chars(result) == 1000


def test_summarize_chapter_full_returns_original(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 约2000字
    calls_before = len(fake_llm.calls)
    result = summarize_chapter(fake_llm, chapter.title, chapter.content, 1.0)
    assert result == chapter.content  # 100% 直接返回原文
    assert len(fake_llm.calls) == calls_before  # 不调用 LLM


def test_explain_chapter_plain(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 100, order=0)
    text = explain_chapter_plain(fake_llm, chapter.title, chapter.content)
    assert "大白话" in fake_llm.calls[-1]
    assert "初中生" in fake_llm.calls[-1]
    assert text == "这一章用大白话讲：先把问题拆小，再一步步解决，就像搭积木一样。"


def test_explain_chapter_plain_target_words(fake_llm):
    # 长章 → 目标 500 字上限
    explain_chapter_plain(fake_llm, "长章", "内容" * 1000)
    assert "约 500 字" in fake_llm.calls[-1]
    assert "400~600" in fake_llm.calls[-1]
    # 短章 → 目标 100 字下限
    explain_chapter_plain(fake_llm, "短章", "内容" * 20)
    assert "约 100 字" in fake_llm.calls[-1]


def test_explain_chapter_by_ratio_condenses_first(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    text = explain_chapter_by_ratio(fake_llm, chapter.title, chapter.content, 0.1)
    # 先按比例浓缩，再对浓缩结果讲解，共两次调用
    assert len(fake_llm.calls) == 2
    assert "浓缩" in fake_llm.calls[0]
    assert "大白话" in fake_llm.calls[1]
    assert text == "这一章用大白话讲：先把问题拆小，再一步步解决，就像搭积木一样。"


def test_explain_chapter_by_ratio_full_no_extra_condense(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    text = explain_chapter_by_ratio(fake_llm, chapter.title, chapter.content, 1.0)
    # 100% 时浓缩直接返回原文，不额外调用 LLM，讲解对象是全文
    assert len(fake_llm.calls) == 1
    assert "大白话" in fake_llm.calls[0]
    assert "内容内容" in fake_llm.calls[0]
    assert text == "这一章用大白话讲：先把问题拆小，再一步步解决，就像搭积木一样。"


def test_explain_chapter_plain_explicit_target_words(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    explain_chapter_plain(fake_llm, chapter.title, chapter.content, target_words=800)
    assert "约 800 字" in fake_llm.calls[-1]
    assert "640~960" in fake_llm.calls[-1]


class LongCondenseLLM(FakeLLM):
    """浓缩输出足够长，避免讲解目标字数被内容长度截断。"""

    def complete(self, prompt, system="", max_tokens=2000):
        if "大白话" in prompt:
            return super().complete(prompt, system, max_tokens)
        return "浓缩内容。" * 200  # 1000 字


def test_explain_chapter_by_ratio_target_grows_with_ratio():
    llm = LongCondenseLLM()
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    # 75% → 约 625 字
    explain_chapter_by_ratio(llm, chapter.title, chapter.content, 0.75)
    assert "约 625 字" in llm.calls[-1]
    # 100% → 约 800 字，篇幅随比例单调递增
    explain_chapter_by_ratio(llm, chapter.title, chapter.content, 1.0)
    assert "约 800 字" in llm.calls[-1]


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
    assert sentences[0]["text"] == "摘要句一。"
    assert sentences[0]["source"] == "原文句一。"
    assert sentences[1]["text"] == "摘要句二。"
    assert sentences[1]["source"] == "原文句二。"


class NoMarkupLLM(FakeLLM):
    """浓缩输出不使用【句】【源】标记，触发 fallback 分支。"""

    def complete(self, prompt, system="", max_tokens=2000):
        if "浓缩" in prompt and "【句】" in prompt:
            return "没有使用标记格式的纯文本摘要。"
        return super().complete(prompt, system, max_tokens)


def test_summarize_chapter_with_sources_fallback():
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)
    summary, sentences = summarize_chapter_with_sources(
        NoMarkupLLM(), chapter.title, chapter.content, 0.1
    )
    # LLM 不返回标记格式，fallback 为单个无来源句子
    assert len(sentences) == 1
    assert sentences[0]["source"] == ""
    assert summary == sentences[0]["text"]


def test_summarize_chapter_with_sources_full_returns_original(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)
    calls_before = len(fake_llm.calls)
    summary, sentences = summarize_chapter_with_sources(fake_llm, chapter.title, chapter.content, 1.0)
    assert summary == chapter.content
    assert sentences == [{
        "text": chapter.content,
        "source": chapter.content,
        "context": chapter.content,
        "highlight": chapter.content,
    }]
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


def test_retrieve_context_includes_neighbor_paragraphs():
    content = (
        "第一段：人工智能正在改变世界。\n\n"
        "第二段：从制造业到服务业，AI 的应用无处不在。这场变革比工业革命更深远。\n\n"
        "第三段：企业必须拥抱变革。"
    )
    context, highlight = _retrieve_context(content, "AI 的应用无处不在，变革比工业革命更深远")
    assert "第一段" in context
    assert "第三段" in context
    assert "制造业" in highlight
    assert "工业革命" in highlight


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
    s = sentences[0]
    assert "…" not in s["source"]
    assert "人工智能" in s["source"]
    # 上下文包含关联段落，highlight 是其中的子串
    assert s["context"]
    assert s["highlight"]
    assert s["highlight"] in s["context"]


def test_summarize_chapter_with_sources_keeps_valid_source():
    content = (
        "第一段：人工智能正在深刻改变我们的世界，它不再只是实验室里的技术。\n\n"
        "第二段：从制造业到服务业，从医疗到教育，AI 的应用无处不在。这场变革比工业革命更加深远。\n\n"
        "第三段：企业必须拥抱这场变革，否则将被时代淘汰。"
    ) * 10
    chapter = Chapter(title="测试章", content=content, order=0)
    summary, sentences = summarize_chapter_with_sources(SourceLLM(), chapter.title, chapter.content, 0.5)
    assert len(sentences) == 2
    for s in sentences:
        assert s["context"]
        assert s["highlight"]
        assert s["highlight"] in s["context"]

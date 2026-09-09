"""解读器测试。"""

from book_interpreter.interpreter import (
    _chunk_content,
    _ensure_paragraphs,
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


class ShortThenExtendedLLM(FakeLLM):
    """初始浓缩输出过短，续写补正后达到目标。"""

    def __init__(self):
        super().__init__()
        self.condense_calls = 0
        self.extend_calls = 0

    def complete(self, prompt, system="", max_tokens=2000):
        self.calls.append(prompt)
        if "续写补充" in prompt:
            self.extend_calls += 1
            return "补充内容。" * 200  # 1000 字
        if "浓缩" in prompt and "【句】" not in prompt:
            self.condense_calls += 1
            return "太短" * 10  # 20 字，远低于目标
        return super().complete(prompt, system, max_tokens)


def test_summarize_chapter_extends_when_too_short():
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    llm = ShortThenExtendedLLM()
    result = summarize_chapter(llm, chapter.title, chapter.content, 0.5)  # 目标1000字
    assert llm.condense_calls == 1  # 仅一次初始浓缩
    assert llm.extend_calls == 1  # 字数不足触发一次续写补正
    assert "续写补充" in llm.calls[1]
    assert 900 <= count_chars(result) <= 1100  # 补正后字数达标


def test_summarize_chapter_no_retry_when_on_target(fake_llm):
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    calls_before = len(fake_llm.calls)
    result = summarize_chapter(fake_llm, chapter.title, chapter.content, 0.5)
    # FakeLLM 返回恰好达标的文本，不应触发重试
    assert len(fake_llm.calls) == calls_before + 1
    assert count_chars(result) == 1000
    # 浓缩 prompt 明确要求分段，避免整篇一个段落
    assert "按逻辑分为若干段落" in fake_llm.calls[-1]


def test_ensure_paragraphs():
    # 长文本无空行 → 按句切分为多段
    text = "第一点内容。" * 10 + "第二点内容。" * 10 + "第三点内容。" * 10
    out = _ensure_paragraphs(text)
    assert "\n\n" in out
    assert out.count("\n\n") >= 2
    assert count_chars(out) == count_chars(text)  # 分段不影响字数
    # 已有空行分隔 → 原样返回
    already = "第一段。\n\n第二段。"
    assert _ensure_paragraphs(already) == already
    # 过短文本 → 原样返回
    short = "很短的内容。"
    assert _ensure_paragraphs(short) == short
    # 单句长文本 → 保持原样
    one = "这是一个很长但没有句号的句子" * 30
    assert _ensure_paragraphs(one) == one


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
    assert "普通读者" in fake_llm.calls[-1]
    assert "初中生" not in fake_llm.calls[-1]
    assert "同学" not in fake_llm.calls[-1]
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
    """浓缩输出恰好达标（1500 字），避免触发补正干扰讲解字数断言。"""

    def complete(self, prompt, system="", max_tokens=2000):
        if "大白话" in prompt:
            return super().complete(prompt, system, max_tokens)
        return "浓缩内容。" * 300  # 1500 字


def test_explain_chapter_by_ratio_target_grows_with_ratio():
    llm = LongCondenseLLM()
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    # 75% → 原文 2000 字 × 0.75 = 约 1500 字，与浓缩目标一致
    explain_chapter_by_ratio(llm, chapter.title, chapter.content, 0.75)
    assert "约 1500 字" in llm.calls[-1]
    # 100% → 约 2000 字，讲解全文，篇幅随比例单调递增
    explain_chapter_by_ratio(llm, chapter.title, chapter.content, 1.0)
    assert "约 2000 字" in llm.calls[-1]


def test_explain_chapter_by_ratio_target_matches_condense():
    """讲解目标字数与浓缩目标字数一致（同为 原文可见字数 × 比例）。"""
    llm = LongCondenseLLM()
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)  # 2000字
    explain_chapter_by_ratio(llm, chapter.title, chapter.content, 0.5)
    assert "约 1000 字" in llm.calls[-1]
    assert summary_target_words(chapter.content, 0.5) == 1000


def _long_paras(n: int = 20, per: int = 100) -> str:
    """构造 n 段、每段约 per*4 字的长文本（超过原 6000 截断）。"""
    return "\n\n".join(f"第{i}段。" + "细节内容。" * per for i in range(n))


def test_explain_plain_100pct_covers_all_content(fake_llm):
    """原文超 6000 字时，100% 讲解必须把全部内容送进讲解，不得截断。"""
    content = _long_paras()
    assert count_chars(content) > 6000  # 确保覆盖原截断场景
    explain_chapter_by_ratio(fake_llm, "长章", content, 1.0)
    # 100% 浓缩直接返回原文不调 LLM；超长内容分块讲解 → 多次调用
    assert len(fake_llm.calls) >= 2, "超长内容应分块讲解"
    all_prompts = "".join(fake_llm.calls)
    for i in range(20):
        assert f"第{i}段" in all_prompts, f"第{i}段的内容应进入讲解输入"
    assert "不得遗漏任何部分" in all_prompts, "讲解应明确要求覆盖全部内容"


def test_explain_plain_low_ratio_still_covers_all_points(fake_llm):
    """低比例讲解也要求覆盖全部要点（简略但完整）。"""
    content = _long_paras()
    explain_chapter_by_ratio(fake_llm, "长章", content, 0.1)
    assert "不得遗漏任何部分" in "".join(fake_llm.calls)
    assert "每个要点都必须提到" in "".join(fake_llm.calls)


def test_explain_plain_chunks_joined(fake_llm):
    """分块讲解结果用空行拼接，顺序保持。"""
    content = _long_paras()
    text = explain_chapter_by_ratio(fake_llm, "长章", content, 1.0)
    block = "这一章用大白话讲：先把问题拆小，再一步步解决，就像搭积木一样。"
    assert text == "\n\n".join([block] * len(fake_llm.calls))


def test_chunk_content_splits_and_keeps_order():
    """分块：每块不超上限、顺序保持、内容完整。"""
    content = _long_paras()
    chunks = _chunk_content(content)
    assert len(chunks) >= 2
    for c in chunks:
        assert count_chars(c) <= 4500, f"块超上限: {count_chars(c)}"
    assert "第0段" in chunks[0]
    assert "第19段" in chunks[-1]
    assert count_chars("".join(chunks)) == count_chars(content), "分块拼接后内容应完整"


def test_chunk_content_splits_single_huge_paragraph():
    """无空行的超长单段：按句子切分，仍能分块且不丢内容。"""
    content = "。".join("句子" * 500 for _ in range(30)) + "。"
    chunks = _chunk_content(content)
    assert len(chunks) >= 2
    for c in chunks:
        assert count_chars(c) <= 4500
    assert count_chars("".join(chunks)) == count_chars(content)


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
    assert len(sentences) == 2
    assert sentences[0]["text"] == "这是第一句摘要。"
    assert sentences[0]["source"] == "这是第一句对应的原文。"
    assert sentences[1]["text"] == "这是第二句摘要。"
    assert sentences[1]["source"] == "这是第二句对应的原文。"


def test_parse_summary_with_sources_paragraphs():
    """LLM 输出中的空行被解析为段落分隔（para 段号递增）。"""
    text = (
        "【句】第一段句子一。\n"
        "【源】原文一。\n"
        "【句】第一段句子二。\n"
        "【源】原文二。\n"
        "\n"
        "【句】第二段句子。\n"
        "【源】原文三。\n"
    )
    sentences = _parse_summary_with_sources(text)
    assert sentences[0]["para"] == 0
    assert sentences[1]["para"] == 0
    assert sentences[2]["para"] == 1


def test_parse_summary_with_sources_auto_split_paragraphs():
    """LLM 未用空行分段时，多句自动均分为若干段落。"""
    text = "".join(f"【句】第{i}句内容。\n【源】原文{i}。\n" for i in range(8))
    sentences = _parse_summary_with_sources(text)
    paras = {s["para"] for s in sentences}
    assert len(paras) > 1  # 自动分了段
    # 段号单调不减
    vals = [s["para"] for s in sentences]
    assert vals == sorted(vals)


def test_parse_summary_with_sources_missing_source():
    sentences = _parse_summary_with_sources("【句】只有摘要没有原文。\n")
    assert sentences == [{"text": "只有摘要没有原文。", "source": "", "para": 0}]


class SourceLLM(FakeLLM):
    """输出【句】【源】标记，且摘要句总字数恰好达标避免触发补正。"""

    def complete(self, prompt, system="", max_tokens=2000):
        if "【句】" in prompt:
            import re

            m = re.search(r"浓缩结果约 (\d+) 字", prompt)
            n = int(m.group(1)) if m else 100
            fill = max(0, n - 10)
            return (
                f"【句】摘要句一。{'内' * fill}\n"
                f"【源】原文句一。{'内' * fill}\n"
                f"【句】摘要句二。\n"
                f"【源】原文句二。\n"
            )
        return super().complete(prompt, system, max_tokens)


def test_summarize_chapter_with_sources():
    chapter = Chapter(title="测试章", content="内容" * 1000, order=0)
    summary, sentences = summarize_chapter_with_sources(SourceLLM(), chapter.title, chapter.content, 0.1)
    assert len(sentences) == 2
    assert sentences[0]["text"].startswith("摘要句一。")
    assert sentences[0]["source"].startswith("原文句一。")
    assert sentences[1]["text"] == "摘要句二。"
    assert sentences[1]["source"] == "原文句二。"
    assert summary.startswith("摘要句一。")
    assert summary.endswith("摘要句二。")


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
    """输出含省略号的过短原文摘录，且摘要句总字数达标避免触发补正。"""

    def complete(self, prompt, system="", max_tokens=2000):
        if "【句】" in prompt:
            import re

            m = re.search(r"浓缩结果约 (\d+) 字", prompt)
            n = int(m.group(1)) if m else 100
            fill = max(0, n - 35)
            return (
                f"【句】人工智能正在深刻改变我们的世界，这场变革比工业革命更加深远。{'内' * fill}\n"
                f"【源】原文开头……原文结尾。\n"
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

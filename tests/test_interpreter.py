"""解读器测试。"""

from book_interpreter.interpreter import _parse_list, extract_chapter_titles, interpret_book
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

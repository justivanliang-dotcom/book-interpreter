"""演示脚本测试：验证模拟 LLM 解读管线可生成完整报告。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo.demo_interpret import MockLLM
from book_interpreter.interpreter import interpret_book
from book_interpreter.parser import parse_book

SAMPLE = Path(__file__).resolve().parents[1] / "sample" / "sample_book.md"


def _load_book() -> object:
    return parse_book(SAMPLE.read_text(encoding="utf-8"))


def test_mock_llm_generates_full_interpretation() -> None:
    interp = interpret_book(MockLLM(), _load_book())
    assert interp.overview
    assert len(interp.key_points) == 5
    assert len(interp.quotes) == 3
    assert all(c.summary for c in interp.book.chapters)


def test_mock_llm_keywords_are_chinese_bigrams() -> None:
    from demo.demo_interpret import _extract_keywords

    keywords = _extract_keywords("刻意练习是提升技能的关键方法")
    assert keywords
    assert all(len(k) == 2 for k in keywords)

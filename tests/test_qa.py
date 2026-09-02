"""问答模块测试。"""

from book_interpreter.models import Book, Chapter
from book_interpreter.qa import answer_question
from book_interpreter.retriever import Retriever


def _make_book() -> Book:
    return Book(
        title="测试书",
        chapters=[
            Chapter(title="第一章", content="苹果富含维生素，适合每天食用。", order=0),
            Chapter(title="第二章", content="汽车是现代重要的交通工具。", order=1),
        ],
    )


def test_answer_question_uses_llm(fake_llm):
    book = _make_book()
    answer = answer_question(fake_llm, book, "苹果有什么好处？")
    assert answer


def test_answer_question_with_custom_retriever(fake_llm):
    book = _make_book()
    retriever = Retriever(["苹果富含维生素。"])
    answer = answer_question(fake_llm, book, "苹果有什么好处？", retriever=retriever)
    assert answer


def test_answer_question_no_match(fake_llm):
    book = _make_book()
    retriever = Retriever(["完全不相关的内容。"])
    answer = answer_question(fake_llm, book, "苹果有什么好处？", retriever=retriever)
    assert "未在书籍内容中找到" in answer

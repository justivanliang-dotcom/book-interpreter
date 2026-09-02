"""检索器测试。"""

import pytest

from book_interpreter.models import Book, Chapter
from book_interpreter.retriever import Retriever, build_retriever, chunk_text


def test_chunk_text_basic():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=400, overlap=100)
    assert len(chunks) >= 3
    assert all(len(c) <= 400 for c in chunks)


def test_chunk_text_empty():
    assert chunk_text("   ") == []


def test_chunk_text_invalid_params():
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=100, overlap=200)


def test_retrieve_relevant_chunk():
    chunks = [
        "苹果是一种常见的水果，富含维生素。",
        "汽车是一种交通工具，使用汽油或电力。",
        "这本书讲述了个人成长的方法。",
    ]
    retriever = Retriever(chunks)
    hits = retriever.retrieve("苹果的营养价值", top_k=1)
    assert hits and hits[0][0] == chunks[0]


def test_retrieve_empty():
    retriever = Retriever([])
    assert retriever.retrieve("任何问题") == []


def test_build_retriever_from_book():
    book = Book(
        title="测试书",
        chapters=[
            Chapter(title="章一", content="这里讲的是如何种植番茄。", order=0),
            Chapter(title="章二", content="这里讲的是如何烘焙面包。", order=1),
        ],
    )
    retriever = build_retriever(book)
    hits = retriever.retrieve("番茄怎么种", top_k=1)
    assert hits and "番茄" in hits[0][0]

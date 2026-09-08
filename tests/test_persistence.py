"""书籍与结果持久化测试：上传/浓缩/讲解落盘后重启恢复。"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FakeLLM
from webapp import persistence
from webapp.main import _books, app, get_llm
from webapp.ratelimit import limiter

client = TestClient(app)
app.dependency_overrides[get_llm] = lambda: FakeLLM()


class CountingLLM(FakeLLM):
    """记录每次 LLM 调用，用于验证缓存命中不触发重新生成。"""

    def __init__(self):
        super().__init__()
        self.prompts = []

    def complete(self, prompt, system="", max_tokens=2000):
        self.prompts.append(prompt)
        return super().complete(prompt, system, max_tokens)


@pytest.fixture(autouse=True)
def clear_books():
    _books.clear()
    limiter.reset()
    yield
    _books.clear()
    limiter.reset()


def _restart():
    """模拟服务重启：清空内存后从磁盘重新加载全部书籍记录。"""
    _books.clear()
    _books.update(persistence.load_state())


def _upload(title="持久化测试书", content=None):
    if content is None:
        content = f"# {title}\n\n## 第一章\n内容一\n\n## 第二章\n内容二"
    return client.post(
        "/api/books",
        files={"file": ("book.md", content, "text/markdown")},
    )


def _book_id(resp) -> str:
    assert resp.status_code == 200
    return resp.json()["id"]


def test_upload_persisted_and_listed():
    book_id = _book_id(_upload())
    assert persistence.book_state_path(book_id).exists()
    assert persistence.raw_text_path(book_id).exists()

    _restart()
    resp = client.get("/api/books")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == book_id
    assert items[0]["title"] == "持久化测试书"
    assert len(items[0]["chapters"]) == 2


def test_raw_text_roundtrip():
    book_id = _book_id(_upload())
    _restart()
    resp = client.get(f"/api/books/{book_id}/raw")
    assert resp.status_code == 200
    assert "# 持久化测试书" in resp.json()["text"]


def test_summarize_cache_hits_after_restart():
    counting = CountingLLM()
    app.dependency_overrides[get_llm] = lambda: counting
    try:
        book_id = _book_id(_upload())
        url = f"/api/books/{book_id}/chapters/0/summarize?ratio=0.25"
        r1 = client.post(url)
        assert r1.status_code == 200
        n1 = len(counting.prompts)

        _restart()
        r2 = client.post(url)
        assert r2.status_code == 200
        assert len(counting.prompts) == n1  # 重启后命中落盘缓存，不调 LLM
        assert r2.json()["summary"] == r1.json()["summary"]
        assert r2.json()["word_count"] == r1.json()["word_count"]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()


def test_plain_cache_hits_after_restart():
    counting = CountingLLM()
    app.dependency_overrides[get_llm] = lambda: counting
    try:
        book_id = _book_id(_upload())
        url = f"/api/books/{book_id}/chapters/1/plain?ratio=0.5"
        r1 = client.post(url)
        assert r1.status_code == 200
        n1 = len(counting.prompts)

        _restart()
        r2 = client.post(url)
        assert r2.status_code == 200
        assert len(counting.prompts) == n1
        assert r2.json()["text"] == r1.json()["text"]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()


def test_list_books_flags_and_ratios():
    book_id = _book_id(_upload())
    client.post(f"/api/books/{book_id}/chapters/0/summarize?ratio=0.5")
    client.post(f"/api/books/{book_id}/chapters/0/plain?ratio=0.25")

    items = client.get("/api/books").json()
    chapters = items[0]["chapters"]
    ch0, ch1 = chapters[0], chapters[1]
    assert ch0["has_summary"] is True
    assert ch0["summary_ratio"] == 0.5
    assert ch0["has_plain"] is True
    assert ch0["plain_ratio"] == 0.25
    assert ch1["has_summary"] is False
    assert ch1["has_plain"] is False


def test_interpretation_persisted():
    book_id = _book_id(_upload())
    resp = client.post(f"/api/books/{book_id}/interpret")
    assert resp.status_code == 200
    overview = resp.json()["overview"]

    _restart()
    assert _books[book_id]["interpretation"] is not None
    assert _books[book_id]["interpretation"].overview == overview
    assert _books[book_id]["interpretation"].key_points


def test_empty_state_dir_loads_nothing():
    _restart()
    assert client.get("/api/books").json() == []

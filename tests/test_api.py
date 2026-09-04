"""Web API 测试。"""

import pytest
from fastapi.testclient import TestClient

from book_interpreter.llm import LLMError
from tests.conftest import FakeLLM
from webapp.main import _books, app, get_llm

client = TestClient(app)
app.dependency_overrides[get_llm] = lambda: FakeLLM()


class FailingLLM(FakeLLM):
    def complete(self, prompt, system="", max_tokens=2000):
        raise LLMError("未配置 LLM_API_KEY")


class CountingLLM(FakeLLM):
    """记录每次 LLM 调用的提示词，用于验证调用顺序。"""

    def __init__(self):
        super().__init__()
        self.prompts = []

    def complete(self, prompt, system="", max_tokens=2000):
        self.prompts.append(prompt)
        return super().complete(prompt, system, max_tokens)


@pytest.fixture(autouse=True)
def clear_books():
    _books.clear()
    yield
    _books.clear()


def _upload(title="测试书", content=None):
    if content is None:
        content = f"# {title}\n\n## 第一章\n内容一\n\n## 第二章\n内容二"
    return client.post(
        "/api/books",
        files={"file": ("book.md", content, "text/markdown")},
    )


def test_index_serves_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "书籍解读器" in resp.text


def test_upload_book():
    resp = _upload()
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "测试书"
    assert len(data["chapters"]) == 2
    assert data["chapters"][0]["title"] == "第一章"


def test_upload_non_utf8():
    resp = client.post(
        "/api/books",
        files={"file": ("book.md", b"\xff\xfe\x00 invalid", "text/markdown")},
    )
    assert resp.status_code == 400


def test_raw_returns_original_text():
    content = "# 测试书\n\n## 第一章\n内容一\n\n## 第二章\n内容二"
    book = _upload(content=content).json()
    resp = client.get(f"/api/books/{book['id']}/raw")
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == content
    assert data["filename"] == "book.md"


def test_raw_not_found():
    resp = client.get("/api/books/nonexistent/raw")
    assert resp.status_code == 404


def test_interpret_book():
    book = _upload().json()
    resp = client.post(f"/api/books/{book['id']}/interpret")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overview"]
    assert len(data["key_points"]) == 5
    assert len(data["quotes"]) == 3
    # 章节浓缩按需生成，interpret 不填充章节摘要
    assert data["chapters"][0]["summary"] == ""


def test_summarize_chapter():
    book = _upload().json()
    resp = client.post(f"/api/books/{book['id']}/chapters/0/summarize?ratio=0.5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "第一章"
    assert data["summary"]
    assert isinstance(data["sentences"], list)
    assert data["sentences"][0]["text"]


def test_summarize_chapter_ratio_5_percent():
    # 5% 比例应通过参数校验
    content = f"# 测试书\n\n## 第一章\n{'内容' * 500}\n\n## 第二章\n{'内容' * 500}"
    book = _upload(content=content).json()
    resp = client.post(f"/api/books/{book['id']}/chapters/0/summarize?ratio=0.05")
    assert resp.status_code == 200
    assert resp.json()["summary"]


def test_summarize_chapter_not_found():
    book = _upload().json()
    resp = client.post(f"/api/books/{book['id']}/chapters/99/summarize")
    assert resp.status_code == 404


def test_summarize_chapter_llm_error():
    app.dependency_overrides[get_llm] = lambda: FailingLLM()
    try:
        # 章节内容足够长，确保触发 LLM 调用而非直接返回原文
        content = f"# 测试书\n\n## 第一章\n{'内容' * 500}\n\n## 第二章\n{'内容' * 500}"
        book = _upload(content=content).json()
        resp = client.post(f"/api/books/{book['id']}/chapters/0/summarize")
        assert resp.status_code == 502
        assert "LLM_API_KEY" in resp.json()["detail"]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()


def test_explain_plain():
    book = _upload().json()
    resp = client.post(f"/api/books/{book['id']}/chapters/0/plain")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "第一章"
    assert data["text"]
    assert "大白话" in data["text"]


def test_explain_plain_not_found():
    book = _upload().json()
    resp = client.post(f"/api/books/{book['id']}/chapters/99/plain")
    assert resp.status_code == 404


def test_explain_plain_empty_chapter():
    content = "# 测试书\n\n## 第一章\n内容一\n\n## 第二章\n   "
    book = _upload(content=content).json()
    resp = client.post(f"/api/books/{book['id']}/chapters/1/plain")
    assert resp.status_code == 200
    assert resp.json()["text"] == "（本章无内容）"


def test_explain_plain_ratio_condenses_first():
    counting = CountingLLM()
    app.dependency_overrides[get_llm] = lambda: counting
    try:
        content = f"# 测试书\n\n## 第一章\n{'内容' * 500}\n\n## 第二章\n{'内容' * 500}"
        book = _upload(content=content).json()
        resp = client.post(f"/api/books/{book['id']}/chapters/0/plain?ratio=0.1")
        assert resp.status_code == 200
        assert resp.json()["text"]
        # 小比例：先浓缩再讲解，共两次 LLM 调用
        assert len(counting.prompts) == 2
        assert "浓缩" in counting.prompts[0]
        assert "大白话" in counting.prompts[1]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()


def test_explain_plain_ratio_100_skips_condense():
    counting = CountingLLM()
    app.dependency_overrides[get_llm] = lambda: counting
    try:
        content = f"# 测试书\n\n## 第一章\n{'内容' * 500}\n\n## 第二章\n{'内容' * 500}"
        book = _upload(content=content).json()
        resp = client.post(f"/api/books/{book['id']}/chapters/0/plain?ratio=1.0")
        assert resp.status_code == 200
        assert resp.json()["text"]
        # 100%：浓缩直接返回原文，仅一次讲解调用，且讲解 prompt 含全文
        assert len(counting.prompts) == 1
        assert "大白话" in counting.prompts[0]
        assert "内容内容" in counting.prompts[0]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()


def test_explain_plain_llm_error():
    app.dependency_overrides[get_llm] = lambda: FailingLLM()
    try:
        content = f"# 测试书\n\n## 第一章\n{'内容' * 100}\n\n## 第二章\n{'内容' * 100}"
        book = _upload(content=content).json()
        resp = client.post(f"/api/books/{book['id']}/chapters/0/plain")
        assert resp.status_code == 502
        assert "LLM_API_KEY" in resp.json()["detail"]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()


def test_interpret_book_not_found():
    resp = client.post("/api/books/nonexistent/interpret")
    assert resp.status_code == 404


def test_interpret_llm_error():
    app.dependency_overrides[get_llm] = lambda: FailingLLM()
    try:
        book = _upload().json()
        resp = client.post(f"/api/books/{book['id']}/interpret")
        assert resp.status_code == 502
        assert "LLM_API_KEY" in resp.json()["detail"]
    finally:
        app.dependency_overrides[get_llm] = lambda: FakeLLM()


def test_ask_question():
    book = _upload().json()
    resp = client.post(
        f"/api/books/{book['id']}/ask",
        json={"question": "这本书讲了什么？"},
    )
    assert resp.status_code == 200
    assert resp.json()["answer"]


def test_ask_empty_question():
    book = _upload().json()
    resp = client.post(
        f"/api/books/{book['id']}/ask",
        json={"question": "   "},
    )
    assert resp.status_code == 400


def test_report_md_export():
    book = _upload().json()
    client.post(f"/api/books/{book['id']}/interpret")
    resp = client.get(f"/api/books/{book['id']}/report?format=md")
    assert resp.status_code == 200
    assert "解读报告" in resp.text
    assert "text/markdown" in resp.headers["content-type"]


def test_report_html_export():
    book = _upload().json()
    client.post(f"/api/books/{book['id']}/interpret")
    resp = client.get(f"/api/books/{book['id']}/report?format=html")
    assert resp.status_code == 200
    assert "<html" in resp.text
    assert "text/html" in resp.headers["content-type"]


def test_report_before_interpret():
    book = _upload().json()
    resp = client.get(f"/api/books/{book['id']}/report?format=md")
    assert resp.status_code == 400


def test_report_unsupported_format():
    book = _upload().json()
    client.post(f"/api/books/{book['id']}/interpret")
    resp = client.get(f"/api/books/{book['id']}/report?format=pdf")
    assert resp.status_code == 400

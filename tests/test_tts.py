"""豆包语音合成模块与 /api/tts/* 接口测试。"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

import webapp.tts as tts_mod
from webapp.main import _books, app
from webapp.ratelimit import limiter
from webapp.tts import TTSUnavailable

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    monkeypatch.delenv("VOLC_TTS_SPEAKER", raising=False)
    _books.clear()
    limiter.reset()
    yield
    _books.clear()
    limiter.reset()


class FakeResp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def _ok_resp(*texts: str) -> FakeResp:
    """构造合法的豆包流式响应：每段文本对应一个 base64 data chunk。"""
    lines = []
    for t in texts:
        lines.append(
            '{"code":0,"message":"OK","data":"%s","usage":{"text_words":%d}}'
            % (base64.b64encode(t.encode()).decode(), len(t))
        )
    return FakeResp(text="\n".join(lines))


def test_tts_configured_default(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    monkeypatch.setattr(tts_mod, "_edge_available", lambda: True)
    assert tts_mod.tts_configured() is True


def test_tts_configured_no_edge(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    monkeypatch.setattr(tts_mod, "_edge_available", lambda: False)
    assert tts_mod.tts_configured() is False


def test_tts_configured_with_key(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "abc123")
    assert tts_mod.tts_configured() is True


def test_clean_markdown_for_speech_bold_and_symbols():
    """带 ** 加粗的句子（如截图里的场景）应被清洗，防止 TTS 合成失败回退机械声。"""
    raw = "说完错误一，咱们接着看第二个坑——**大家都想轻轻松松摘果子，没人愿意去种树**。"
    cleaned = tts_mod.clean_markdown_for_speech(raw)
    assert "**" not in cleaned, "加粗符号应被清除，否则 edge-tts 可能失败并回退机械声"
    assert "大家都想轻轻松松摘果子" in cleaned
    assert cleaned.endswith("。")


def test_clean_markdown_for_speech_variety():
    """各种 markdown 语法与残余符号都应被清掉。"""
    samples = [
        ("`代码` 片段", "代码 片段"),
        ("*斜体* 字", "斜体 字"),
        ("~~删除~~ 线", "删除 线"),
        ("[链接](https://x.com)", "链接"),
        ("![图片](a.png)", "图片"),
        ("# 标题\n正文", "标题 正文"),
        ("- 列表项\n- 第二项", "列表项 第二项"),
        ("1. 有序\n2. 第二", "有序 第二"),
        ("> 引用段", "引用段"),
        ("正常句子。", "正常句子。"),
    ]
    for raw, expected in samples:
        assert tts_mod.clean_markdown_for_speech(raw) == expected, f"失败: {raw!r}"


def test_synthesize_ok(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "k")
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return _ok_resp("你好，语音测试")

    monkeypatch.setattr(tts_mod.requests, "post", fake_post)
    audio = tts_mod.synthesize("你好，语音测试")
    assert audio == "你好，语音测试".encode()
    url, payload, headers = calls[0]
    assert url == tts_mod.TTS_URL
    assert payload["req_params"]["text"] == "你好，语音测试"
    assert payload["req_params"]["speaker"] == tts_mod.DEFAULT_SPEAKER
    assert payload["req_params"]["audio_params"]["format"] == "mp3"
    assert headers["X-Api-Key"] == "k"
    assert headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert headers["X-Api-Request-Id"]


def test_synthesize_custom_speaker(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "k")
    monkeypatch.setenv("VOLC_TTS_SPEAKER", "zh_female_xiaohe_uranus_bigtts")
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["speaker"] = json["req_params"]["speaker"]
        return _ok_resp("x")

    monkeypatch.setattr(tts_mod.requests, "post", fake_post)
    tts_mod.synthesize("x")
    assert seen["speaker"] == "zh_female_xiaohe_uranus_bigtts"


def test_synthesize_no_key_uses_edge(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    monkeypatch.setattr(tts_mod, "_edge_synthesize", lambda t: t.encode())
    assert tts_mod.synthesize("你好") == "你好".encode()


def test_synthesize_http_error(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "k")
    monkeypatch.setattr(tts_mod.requests, "post", lambda *a, **k: FakeResp(401, "unauthorized"))
    with pytest.raises(TTSUnavailable, match="401"):
        tts_mod.synthesize("你好")


def test_synthesize_business_error(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "k")
    monkeypatch.setattr(
        tts_mod.requests,
        "post",
        lambda *a, **k: FakeResp(text='{"code":400,"message":"bad speaker"}'),
    )
    with pytest.raises(TTSUnavailable, match="bad speaker"):
        tts_mod.synthesize("你好")


def test_synthesize_empty_body(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "k")
    monkeypatch.setattr(tts_mod.requests, "post", lambda *a, **k: FakeResp(text=""))
    with pytest.raises(TTSUnavailable, match="空音频"):
        tts_mod.synthesize("你好")


def test_synthesize_batch_order(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "k")

    def fake_post(url, json=None, headers=None, timeout=None):
        return _ok_resp(json["req_params"]["text"])

    monkeypatch.setattr(tts_mod.requests, "post", fake_post)
    out = tts_mod.synthesize_batch(["甲。", "乙。", "丙。"])
    assert out == ["甲。".encode(), "乙。".encode(), "丙。".encode()]


def test_api_tts_status_no_key_edge_available(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    monkeypatch.setattr(tts_mod, "_edge_available", lambda: True)
    resp = client.get("/api/tts/status")
    assert resp.status_code == 200
    assert resp.json() == {"available": True}


def test_api_tts_status_no_key_edge_missing(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    monkeypatch.setattr(tts_mod, "_edge_available", lambda: False)
    resp = client.get("/api/tts/status")
    assert resp.status_code == 200
    assert resp.json() == {"available": False}


def test_api_tts_status_with_key(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "k")
    resp = client.get("/api/tts/status")
    assert resp.status_code == 200
    assert resp.json() == {"available": True}


def test_api_tts_batch_ok(monkeypatch):
    def fake_batch(texts):
        return [t.encode() for t in texts]

    monkeypatch.setattr("webapp.main.synthesize_batch", fake_batch)
    resp = client.post("/api/tts/batch", json={"texts": ["一。", "二。"]})
    assert resp.status_code == 200
    audios = resp.json()["audios"]
    assert [base64.b64decode(a).decode() for a in audios] == ["一。", "二。"]


def test_api_tts_batch_empty():
    resp = client.post("/api/tts/batch", json={"texts": []})
    assert resp.status_code == 400


def test_api_tts_batch_too_many():
    resp = client.post("/api/tts/batch", json={"texts": ["x"] * 9})
    assert resp.status_code == 400


def test_api_tts_batch_unavailable(monkeypatch):
    def fail(texts):
        raise TTSUnavailable("未配置豆包语音 API Key")

    monkeypatch.setattr("webapp.main.synthesize_batch", fail)
    resp = client.post("/api/tts/batch", json={"texts": ["一。"]})
    assert resp.status_code == 503
    assert "未配置" in resp.json()["detail"]


# ---------- Edge 合成与重试 ----------


def _make_fake_stream(audio: bytes):
    class FakeStream:
        def __init__(self):
            self._data = [{"type": "audio", "data": audio}]

        def __aiter__(self):
            self._it = iter(self._data)
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration

    return FakeStream


def test_edge_synthesize_retry_success(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    import edge_tts

    attempts = {"n": 0}
    FakeStream = _make_fake_stream(b"abc")

    class FakeComm:
        def __init__(self, text, voice):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise OSError("connection reset")

        def stream(self):
            return FakeStream()

    monkeypatch.setattr(edge_tts, "Communicate", FakeComm)
    audio = tts_mod.synthesize("重试测试")
    assert audio == b"abc"
    assert attempts["n"] == 3


def test_edge_synthesize_retry_exhausted(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    import edge_tts

    def fail_comm(text, voice):
        raise OSError("boom")

    monkeypatch.setattr(edge_tts, "Communicate", fail_comm)
    with pytest.raises(TTSUnavailable, match="boom"):
        tts_mod.synthesize("重试测试")


def test_edge_many_retry_success(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    import edge_tts

    attempts = {"n": 0}
    FakeStream = _make_fake_stream(b"xyz")

    class FakeComm:
        def __init__(self, text, voice):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise OSError("connection reset")

        def stream(self):
            return FakeStream()

    monkeypatch.setattr(edge_tts, "Communicate", FakeComm)
    out = tts_mod.synthesize_batch(["甲。", "乙。"])
    assert out == [b"xyz", b"xyz"]
    assert attempts["n"] >= 3

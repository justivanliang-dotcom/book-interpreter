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
    assert tts_mod.tts_configured() is False


def test_tts_configured_with_key(monkeypatch):
    monkeypatch.setenv("VOLC_TTS_API_KEY", "abc123")
    assert tts_mod.tts_configured() is True


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


def test_synthesize_no_key(monkeypatch):
    monkeypatch.delenv("VOLC_TTS_API_KEY", raising=False)
    with pytest.raises(TTSUnavailable):
        tts_mod.synthesize("你好")


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


def test_api_tts_status_no_key():
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

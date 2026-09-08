"""豆包（火山引擎）语音合成：把文本合成为 mp3 音频。

使用豆包语音合成大模型 2.0（seed-tts-2.0），默认音色 Vivi 2.0
（自然普通话女声）。未配置 API Key 时抛 TTSUnavailable，
由前端回退到浏览器自带语音。
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
DEFAULT_SPEAKER = "zh_female_vv_uranus_bigtts"
_MAX_TEXT = 2000  # 单次合成文本上限（字符），超出截断
_BATCH_CONCURRENCY = 4  # 批量合成时的并发请求数


class TTSUnavailable(Exception):
    """豆包语音未配置或调用失败。"""


def tts_configured() -> bool:
    return bool(os.environ.get("VOLC_TTS_API_KEY", "").strip())


def _api_key() -> str:
    key = os.environ.get("VOLC_TTS_API_KEY", "").strip()
    if not key:
        raise TTSUnavailable("未配置豆包语音 API Key（VOLC_TTS_API_KEY）")
    return key


def synthesize(text: str) -> bytes:
    """合成单段文本为 mp3 音频字节，失败抛 TTSUnavailable。"""
    text = (text or "").strip()
    if not text:
        raise TTSUnavailable("合成文本为空")
    if len(text) > _MAX_TEXT:
        text = text[:_MAX_TEXT]
    speaker = os.environ.get("VOLC_TTS_SPEAKER", "").strip() or DEFAULT_SPEAKER
    payload = {
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": {"format": "mp3", "sample_rate": 24000},
            "disable_markdown_filter": True,
        }
    }
    headers = {
        "X-Api-Key": _api_key(),
        "X-Api-Resource-Id": "seed-tts-2.0",
        "X-Api-Request-Id": uuid.uuid4().hex,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(TTS_URL, json=payload, headers=headers, timeout=60)
    except requests.RequestException as e:
        raise TTSUnavailable(f"豆包语音请求失败：{e}") from e
    if resp.status_code != 200:
        raise TTSUnavailable(f"豆包语音返回 HTTP {resp.status_code}：{resp.text[:200]}")
    return _parse_response(resp.text)


def _parse_response(body: str) -> bytes:
    """解析单向流式响应：逐行 JSON，拼接 data 中的 base64 音频。"""
    chunks: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = obj.get("code", -1)
        if code != 0:
            raise TTSUnavailable(
                f"豆包语音合成失败（code={code}）：{obj.get('message', '')}"
            )
        data = obj.get("data")
        if data:
            chunks.append(data)
    if not chunks:
        raise TTSUnavailable("豆包语音返回空音频")
    try:
        return base64.b64decode("".join(chunks))
    except (ValueError, TypeError) as e:
        raise TTSUnavailable(f"豆包语音音频解码失败：{e}") from e


def synthesize_batch(texts: list[str]) -> list[bytes]:
    """并发合成多段文本，返回与输入顺序一致的音频字节列表。

    任一段合成失败都会抛 TTSUnavailable，由调用方整体回退。
    """
    texts = [(t or "").strip() for t in texts]
    if not texts:
        raise TTSUnavailable("合成文本列表为空")
    with ThreadPoolExecutor(max_workers=_BATCH_CONCURRENCY) as pool:
        results = list(pool.map(synthesize, texts))
    return results

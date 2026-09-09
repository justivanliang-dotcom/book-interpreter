"""语音合成：默认微软 Edge 在线神经女声（edge-tts，免费、无需 Key），
配置 VOLC_TTS_API_KEY 时优先使用豆包（火山引擎）自然女声。

未配置任何在线引擎或调用失败时抛 TTSUnavailable，由前端回退到
浏览器自带语音。
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
DEFAULT_SPEAKER = "zh_female_vv_uranus_bigtts"
EDGE_VOICE = "zh-CN-XiaoxiaoNeural"  # 晓晓神经语音：自然普通话女声
_MAX_TEXT = 2000  # 单次合成文本上限（字符），超出截断
_BATCH_CONCURRENCY = 4  # 批量合成时的并发请求数
_EDGE_RETRIES = 3  # Edge 合成遇瞬时网络错误时的重试次数


class TTSUnavailable(Exception):
    """在线语音未配置或调用失败。"""


def clean_markdown_for_speech(text: str) -> str:
    """朗读前清除 markdown 语法符号，避免合成失败或读成"星号"等。

    与前端 tts.js 的 cleanText 保持一致，服务端兜底清洗：
    即使前端漏传或缓存了旧脚本，服务器合成也不会把 ** 等符号送进 TTS。
    """
    if not text:
        return text
    t = str(text)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)  # ![alt](url) → alt
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)  # [text](url) → text
    t = re.sub(r"`([^`]*)`", r"\1", t)  # `code` → code
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)  # **bold** → bold
    t = re.sub(r"\*([^*]+)\*", r"\1", t)  # *italic* → italic
    t = re.sub(r"__([^_]+)__", r"\1", t)  # __bold__ → bold
    t = re.sub(r"_([^_]+)_", r"\1", t)  # _italic_ → italic
    t = re.sub(r"~~([^~]+)~~", r"\1", t)  # ~~del~~ → del
    t = re.sub(r"^\s{0,3}#{1,6}\s+", "", t, flags=re.MULTILINE)  # # 标题
    t = re.sub(r"^\s*>\s?", "", t, flags=re.MULTILINE)  # > 引用
    t = re.sub(r"^\s*[-+*]\s+", "", t, flags=re.MULTILINE)  # - 列表
    t = re.sub(r"^\s*\d+[.)]\s+", "", t, flags=re.MULTILINE)  # 1. 序号
    t = re.sub(r"[`*_~]", "", t)  # 残余符号一律清除
    t = re.sub(r"\s+", " ", t).strip()
    return t


def tts_configured() -> bool:
    """是否有可用的在线语音引擎（豆包配置或 edge-tts 可用）。"""
    if os.environ.get("VOLC_TTS_API_KEY", "").strip():
        return True
    return _edge_available()


def _edge_available() -> bool:
    try:
        import edge_tts  # noqa: F401

        return True
    except ImportError:
        return False


def _volc_configured() -> bool:
    return bool(os.environ.get("VOLC_TTS_API_KEY", "").strip())


def synthesize(text: str) -> bytes:
    """合成单段文本为 mp3 音频字节，失败抛 TTSUnavailable。"""
    text = clean_markdown_for_speech(text or "")
    if not text:
        raise TTSUnavailable("合成文本为空")
    if len(text) > _MAX_TEXT:
        text = text[:_MAX_TEXT]
    if _volc_configured():
        return _volc_synthesize(text)
    return _edge_synthesize(text)


def _api_key() -> str:
    key = os.environ.get("VOLC_TTS_API_KEY", "").strip()
    if not key:
        raise TTSUnavailable("未配置豆包语音 API Key（VOLC_TTS_API_KEY）")
    return key


def _volc_synthesize(text: str) -> bytes:
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
    return _parse_volc_response(resp.text)


def _parse_volc_response(body: str) -> bytes:
    """解析豆包单向流式响应：逐行 JSON，拼接 data 中的 base64 音频。"""
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


def _edge_voice() -> str:
    return os.environ.get("EDGE_TTS_VOICE", "").strip() or EDGE_VOICE


def _edge_synthesize(text: str) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(_EDGE_RETRIES):
        try:
            return asyncio.run(_edge_one(text, _edge_voice()))
        except TTSUnavailable:
            raise
        except Exception as e:  # 微软服务瞬时网络抖动，可重试
            last_exc = e
            if attempt < _EDGE_RETRIES - 1:
                time.sleep(0.5 * (attempt + 1))
    raise TTSUnavailable(f"Edge 语音合成失败：{last_exc}") from last_exc


async def _edge_one(text: str, voice: str) -> bytes:
    import edge_tts

    chunks = bytearray()
    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio" and chunk["data"]:
            chunks.extend(chunk["data"])
    if not chunks:
        raise TTSUnavailable("Edge 语音返回空音频")
    return bytes(chunks)


def synthesize_batch(texts: list[str]) -> list[bytes]:
    """并发合成多段文本，返回与输入顺序一致的音频字节列表。

    任一段合成失败都会抛 TTSUnavailable，由调用方整体回退。
    """
    texts = [clean_markdown_for_speech(t or "") for t in texts]
    if not texts:
        raise TTSUnavailable("合成文本列表为空")
    if _volc_configured():
        with ThreadPoolExecutor(max_workers=_BATCH_CONCURRENCY) as pool:
            return list(pool.map(_volc_synthesize, texts))
    try:
        return asyncio.run(_edge_many(texts, _edge_voice()))
    except TTSUnavailable:
        raise
    except Exception as e:
        raise TTSUnavailable(f"Edge 语音合成失败：{e}") from e


async def _edge_many(texts: list[str], voice: str) -> list[bytes]:
    import edge_tts

    async def one(text: str) -> bytes:
        last_exc: Exception | None = None
        for attempt in range(_EDGE_RETRIES):
            try:
                chunks = bytearray()
                communicate = edge_tts.Communicate(text, voice)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio" and chunk["data"]:
                        chunks.extend(chunk["data"])
                if not chunks:
                    raise TTSUnavailable("Edge 语音返回空音频")
                return bytes(chunks)
            except TTSUnavailable:
                raise
            except Exception as e:
                last_exc = e
                if attempt < _EDGE_RETRIES - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise TTSUnavailable(f"Edge 语音合成失败：{last_exc}") from last_exc

    return await asyncio.gather(*(one(t) for t in texts))

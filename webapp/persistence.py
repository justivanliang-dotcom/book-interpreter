"""书籍与生成结果持久化：上传的书、浓缩/讲解缓存落盘，重启后恢复。

磁盘布局（STATE_DIR，默认 webapp/data）：
  books/{book_id}.json   完整记录（book 结构、解读、浓缩/讲解缓存、最近比例）
  books/{book_id}.txt    原始提取文本（raw_text）
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from book_interpreter.models import Book, Chapter, Interpretation

STATE_DIR = Path(
    os.environ.get("BOOK_STATE_DIR", "") or (Path(__file__).parent / "data")
).expanduser()


def _ensure_dir() -> None:
    (STATE_DIR / "books").mkdir(parents=True, exist_ok=True)


def book_state_path(book_id: str) -> Path:
    return STATE_DIR / "books" / f"{book_id}.json"


def raw_text_path(book_id: str) -> Path:
    return STATE_DIR / "books" / f"{book_id}.txt"


# ---------- 序列化 ----------


def _book_to_dict(book: Book) -> dict:
    return {
        "title": book.title,
        "chapters": [
            {
                "title": c.title,
                "content": c.content,
                "order": c.order,
                "summary": c.summary,
                "plain": c.plain,
            }
            for c in book.chapters
        ],
    }


def _book_from_dict(data: dict) -> Book:
    return Book(
        title=data.get("title", "未命名书籍"),
        chapters=[
            Chapter(
                title=ch.get("title", ""),
                content=ch.get("content", ""),
                order=ch.get("order", i),
                summary=ch.get("summary", ""),
                plain=ch.get("plain", ""),
            )
            for i, ch in enumerate(data.get("chapters", []))
        ],
    )


def _interp_to_dict(interp: Interpretation | None) -> dict | None:
    if interp is None:
        return None
    return {
        "overview": interp.overview,
        "key_points": interp.key_points,
        "quotes": interp.quotes,
    }


def _interp_from_dict(data: dict | None, book: Book) -> Interpretation | None:
    if not data:
        return None
    return Interpretation(
        book=book,
        overview=data.get("overview", ""),
        key_points=list(data.get("key_points", [])),
        quotes=list(data.get("quotes", [])),
    )


def _ratios_to_dict(ratios: dict) -> dict:
    """最近浓缩/讲解比例：{章节索引: {"summary": 比例|None, "plain": 比例|None}}。"""
    return {str(k): dict(v) for k, v in ratios.items()}


def _nested_to_dict(cache: dict) -> dict:
    """按章节/比例分组的缓存：{章节索引: {比例字符串: 值}}。"""
    return {str(k): dict(v) for k, v in cache.items()}


def save_state(books: dict[str, dict[str, Any]]) -> None:
    """全量保存书籍记录到磁盘。books 即 webapp.main._books。"""
    _ensure_dir()
    for book_id, record in books.items():
        payload = {
            "filename": record["filename"],
            "book": _book_to_dict(record["book"]),
            "interpretation": _interp_to_dict(record.get("interpretation")),
            "titles_extracted": bool(record.get("titles_extracted")),
            "last_ratios": _ratios_to_dict(record.get("last_ratios", {})),
            "summaries": _nested_to_dict(record.get("summaries", {})),
            "plains": _nested_to_dict(record.get("plains", {})),
        }
        state_path = book_state_path(book_id)
        tmp = state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(state_path)
        raw_text_path(book_id).write_text(record["raw_text"], encoding="utf-8")


def load_state() -> dict[str, dict[str, Any]]:
    """从磁盘加载全部书籍记录，返回可直接作为 webapp.main._books 的字典。"""
    books: dict[str, dict[str, Any]] = {}
    _ensure_dir()
    for state_path in (STATE_DIR / "books").glob("*.json"):
        book_id = state_path.stem
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        book = _book_from_dict(payload.get("book", {}))
        record = {
            "book": book,
            "filename": payload.get("filename", ""),
            "raw_text": _read_raw_text(book_id),
            "interpretation": _interp_from_dict(payload.get("interpretation"), book),
            "titles_extracted": bool(payload.get("titles_extracted")),
            "last_ratios": {
                int(k): v for k, v in payload.get("last_ratios", {}).items()
            },
            "summaries": {
                int(k): v for k, v in payload.get("summaries", {}).items()
            },
            "plains": {
                int(k): v for k, v in payload.get("plains", {}).items()
            },
        }
        books[book_id] = record
    return books


def _read_raw_text(book_id: str) -> str:
    try:
        return raw_text_path(book_id).read_text(encoding="utf-8")
    except OSError:
        return ""

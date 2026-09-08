"""书籍解读器本地 Web 应用。"""

from __future__ import annotations

import base64
import hmac
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from book_interpreter.exporter import export
from book_interpreter.interpreter import (
    count_chars,
    explain_chapter_by_ratio,
    extract_chapter_titles,
    generate_overview,
    summarize_chapter_with_sources,
    summary_target_words,
)
from book_interpreter.llm import LLMClient, LLMError
from book_interpreter.loaders import SUPPORTED_EXTENSIONS, UnsupportedFormatError, extract_text
from book_interpreter.parser import parse_book
from book_interpreter.qa import answer_question
from webapp.ratelimit import limiter
from webapp.persistence import load_state, save_state
from webapp.tts import TTSUnavailable, synthesize_batch, tts_configured

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="书籍解读器")

# 内存存储：book_id -> 记录（上传/浓缩/讲解结果同时持久化到磁盘）
_books: dict[str, dict[str, Any]] = load_state()


def _get_access_token() -> str:
    """公网部署的访问口令，未配置则不启用鉴权。"""
    return os.environ.get("ACCESS_TOKEN", "")


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path != "/api/auth/verify":
        token = _get_access_token()
        if token and not hmac.compare_digest(request.headers.get("x-access-token", ""), token):
            return JSONResponse(status_code=401, content={"detail": "请输入访问口令"})
    if path.startswith("/api/"):
        ip = request.client.host if request.client else "unknown"
        if not limiter.allow(ip, path):
            return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
    return await call_next(request)


def get_llm() -> LLMClient:
    return LLMClient()


class ChapterOut(BaseModel):
    title: str
    summary: str = ""


class BookOut(BaseModel):
    id: str
    title: str
    filename: str
    chapters: list[ChapterOut]


class BookListChapterOut(BaseModel):
    title: str
    has_summary: bool = False
    summary_ratio: float | None = None
    has_plain: bool = False
    plain_ratio: float | None = None


class BookListItemOut(BaseModel):
    id: str
    title: str
    filename: str
    chapters: list[BookListChapterOut]


class AskIn(BaseModel):
    question: str


class AskOut(BaseModel):
    answer: str


class InterpretOut(BaseModel):
    overview: str
    key_points: list[str]
    quotes: list[str]
    chapters: list[ChapterOut]


class ChapterSummarizeOut(BaseModel):
    title: str
    summary: str
    sentences: list[dict] = []
    word_count: int = 0
    target_words: int = 0


class PlainOut(BaseModel):
    title: str
    text: str


class RawOut(BaseModel):
    id: str
    title: str
    filename: str
    text: str


class TtsBatchIn(BaseModel):
    texts: list[str]


class TtsBatchOut(BaseModel):
    audios: list[str]


def _get_record(book_id: str) -> dict[str, Any]:
    record = _books.get(book_id)
    if record is None:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return record


def _cache_key(ratio: float) -> str:
    return str(round(ratio, 6))


def _record_caches(record: dict[str, Any]) -> dict[str, Any]:
    """补齐记录中的缓存字段（兼容旧内存态记录）。"""
    record.setdefault("last_ratios", {})
    record.setdefault("summaries", {})
    record.setdefault("plains", {})
    return record


class AuthIn(BaseModel):
    token: str


@app.post("/api/auth/verify")
def verify_auth(payload: AuthIn) -> dict:
    """校验访问口令，前端验证通过后保存 token 用于后续请求。"""
    token = _get_access_token()
    if not token or hmac.compare_digest(payload.token, token):
        return {"ok": True}
    raise HTTPException(status_code=401, detail="访问口令错误")


@app.get("/api/tts/status")
def tts_status() -> dict:
    """豆包语音是否已配置，前端据此决定优先使用在线自然女声。"""
    return {"available": tts_configured()}


@app.post("/api/tts/batch", response_model=TtsBatchOut)
def tts_batch(payload: TtsBatchIn) -> TtsBatchOut:
    """批量合成朗读音频（每段一个 mp3，base64 返回）。"""
    texts = [(t or "").strip() for t in payload.texts if (t or "").strip()]
    if not texts:
        raise HTTPException(status_code=400, detail="合成文本不能为空")
    if len(texts) > 8:
        raise HTTPException(status_code=400, detail="单次最多合成 8 段文本")
    try:
        audios = synthesize_batch(texts)
    except TTSUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return TtsBatchOut(
        audios=[base64.b64encode(a).decode("ascii") for a in audios]
    )


@app.get("/api/books", response_model=list[BookListItemOut])
def list_books() -> list[BookListItemOut]:
    """返回已上传书籍列表，含各章是否已有浓缩/讲解缓存及最近比例。"""
    items = []
    for book_id, record in _books.items():
        record = _record_caches(record)
        book = record["book"]
        chapters = []
        for i, chapter in enumerate(book.chapters):
            last = record["last_ratios"].get(i, {})
            chapters.append(
                BookListChapterOut(
                    title=chapter.title,
                    has_summary=bool(record["summaries"].get(i)),
                    summary_ratio=last.get("summary"),
                    has_plain=bool(record["plains"].get(i)),
                    plain_ratio=last.get("plain"),
                )
            )
        items.append(
            BookListItemOut(
                id=book_id,
                title=book.title,
                filename=record["filename"],
                chapters=chapters,
            )
        )
    return items


@app.post("/api/books", response_model=BookOut)
async def upload_book(file: UploadFile = File(...)) -> BookOut:
    raw = await file.read()
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的格式：{ext or '未知'}，支持 TXT / Markdown / PDF / EPUB / MOBI / AZW3",
        )
    try:
        text = extract_text(file.filename, raw)
    except UnsupportedFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    book = parse_book(text)
    if book.title == "未命名书籍":
        book.title = Path(file.filename).stem
    book_id = uuid4().hex[:8]
    _books[book_id] = {
        "book": book,
        "filename": file.filename,
        "raw_text": text,
        "interpretation": None,
        "titles_extracted": False,
        "last_ratios": {},
        "summaries": {},
        "plains": {},
    }
    save_state(_books)
    return BookOut(
        id=book_id,
        title=book.title,
        filename=file.filename,
        chapters=[ChapterOut(title=c.title, summary=c.summary) for c in book.chapters],
    )


@app.get("/api/books/{book_id}/raw", response_model=RawOut)
def raw(book_id: str) -> RawOut:
    record = _get_record(book_id)
    return RawOut(
        id=book_id,
        title=record["book"].title,
        filename=record["filename"],
        text=record["raw_text"],
    )


@app.post("/api/books/{book_id}/interpret", response_model=InterpretOut)
def interpret(book_id: str, llm: LLMClient = Depends(get_llm)) -> InterpretOut:
    """仅生成全书概述、核心观点、金句；章节浓缩按需单独生成。"""
    record = _get_record(book_id)
    if not record.get("titles_extracted"):
        extract_chapter_titles(llm, record["book"])
        record["titles_extracted"] = True
    try:
        interp = generate_overview(llm, record["book"])
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    record["interpretation"] = interp
    save_state(_books)
    return InterpretOut(
        overview=interp.overview,
        key_points=interp.key_points,
        quotes=interp.quotes,
        chapters=[
            ChapterOut(title=c.title, summary=c.summary) for c in interp.book.chapters
        ],
    )


@app.post("/api/books/{book_id}/chapters/{chapter_index}/summarize", response_model=ChapterSummarizeOut)
def summarize_chapter_api(
    book_id: str,
    chapter_index: int,
    ratio: float = Query(0.25, ge=0.05, le=1.0),
    llm: LLMClient = Depends(get_llm),
) -> ChapterSummarizeOut:
    """按比例浓缩指定章节，长度上限为原文字数。"""
    record = _get_record(book_id)
    book = record["book"]
    if chapter_index < 0 or chapter_index >= len(book.chapters):
        raise HTTPException(status_code=404, detail="章节不存在")
    chapter = book.chapters[chapter_index]
    if not chapter.content.strip():
        return ChapterSummarizeOut(title=chapter.title, summary="（本章无内容）")
    record = _record_caches(record)
    cached = record["summaries"].get(chapter_index, {}).get(_cache_key(ratio))
    if cached is not None:
        return ChapterSummarizeOut(**cached)
    if not record.get("titles_extracted"):
        extract_chapter_titles(llm, book)
        record["titles_extracted"] = True
    try:
        summary, sentences = summarize_chapter_with_sources(llm, chapter.title, chapter.content, ratio)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    chapter.summary = summary
    result = {
        "title": chapter.title,
        "summary": summary,
        "sentences": sentences,
        "word_count": count_chars(summary),
        "target_words": summary_target_words(chapter.content, ratio),
    }
    record["summaries"].setdefault(chapter_index, {})[_cache_key(ratio)] = result
    record["last_ratios"].setdefault(chapter_index, {})["summary"] = ratio
    save_state(_books)
    return ChapterSummarizeOut(**result)


@app.post("/api/books/{book_id}/chapters/{chapter_index}/plain", response_model=PlainOut)
def explain_chapter_api(
    book_id: str,
    chapter_index: int,
    ratio: float = Query(0.25, ge=0.05, le=1.0),
    llm: LLMClient = Depends(get_llm),
) -> PlainOut:
    """按浓缩比例先浓缩章节，再用初中生词汇对浓缩结果做通俗易懂的讲解。"""
    record = _get_record(book_id)
    book = record["book"]
    if chapter_index < 0 or chapter_index >= len(book.chapters):
        raise HTTPException(status_code=404, detail="章节不存在")
    chapter = book.chapters[chapter_index]
    if not chapter.content.strip():
        return PlainOut(title=chapter.title, text="（本章无内容）")
    record = _record_caches(record)
    cached = record["plains"].get(chapter_index, {}).get(_cache_key(ratio))
    if cached is not None:
        return PlainOut(title=chapter.title, text=cached)
    if not record.get("titles_extracted"):
        extract_chapter_titles(llm, book)
        record["titles_extracted"] = True
    try:
        text = explain_chapter_by_ratio(llm, chapter.title, chapter.content, ratio)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    chapter.plain = text
    record["plains"].setdefault(chapter_index, {})[_cache_key(ratio)] = text
    record["last_ratios"].setdefault(chapter_index, {})["plain"] = ratio
    save_state(_books)
    return PlainOut(title=chapter.title, text=text)


@app.post("/api/books/{book_id}/ask", response_model=AskOut)
def ask(book_id: str, payload: AskIn, llm: LLMClient = Depends(get_llm)) -> AskOut:
    record = _get_record(book_id)
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    try:
        answer = answer_question(llm, record["book"], payload.question)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return AskOut(answer=answer)


@app.get("/api/books/{book_id}/report")
def report(book_id: str, format: str = "md") -> Response:
    record = _get_record(book_id)
    interp = record["interpretation"]
    if interp is None:
        raise HTTPException(status_code=400, detail="请先执行解读")
    fmt = format.lower()
    if fmt not in ("md", "html"):
        raise HTTPException(status_code=400, detail="不支持的导出格式")
    content = export(interp, fmt)
    ext = "html" if fmt == "html" else "md"
    filename = f"{record['book'].title}-解读报告.{ext}"
    media_type = "text/html; charset=utf-8" if fmt == "html" else "text/markdown; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

"""书籍解读器本地 Web 应用。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from book_interpreter.exporter import export
from book_interpreter.interpreter import interpret_book
from book_interpreter.llm import LLMClient, LLMError
from book_interpreter.parser import parse_book
from book_interpreter.qa import answer_question

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="书籍解读器")

# 内存存储：book_id -> 记录
_books: dict[str, dict[str, Any]] = {}


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


class AskIn(BaseModel):
    question: str


class AskOut(BaseModel):
    answer: str


class InterpretOut(BaseModel):
    overview: str
    key_points: list[str]
    quotes: list[str]
    chapters: list[ChapterOut]


def _get_record(book_id: str) -> dict[str, Any]:
    record = _books.get(book_id)
    if record is None:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return record


@app.post("/api/books", response_model=BookOut)
async def upload_book(file: UploadFile = File(...)) -> BookOut:
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="仅支持 UTF-8 编码的文本文件")
    book = parse_book(text)
    if book.title == "未命名书籍":
        book.title = Path(file.filename).stem
    book_id = uuid4().hex[:8]
    _books[book_id] = {"book": book, "filename": file.filename, "interpretation": None}
    return BookOut(
        id=book_id,
        title=book.title,
        filename=file.filename,
        chapters=[ChapterOut(title=c.title, summary=c.summary) for c in book.chapters],
    )


@app.post("/api/books/{book_id}/interpret", response_model=InterpretOut)
def interpret(book_id: str, llm: LLMClient = Depends(get_llm)) -> InterpretOut:
    record = _get_record(book_id)
    try:
        interp = interpret_book(llm, record["book"])
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    record["interpretation"] = interp
    return InterpretOut(
        overview=interp.overview,
        key_points=interp.key_points,
        quotes=interp.quotes,
        chapters=[
            ChapterOut(title=c.title, summary=c.summary) for c in interp.book.chapters
        ],
    )


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

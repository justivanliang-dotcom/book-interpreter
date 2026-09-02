"""解析 TXT/Markdown 书籍内容，识别章节结构。"""

from __future__ import annotations

import os
import re

from .models import Book, Chapter

# 常见章节标题模式（中文/英文）
_CHAPTER_PATTERNS = [
    re.compile(r"^\s*第\s*[0-9一二三四五六七八九十百千万零]+\s*[章节回部卷篇]\s*[^\n]*$"),
    re.compile(r"^\s*Chapter\s+\d+[^\n]*$", re.IGNORECASE),
    re.compile(r"^\s*Part\s+[IVX\d]+[^\n]*$", re.IGNORECASE),
]

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _is_markdown(text: str) -> bool:
    """判断文本是否为 Markdown 格式（存在标题标记）。"""
    for line in text.splitlines():
        if _MARKDOWN_HEADING.match(line):
            return True
    return False


def _parse_markdown(text: str) -> list[Chapter]:
    """按 Markdown 标题切分章节。"""
    chapters: list[Chapter] = []
    current_title = "前言"
    current_lines: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal current_title, current_lines, order
        content = "\n".join(current_lines).strip()
        if content or chapters:
            chapters.append(Chapter(title=current_title, content=content, order=order))
            order += 1
        current_lines = []

    for line in text.splitlines():
        m = _MARKDOWN_HEADING.match(line)
        if m:
            flush()
            current_title = m.group(2).strip()
        else:
            current_lines.append(line)
    flush()
    return chapters


def _parse_plain_text(text: str) -> list[Chapter]:
    """按常见章节标题模式切分纯文本。"""
    chapters: list[Chapter] = []
    current_title = "前言"
    current_lines: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal current_title, current_lines, order
        content = "\n".join(current_lines).strip()
        if content or chapters:
            chapters.append(Chapter(title=current_title, content=content, order=order))
            order += 1
        current_lines = []

    for line in text.splitlines():
        if any(p.match(line) for p in _CHAPTER_PATTERNS):
            flush()
            current_title = line.strip()
        else:
            current_lines.append(line)
    flush()
    return chapters


def parse_book(text: str, title: str = "") -> Book:
    """将书籍文本解析为 Book 对象。

    Args:
        text: 书籍全文（TXT 或 Markdown）。
        title: 书籍标题，缺省时从文本首行推断。

    Returns:
        解析后的 Book 对象。
    """
    text = text.strip()
    if not text:
        return Book(title=title or "未命名书籍")

    if not title:
        first_line = text.splitlines()[0].strip()
        if first_line.startswith("# "):
            title = first_line[2:].strip()

    chapters = _parse_markdown(text) if _is_markdown(text) else _parse_plain_text(text)
    return Book(title=title or "未命名书籍", chapters=chapters)


def read_book_file(path: str) -> Book:
    """从文件读取并解析书籍，标题优先取自内容，缺省时用文件名。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    book = parse_book(text)
    if book.title == "未命名书籍":
        book.title = os.path.splitext(os.path.basename(path))[0]
    return book

"""解析 TXT/Markdown 书籍内容，识别章节结构。

支持两种章节标记：
- Markdown 标题（# 开头）
- 章节标记（第X章、自序、结语等），可出现在行首或段落中间（内嵌）
"""

from __future__ import annotations

import os
import re

from .models import Book, Chapter

# 章节/前言/结语标记（可出现在行首或段落中间）
# 第X章 后必须跟空格，以区分"第1章 标题"与"第1章提到的"这类引用
_INLINE_CHAPTER = re.compile(
    r"第\s*[0-9一二三四五六七八九十百千万零]+\s*(?:部分|章节|回|部|卷|篇|章|节)\s+"
)
_INLINE_FRONT = re.compile(r"(?:自序|序言|前言|引言|绪论|导言|推荐序|译者序)\s*[：:]")
_INLINE_BACK = re.compile(r"(?:结语|结束语|后记|附录|跋)\s*[：:]")
_INLINE_THANKS = re.compile(r"(?:^|[。！？\n\r])致谢")
_INLINE_EN = re.compile(r"(?:Chapter|Part)\s+[IVX\d]+\s+", re.IGNORECASE)

# 行首章节标记：无"第"字的章节（如"一章 xxx"、"一部分 xxx"）或整行单独出现的章节名
_LINE_CHAPTER_NO_PREFIX = re.compile(
    r"^[ \t]*[0-9一二三四五六七八九十百千万零]+\s*(?:部分|章节|回|部|卷|篇|章|节)\s+",
    re.MULTILINE,
)
_LINE_FRONT_SOLO = re.compile(
    r"^[ \t]*(?:序|自序|序言|前言|推荐序|译者序|关于本书的[重要]*说明)[ \t]*(?:[0-9IVXLCivxlc]+)?$",
    re.MULTILINE,
)
# "序 作者名"、"前言 译者" 这类"章节名+内容"格式
_LINE_ORDER = re.compile(r"^[ \t]*(?:序|序言|前言|自序)[ \t]+", re.MULTILINE)
_LINE_BACK_SOLO = re.compile(
    r"^[ \t]*(?:结语|结束语|后记|跋|附录|注释|致谢|参考文献)[ \t]*$",
    re.MULTILINE,
)

_LINE_MARKERS = (_LINE_CHAPTER_NO_PREFIX, _LINE_FRONT_SOLO, _LINE_BACK_SOLO, _LINE_ORDER)

_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.*)$")

# 内嵌标题的最大长度（标题后直接跟正文，无法精确切分，取近似值）
_TITLE_MAX = 18
_SENT_END = "。！？"


def _is_markdown(text: str) -> bool:
    """判断文本是否为 Markdown 格式（存在标题标记）。

    要求井号后跟空白且至少 2 个标题行，避免将
    "#18,..." 这类以井号开头的引用/注释误判为 Markdown。
    """
    count = 0
    for line in text.splitlines():
        if _MARKDOWN_HEADING.match(line):
            count += 1
            if count >= 2:
                return True
    return False


def starts_with_marker(line: str) -> bool:
    """判断行首是否为章节标记（第X章、自序、结语等）。"""
    for pattern in (
        _INLINE_CHAPTER,
        _INLINE_FRONT,
        _INLINE_BACK,
        _INLINE_THANKS,
        _INLINE_EN,
        *_LINE_MARKERS,
    ):
        if pattern.match(line):
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
            current_title = m.group(1).strip() or "前言"
        else:
            current_lines.append(line)
    flush()
    return chapters


def _extract_title(after: str) -> str:
    """从标记后的文本中提取章节标题（近似）。"""
    line = after.split("\n", 1)[0].strip()
    for i, ch in enumerate(line):
        if ch in _SENT_END:
            line = line[:i]
            break
    if len(line) > _TITLE_MAX:
        line = line[:_TITLE_MAX]
    return line.strip()


def _find_markers(text: str) -> list[tuple[int, int, str]]:
    """收集所有章节标记，按位置排序并去重（不同模式可能匹配同一位置或重叠）。"""
    markers: list[tuple[int, int, str]] = []
    for pattern in (
        _INLINE_CHAPTER,
        _INLINE_FRONT,
        _INLINE_BACK,
        _INLINE_THANKS,
        _INLINE_EN,
        *_LINE_MARKERS,
    ):
        for m in pattern.finditer(text):
            markers.append((m.start(), m.end(), m.group(0)))
    markers.sort(key=lambda x: (x[0], x[1]))
    unique: list[tuple[int, int, str]] = []
    for m in markers:
        if unique and m[0] < unique[-1][1]:
            # 与上一个标记区间重叠（如"致谢"被内嵌与行首模式同时匹配），保留较长的
            if m[1] > unique[-1][1]:
                unique[-1] = m
        else:
            unique.append(m)
    return unique


def _is_toc_line(text: str) -> bool:
    """目录行特征：由无句号的短行组成（章节标题+页码）。

    允许问号（章节标题可含"？"），排除句号/感叹号/分号。
    """
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) > 60 or any(c in line for c in "。！；"):
            return False
    return True


_PAGE_NUM = re.compile(r"[0-9IVXLCivxlc]+$")


def _strip_toc(text: str) -> str:
    """检测并移除文本开头的目录页。

    优先定位"目 录"/"CONTENTS"标题：其后连续的"目录行"
    （短行、无句号）视为目录块，块内须出现 3 个以上章节标记。
    定位失败时回退到开头启发式：连续多个章节标记之间没有正文
    （只有短行/空行）则判定为目录。
    """
    head = text[: max(1, len(text) // 4)]
    toc_start = None
    for pattern in (
        re.compile(r"^目\s*录\s*$", re.MULTILINE),
        re.compile(r"^CONTENTS\s*$", re.MULTILINE),
    ):
        m = pattern.search(head)
        if m:
            toc_start = m.end()
            break
    if toc_start is not None:
        toc_end = _toc_block_end(text, toc_start)
        if toc_end is not None:
            return text[toc_end:].lstrip("\r\n ")

    # 无"目 录"标题时的回退启发式：从开头连续出现 3 个以上
    # "章节标记 + 短行间隔"即判定为目录页
    markers = [(s, e) for s, e, _ in _find_markers(text)]
    if len(markers) >= 3:
        count = 0
        prev_end = 0
        toc_end = 0
        for start, end in markers:
            if not _is_toc_line(text[prev_end:start]):
                break
            count += 1
            prev_end = end
            toc_end = end
        if count >= 3:
            return text[toc_end:].lstrip("\r\n ")
    return text


def _toc_block_end(text: str, start: int) -> int | None:
    """定位"目 录"标题后的目录块结束位置。

    目录块由连续目录行组成；块内章节标记少于 3 个视为误判，
    返回 None（不执行移除）。
    """
    pos = start
    block_end = start
    marker_count = 0
    while pos < len(text):
        m = re.compile(r"[^\n]*").match(text, pos)
        line = m.group(0)
        next_pos = m.end() + (1 if text[m.end() : m.end() + 1] == "\n" else 0)
        if not line.strip():
            pos = next_pos
            continue
        # 目录行：短行、无句号。正文段落（含标点/长行）终止目录块
        if not _is_toc_line(line):
            break
        marker_count += len(_find_markers(line + "\n"))
        # 目录块末尾以带页码的行收束（无页码的行多为子标题/页码列）
        if _PAGE_NUM.search(line):
            block_end = next_pos
        pos = next_pos
    return block_end if marker_count >= 3 else None


def _parse_plain_text(text: str) -> list[Chapter]:
    """按章节标记切分纯文本，标记可内嵌在段落中间。"""
    text = _strip_toc(text)
    markers = _find_markers(text)
    if not markers:
        return [Chapter(title="前言", content=text.strip(), order=0)]

    chapters: list[Chapter] = []
    prefix = text[: markers[0][0]].strip()
    if prefix:
        chapters.append(Chapter(title="前言", content=prefix, order=0))

    for i, (start, end, marker_text) in enumerate(markers):
        next_start = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        after = text[end:next_start]
        title = _extract_title(after)
        clean_marker = marker_text.strip().lstrip("。！？\n\r ")
        full_title = f"{clean_marker} {title}".strip()
        content = text[start:next_start].strip()
        chapters.append(Chapter(title=full_title, content=content, order=len(chapters)))
    return chapters


def _infer_title(text: str) -> str:
    """从文本开头推断书名：取头部前几个短行中的书名行。

    优先取含中文的行（书名通常为中文）；版权页等前置页不影响
    推断（书名通常出现在最前面几行）。
    """
    chinese_candidates: list[str] = []
    for line in text.splitlines()[:8]:
        line = line.strip()
        if not line:
            continue
        if len(line) > 30:
            continue
        if any(c in line for c in "。！？；："):
            continue
        if any(kw in line for kw in ("著", "编", "译", "出版社", "ISBN", "版权所有")):
            continue
        if re.search(r"[\u4e00-\u9fff]", line):
            chinese_candidates.append(line)
    return chinese_candidates[0] if chinese_candidates else ""


def parse_book(text: str, title: str = "") -> Book:
    """将书籍文本解析为 Book 对象。

    Args:
        text: 书籍全文（TXT 或 Markdown）。
        title: 书籍标题，缺省时从文本开头推断。

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
        else:
            title = _infer_title(text)

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

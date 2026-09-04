"""多格式书籍文本提取：TXT / Markdown / PDF / EPUB / MOBI / AZW3。"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".epub", ".mobi", ".azw3"}
_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}


class UnsupportedFormatError(ValueError):
    """格式不支持或解析失败。"""


def _decode_text(raw: bytes) -> str:
    """按 BOM/编码依次尝试解码文本，避免乱码与失败。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16-le")
    if raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16-be")
    for enc in ("utf-8", "gb18030", "big5", "shift_jis"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


class _HtmlToText(HTMLParser):
    """把 HTML 转为带段落换行的纯文本，跳过 script/style 内容。"""

    _BLOCK_TAGS = {
        "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "tr", "blockquote", "section", "article", "figure",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
        elif self._skip_depth == 0 and tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        lines = [ln.strip() for ln in "".join(self._parts).splitlines()]
        out: list[str] = []
        blank = 0
        for ln in lines:
            if ln:
                out.append(ln)
                blank = 0
            else:
                blank += 1
                if blank == 1:
                    out.append("")
        return "\n".join(out).strip()


def html_to_text(html: str) -> str:
    parser = _HtmlToText()
    parser.feed(html)
    parser.close()
    return parser.text()


def _extract_pdf(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    if len(text) < 50:
        raise UnsupportedFormatError("未能从 PDF 提取到文本，可能是扫描版或加密的 PDF")
    return text


def _norm_href(href: str | None) -> str:
    """去掉锚点与 URL 编码，得到 EPUB 内文件路径。"""
    if not href:
        return ""
    return urllib.parse.unquote(href.split("#", 1)[0])


def _html_title(html: str) -> str:
    """从 HTML <title> 标签提取标题，失败返回空串。"""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if title:
            return title
    return ""


def _html_first_heading(html: str) -> str:
    """从 HTML 正文提取第一个标题（h1-h6）文本，失败返回空串。

    部分 EPUB/MOBI 的 HTML 丢失 <title> 或 `<head>` 为空（如 ebooklib
    序列化时丢弃），此时正文首标题是章节名的最后兜底。
    """
    m = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if title:
            return title
    return ""


def _entry_title(item, raw_html: str, fname: str) -> str:
    """按优先级提取章节标题，保证任何情况下都不为空。"""
    candidates = (
        getattr(item, "title", None) or "",
        _html_title(raw_html),
        _html_first_heading(raw_html),
        Path(fname).stem,
        "未命名章节",
    )
    for title in candidates:
        if title and title.strip():
            return title.strip()
    return "未命名章节"


def _flatten_toc(toc) -> list[tuple[str, str | None]]:
    """递归展开 ebooklib 目录，返回 [(标题, 文件路径), ...]。"""

    def entry_of(node) -> tuple[str, str | None]:
        if isinstance(node, str):
            return (node, None)
        title = getattr(node, "title", None) or getattr(node, "text", None) or ""
        fname = getattr(node, "file_name", None) or getattr(node, "href", None)
        return (str(title).strip() or "未命名章节", fname)

    out: list[tuple[str, str | None]] = []

    def walk(nodes) -> None:
        for node in nodes:
            if isinstance(node, (tuple, list)):
                if node:
                    out.append(entry_of(node[0]))
                    walk(node[1:])
            elif node is not None:
                out.append(entry_of(node))

    walk(toc)
    return out


def _extract_epub(raw: bytes) -> str:
    """按 EPUB 目录（NCX/nav）组织章节，输出 Markdown 结构文本。

    优先使用书内目录的标题作为章节标题，正文内容按目录顺序拼入，
    避免正文标题为图片或注释块干扰导致的章节标题丢失。
    """
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(io.BytesIO(raw))
    toc = _flatten_toc(book.toc)
    docs = {
        _norm_href(item.get_name()): item
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
    }
    title = (book.title or "").strip()
    lines = [f"# {title}"] if title else []
    emitted: set[str] = set()

    def content_of(item) -> str:
        return html_to_text(item.get_content().decode("utf-8", errors="replace"))

    if toc:
        for entry_title, href in toc:
            fname = _norm_href(href)
            item = docs.get(fname)
            text = ""
            if item is not None:
                text = content_of(item)
                emitted.add(fname)
            lines.append(f"## {entry_title}")
            if text:
                lines.append(text)
    else:
        for fname, item in sorted(docs.items()):
            if fname.lower().endswith(("nav.xhtml", "nav.html", "toc.xhtml")):
                continue
            raw_html = item.get_content().decode("utf-8", errors="replace")
            text = html_to_text(raw_html)
            entry_title = _entry_title(item, raw_html, fname)
            lines.append(f"## {entry_title}")
            if text:
                lines.append(text)

    result = "\n\n".join(lines).strip()
    if len(result) < 20:
        raise UnsupportedFormatError("未能从 EPUB 提取到文本")
    return result


def _extract_mobi(raw: bytes) -> str:
    import mobi

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "input.mobi"
        src.write_bytes(raw)
        tempdir, filepath = mobi.extract(str(src))
        try:
            root = Path(tempdir)
            html_files = sorted(
                [p for p in root.rglob("*.html") if p.is_file()]
            ) + sorted([p for p in root.rglob("*.htm") if p.is_file()])
            if filepath and Path(filepath).suffix.lower() in (".html", ".htm"):
                html_files = [Path(filepath)] + [
                    p for p in html_files if p != Path(filepath)
                ]
            parts = []
            seen: set[str] = set()
            for p in html_files:
                raw_html = p.read_text(encoding="utf-8", errors="replace")
                text = html_to_text(raw_html)
                if not text or text in seen:
                    continue
                seen.add(text)
                parts.append(f"## {_entry_title(None, raw_html, str(p))}")
                parts.append(text)
            text = "\n\n".join(parts).strip()
            if not text:
                raise UnsupportedFormatError("未能从 MOBI/AZW3 提取到文本")
            return text
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)


def extract_text(filename: str, raw: bytes) -> str:
    """按扩展名提取书籍纯文本，失败时抛 UnsupportedFormatError。"""
    ext = Path(filename).suffix.lower()
    if ext in _TEXT_EXTENSIONS:
        return _decode_text(raw)
    try:
        if ext == ".pdf":
            return _extract_pdf(raw)
        if ext == ".epub":
            return _extract_epub(raw)
        if ext in (".mobi", ".azw3"):
            return _extract_mobi(raw)
    except UnsupportedFormatError:
        raise
    except Exception as e:  # 解析库的各类异常统一转为可读错误
        raise UnsupportedFormatError(f"{ext[1:].upper()} 解析失败：{e}") from e
    raise UnsupportedFormatError(
        f"不支持的格式：{ext or '未知'}，支持 TXT / Markdown / PDF / EPUB / MOBI / AZW3"
    )

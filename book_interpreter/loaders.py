"""多格式书籍文本提取：TXT / Markdown / PDF / EPUB / MOBI / AZW3。"""

from __future__ import annotations

import io
import shutil
import tempfile
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


def _extract_epub(raw: bytes) -> str:
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(io.BytesIO(raw))
    parts = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        content = item.get_content().decode("utf-8", errors="replace")
        parts.append(html_to_text(content))
    return "\n\n".join(p for p in parts if p).strip()


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
            for p in html_files:
                parts.append(html_to_text(p.read_text(encoding="utf-8", errors="replace")))
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

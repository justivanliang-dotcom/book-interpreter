"""基于 TF-IDF 的文本检索，用于内容问答的召回阶段。"""

from __future__ import annotations

import math
import re
from collections import Counter

from .models import Book

_LATIN_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """将文本切分为有重叠的片段，保证检索粒度。"""
    if chunk_size <= overlap:
        raise ValueError("chunk_size 必须大于 overlap")
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _tokenize(text: str) -> list[str]:
    """中英文分词：英文按词切分，中文按相邻字符二元组切分。"""
    text = text.lower()
    tokens = [m.group(0) for m in _LATIN_RE.finditer(text)]
    chars = _CJK_RE.findall(text)
    if len(chars) == 1:
        tokens.append(chars[0])
    for i in range(len(chars) - 1):
        tokens.append(chars[i] + chars[i + 1])
    return tokens


class Retriever:
    """TF-IDF 检索器。"""

    def __init__(self, chunks: list[str] | None = None) -> None:
        self.chunks: list[str] = chunks or []
        self._tf: list[Counter] = []
        self._idf: dict[str, float] = {}
        if self.chunks:
            self._build_index()

    def _build_index(self) -> None:
        doc_count = len(self.chunks)
        df: Counter = Counter()
        for chunk in self.chunks:
            tokens = _tokenize(chunk)
            self._tf.append(Counter(tokens))
            df.update(set(tokens))
        self._idf = {
            term: math.log((1 + doc_count) / (1 + freq)) + 1.0
            for term, freq in df.items()
        }

    def _score(self, query_tokens: list[str], tf: Counter) -> float:
        score = 0.0
        for term in query_tokens:
            if term in tf:
                score += tf[term] * self._idf.get(term, 0.0)
        return score

    def retrieve(self, query: str, top_k: int = 3) -> list[tuple[str, float]]:
        """返回与查询最相关的 top_k 个片段及其得分。"""
        if not self.chunks:
            return []
        query_tokens = _tokenize(query)
        scored = [
            (self.chunks[i], self._score(query_tokens, self._tf[i]))
            for i in range(len(self.chunks))
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(chunk, score) for chunk, score in scored[:top_k] if score > 0]


def build_retriever(book: Book, chunk_size: int = 800, overlap: int = 100) -> Retriever:
    """将书籍构建为检索器。"""
    return Retriever(chunk_text(book.full_text, chunk_size, overlap))

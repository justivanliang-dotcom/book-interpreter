"""数据模型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chapter:
    """书籍的一个章节。"""

    title: str
    content: str
    order: int
    summary: str = ""
    plain: str = ""


@dataclass
class Book:
    """解析后的书籍。"""

    title: str
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(f"{c.title}\n{c.content}" for c in self.chapters)


@dataclass
class Interpretation:
    """书籍解读结果。"""

    book: Book
    overview: str = ""
    key_points: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)

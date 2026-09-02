"""书籍解读：章节摘要、全书解读、重点/金句摘录。"""

from __future__ import annotations

from .llm import LLMClient
from .models import Book, Interpretation


def _truncate(text: str, limit: int = 6000) -> str:
    """截断过长的文本，避免超出模型上下文。"""
    return text if len(text) <= limit else text[:limit] + "……（内容过长已截断）"


def summarize_chapter(llm: LLMClient, title: str, content: str) -> str:
    """生成单个章节的摘要。"""
    prompt = (
        f"请为以下书籍章节生成一段简洁的中文摘要（150 字以内），"
        f"概括本章的核心内容和主要观点。\n\n章节标题：{title}\n\n章节内容：\n{_truncate(content)}"
    )
    return llm.complete(prompt, max_tokens=500)


def interpret_book(llm: LLMClient, book: Book) -> Interpretation:
    """对整本书进行解读：章节摘要 + 全书概述 + 核心观点 + 金句摘录。"""
    interp = Interpretation(book=book)

    for chapter in book.chapters:
        if chapter.content.strip():
            chapter.summary = summarize_chapter(llm, chapter.title, chapter.content)

    # 全书概述
    summary_block = "\n".join(
        f"- {c.title}：{c.summary}" for c in book.chapters if c.summary
    )
    overview_prompt = (
        f"请为《{book.title}》写一段全书概述（200 字以内），说明这本书的主旨和整体价值。\n\n"
        f"各章节摘要如下：\n{summary_block}"
    )
    interp.overview = llm.complete(overview_prompt, max_tokens=500)

    # 核心观点
    points_prompt = (
        f"请提炼《{book.title}》的 5 个核心观点，每个观点用一句话概括，用编号列表输出。\n\n"
        f"各章节摘要如下：\n{summary_block}"
    )
    points_text = llm.complete(points_prompt, max_tokens=800)
    interp.key_points = _parse_list(points_text)

    # 金句摘录
    quotes_prompt = (
        f"请从《{book.title}》中摘录 3 句最有代表性的金句，"
        f"每句用引号括起来并注明出处章节，用编号列表输出。\n\n全书内容：\n{_truncate(book.full_text)}"
    )
    quotes_text = llm.complete(quotes_prompt, max_tokens=800)
    interp.quotes = _parse_list(quotes_text)

    return interp


def _parse_list(text: str) -> list[str]:
    """解析 LLM 输出的编号/项目符号列表。"""
    items: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 去掉编号或项目符号前缀
        cleaned = line
        for prefix in ("- ", "* ", "• "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break
        else:
            import re

            m = re.match(r"^\d+[.、)]\s*", cleaned)
            if m:
                cleaned = cleaned[m.end():]
        if cleaned:
            items.append(cleaned)
    return items

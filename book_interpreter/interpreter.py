"""书籍解读：章节摘要、全书解读、重点/金句摘录。"""

from __future__ import annotations

import re

from .llm import LLMClient
from .models import Book, Interpretation
from .parser import starts_with_marker
from .retriever import Retriever


def _truncate(text: str, limit: int = 6000) -> str:
    """截断过长的文本，避免超出模型上下文。"""
    return text if len(text) <= limit else text[:limit] + "……（内容过长已截断）"


def _build_summary_prompt(
    title: str, content: str, target_words: int, with_sources: bool = False
) -> str:
    lower = max(50, int(target_words * 0.8))
    upper = int(target_words * 1.2)
    prompt = (
        f"请将以下书籍章节浓缩为一段中文摘要，目标字数约 {target_words} 字"
        f"（请尽量接近该字数，允许在 {lower}~{upper} 字之间），"
        f"概括本章的核心内容和主要观点。"
    )
    if with_sources:
        prompt += (
            "\n\n输出格式要求：把摘要按句子拆开，每个句子后紧跟该句对应的原文摘录。"
            "原文摘录必须逐字取自原文，必须是原文中连续的一段文字，"
            "完整覆盖该句所依据的原文内容（通常 50~200 字）。"
            "严禁使用省略号（……、...）省略中间内容；若原文较长，"
            "请摘录最相关的一段连续原文，宁可摘录更长也不要截断。用以下标记分隔：\n"
            "【句】摘要句子1\n【源】原文摘录1\n【句】摘要句子2\n【源】原文摘录2\n"
        )
    return prompt + f"\n\n章节标题：{title}\n\n章节内容：\n{_truncate(content, 20000)}"


def summarize_chapter(
    llm: LLMClient,
    title: str,
    content: str,
    ratio: float = 0.25,
    max_words: int | None = None,
) -> str:
    """生成单个章节的浓缩摘要，长度按原文比例计算。

    ratio 为 0~1 的比例值，目标字数 = 原文字数 × ratio，
    上限为原文字数（不设固定上限），下限为 100 字；
    max_words 可额外限制目标字数上限（用于报告等固定长度场景）。
    当目标字数达到原文字数时（如 100%），直接返回原文，不再调用 LLM。
    """
    content_length = len(content)
    target_words = max(100, min(content_length, int(content_length * ratio)))
    if max_words is not None:
        target_words = min(target_words, max_words)
    if target_words >= content_length:
        return content
    prompt = _build_summary_prompt(title, content, target_words)
    return llm.complete(prompt, max_tokens=min(target_words * 2, 16000))


def _parse_summary_with_sources(text: str) -> list[dict]:
    """解析带原文引用的浓缩结果，返回 [{text, source}, ...]。"""
    sentences: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("【句】"):
            if current and current.get("text"):
                sentences.append(current)
            current = {"text": line[len("【句】"):].strip(), "source": ""}
        elif line.startswith("【源】") and current is not None:
            current["source"] = line[len("【源】"):].strip()
    if current and current.get("text"):
        sentences.append(current)
    return [s for s in sentences if s["text"]]


def _split_paragraphs(text: str) -> list[str]:
    """按换行切分段落，并把过短段落合并到前一段，避免碎片化。"""
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    merged: list[str] = []
    for p in paras:
        if merged and len(p) < 20:
            merged[-1] += p
        else:
            merged.append(p)
    return merged


def _retrieve_context(content: str, sentence: str) -> tuple[str, str]:
    """检索与浓缩句最相关的段落及其前后上下文。

    返回 (context, highlight)：context 为包含关联段落的完整上下文，
    highlight 为其中与浓缩句直接关联的段落（用于高亮）。
    """
    paras = _split_paragraphs(content)
    if not paras:
        return "", ""
    results = Retriever(paras).retrieve(sentence, top_k=1)
    if not results:
        return "", ""
    idx = paras.index(results[0][0])
    start = max(0, idx - 1)
    end = min(len(paras), idx + 2)
    context = "\n\n".join(paras[start:end])
    return context, results[0][0]


def summarize_chapter_with_sources(
    llm: LLMClient, title: str, content: str, ratio: float = 0.25
) -> tuple[str, list[dict]]:
    """浓缩章节并让 LLM 为每个句子标注对应的原文摘录。

    返回 (摘要纯文本, [{text, source, context, highlight}, ...])。
    context 为包含原文摘录的完整上下文，highlight 为其中直接关联的部分。
    当目标字数达到原文字数时（如 100%）直接返回原文。
    对含省略号或过短的原文摘录，用检索到的完整段落兜底替换。
    """
    content_length = len(content)
    target_words = max(100, min(content_length, int(content_length * ratio)))
    if target_words >= content_length:
        return content, [{"text": content, "source": content, "context": content, "highlight": content}]
    prompt = _build_summary_prompt(title, content, target_words, with_sources=True)
    raw = llm.complete(prompt, max_tokens=min(target_words * 2, 16000))
    sentences = _parse_summary_with_sources(raw)
    if not sentences:
        return raw, [{"text": raw, "source": "", "context": "", "highlight": ""}]
    for s in sentences:
        src = s.get("source", "")
        context, retrieved = _retrieve_context(content, s["text"])
        if not context:
            context = src
            highlight = src
        elif src and src in context:
            highlight = src
        else:
            highlight = retrieved
        s["context"] = context
        s["highlight"] = highlight
        if not src or "…" in src or "..." in src or len(src) < 20:
            s["source"] = highlight
    summary_text = "".join(s["text"] for s in sentences)
    return summary_text, sentences


def extract_chapter_titles(llm: LLMClient, book: Book) -> None:
    """让 LLM 批量提取各章节准确标题，避免标题混入正文。

    仅处理行首带章节标记的章节（纯文本书的标题与正文直接拼接，
    无法用规则精确切分）；Markdown 书的标题取自标题行，无需处理。
    """
    chapters = book.chapters
    if not chapters:
        return
    target_idx = [
        i
        for i, ch in enumerate(chapters)
        if ch.content.strip()
        and starts_with_marker(ch.content.split("\n", 1)[0].strip())
    ]
    if not target_idx:
        return

    lines = [
        f"{i + 1}. {ch.content.split(chr(10), 1)[0].strip()}" for i, ch in enumerate(chapters)
    ]
    prompt = (
        f"以下是书籍《{book.title}》各章节的开头行。每行是“章节编号+章节标题+正文开头”"
        f"直接拼接而成，没有分隔符。请为每一行提取准确的章节标题（保留“第X章”等编号），"
        f"不要包含正文。只输出标题，每行一个，不要编号。\n\n"
        + "\n".join(lines)
    )
    raw = llm.complete(prompt, max_tokens=800).strip()
    parsed = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(parsed) != len(chapters):
        return
    for i in target_idx:
        title = parsed[i].strip()
        # 仅去除成对包裹标题的外层引号，保留标题内部的引号（如“老板AI”）
        if len(title) >= 2 and title[0] == title[-1] and title[0] in '"\'“”':
            title = title[1:-1].strip()
        if title and len(title) <= 60:
            chapters[i].title = title


def generate_overview(llm: LLMClient, book: Book) -> Interpretation:
    """生成全书概述、核心观点、金句摘录（不生成章节浓缩）。

    章节浓缩按需单独生成，此处仅以各章节开头片段作为概述依据。
    """
    interp = Interpretation(book=book)
    preview_block = "\n".join(
        f"- {c.title}：{_truncate(c.content, 300)}" for c in book.chapters if c.content.strip()
    )

    overview_prompt = (
        f"请为《{book.title}》写一段全书概述（200 字以内），说明这本书的主旨和整体价值。\n\n"
        f"各章节开头预览如下：\n{preview_block}"
    )
    interp.overview = llm.complete(overview_prompt, max_tokens=500)

    points_prompt = (
        f"请提炼《{book.title}》的 5 个核心观点，每个观点用一句话概括，用编号列表输出。\n\n"
        f"各章节开头预览如下：\n{preview_block}"
    )
    points_text = llm.complete(points_prompt, max_tokens=800)
    interp.key_points = _parse_list(points_text)

    quotes_prompt = (
        f"请从《{book.title}》中摘录 3 句最有代表性的金句，"
        f"每句用引号括起来并注明出处章节，用编号列表输出。\n\n全书内容：\n{_truncate(book.full_text)}"
    )
    quotes_text = llm.complete(quotes_prompt, max_tokens=800)
    interp.quotes = _parse_list(quotes_text)

    return interp


def interpret_book(llm: LLMClient, book: Book) -> Interpretation:
    """对整本书进行解读：章节摘要 + 全书概述 + 核心观点 + 金句摘录。"""
    interp = Interpretation(book=book)

    extract_chapter_titles(llm, book)
    for chapter in book.chapters:
        if chapter.content.strip():
            chapter.summary = summarize_chapter(llm, chapter.title, chapter.content, max_words=300)

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

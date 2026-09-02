"""基于检索增强（RAG）的内容问答。"""

from __future__ import annotations

from .llm import LLMClient
from .models import Book
from .retriever import Retriever, build_retriever


def answer_question(
    llm: LLMClient,
    book: Book,
    question: str,
    retriever: Retriever | None = None,
    top_k: int = 3,
) -> str:
    """基于书籍内容回答用户问题。

    流程：检索相关片段 -> 拼接上下文 -> 调用 LLM 生成答案。
    """
    retriever = retriever or build_retriever(book)
    hits = retriever.retrieve(question, top_k=top_k)
    if not hits:
        return "未在书籍内容中找到与问题相关的信息。"

    context = "\n\n---\n\n".join(chunk for chunk, _ in hits)
    prompt = (
        f"请仅根据以下书籍内容回答用户问题。如果内容不足以回答，请如实说明。\n\n"
        f"书籍：《{book.title}》\n\n相关内容：\n{context}\n\n"
        f"用户问题：{question}\n\n请用中文回答。"
    )
    return llm.complete(prompt, max_tokens=1000)

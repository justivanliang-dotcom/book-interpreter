"""命令行入口。

用法示例：
    python -m book_interpreter.cli interpret 书籍.md -o 报告.md
    python -m book_interpreter.cli interpret 书籍.md --format html -o 报告.html
    python -m book_interpreter.cli ask 书籍.md "这本书讲了什么？"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .exporter import export
from .interpreter import interpret_book
from .llm import LLMClient
from .loaders import UnsupportedFormatError, extract_text
from .parser import parse_book
from .qa import answer_question


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book-interpreter", description="书籍解读器 MVP")
    sub = parser.add_subparsers(dest="command", required=True)

    p_interpret = sub.add_parser("interpret", help="解读书籍并导出报告")
    p_interpret.add_argument(
        "book", help="书籍文件路径（TXT/Markdown/PDF/EPUB/MOBI/AZW3）"
    )
    p_interpret.add_argument("-o", "--output", help="输出文件路径")
    p_interpret.add_argument("--format", choices=["md", "html"], default="md", help="导出格式")

    p_ask = sub.add_parser("ask", help="基于书籍内容回答问题")
    p_ask.add_argument(
        "book", help="书籍文件路径（TXT/Markdown/PDF/EPUB/MOBI/AZW3）"
    )
    p_ask.add_argument("question", help="要提问的问题")

    return parser


def _read_book(path: str):
    try:
        text = extract_text(path, open(path, "rb").read())
    except UnsupportedFormatError as e:
        raise SystemExit(f"错误：{e}")
    book = parse_book(text)
    if book.title == "未命名书籍":
        book.title = Path(path).stem
    return book


def _cmd_interpret(args: argparse.Namespace) -> int:
    book = _read_book(args.book)
    llm = LLMClient()
    print(f"正在解读《{book.title}》（{len(book.chapters)} 个章节）...", file=sys.stderr)
    interp = interpret_book(llm, book)
    report = export(interp, args.format)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已导出到: {args.output}")
    else:
        print(report)
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    book = _read_book(args.book)
    llm = LLMClient()
    answer = answer_question(llm, book, args.question)
    print(answer)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "interpret":
        return _cmd_interpret(args)
    if args.command == "ask":
        return _cmd_ask(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

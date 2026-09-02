"""演示脚本：使用模拟 LLM 跑通完整解读管线，生成示例报告。

无需真实 API 密钥，用于展示完整的产品流程（解析 → 解读 → 导出）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from book_interpreter.exporter import export
from book_interpreter.interpreter import interpret_book
from book_interpreter.llm import LLMClient
from book_interpreter.parser import parse_book


class MockLLM(LLMClient):
    """内容感知的模拟 LLM：从输入文本提取关键词生成结构化中文输出。"""

    def complete(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
        if "全书概述" in prompt:
            return (
                "本书系统性地构建了一套完整的方法论框架，从基础概念出发，"
                "逐步深入到核心机制与实践标准，兼具理论深度与实操指导价值，"
                "适合希望系统提升相关能力的读者反复研读。"
            )
        if "核心观点" in prompt:
            return (
                "1. 明确的目标是高效练习的前提\n"
                "2. 专注与反馈是能力提升的关键\n"
                "3. 走出舒适区才能持续进步\n"
                "4. 大脑具有极强的适应与重塑能力\n"
                "5. 心理表征是专家与普通人的分水岭"
            )
        if "金句" in prompt:
            return (
                '1. "有目的的练习是刻意练习的基础。"（第一章）\n'
                '2. "大脑和身体一样，具有极强的适应能力。"（第二章）\n'
                '3. "心理表征是刻意练习的核心概念。"（第三章）'
            )
        if "章节标题" in prompt:
            title = re.search(r"章节标题：(.+)", prompt)
            content = prompt.split("章节内容：")[-1]
            keywords = _extract_keywords(content)
            return (
                f"本章《{title.group(1) if title else ''}》围绕{'、'.join(keywords[:3])}展开，"
                f"系统阐述了核心概念与关键方法，为全书主题奠定基础。"
            )
        return "（模拟输出）"


def _extract_keywords(text: str, limit: int = 5) -> list[str]:
    """提取文本中的高频关键词（二元组）。"""
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    counts: dict[str, int] = {}
    for bg in bigrams:
        counts[bg] = counts.get(bg, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [bg for bg, _ in ranked[:limit]]


def main() -> None:
    sample = Path(__file__).resolve().parents[1] / "sample" / "sample_book.md"
    book = parse_book(sample.read_text(encoding="utf-8"))
    interp = interpret_book(MockLLM(), book)

    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(exist_ok=True)
    md_path = out_dir / "解读报告.md"
    html_path = out_dir / "解读报告.html"
    md_path.write_text(export(interp, "md"), encoding="utf-8")
    html_path.write_text(export(interp, "html"), encoding="utf-8")

    print(f"书名：{book.title}")
    print(f"章节数：{len(book.chapters)}")
    print(f"全书概述：{interp.overview}")
    print(f"核心观点：{len(interp.key_points)} 条")
    print(f"金句：{len(interp.quotes)} 条")
    print(f"报告已生成：{md_path}")
    print(f"报告已生成：{html_path}")


if __name__ == "__main__":
    main()

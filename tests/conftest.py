"""测试共享的模拟 LLM 与辅助构造工具。"""

from __future__ import annotations

import re

import pytest

from book_interpreter.llm import LLMClient


def simple_pdf(text: str) -> bytes:
    """构造一个含单行文本的单页 PDF。"""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = [b"%PDF-1.4\n"]
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(b"".join(out)))
        out.append(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref_pos = len(b"".join(out))
    n = len(objs)
    xref = b"xref\n0 %d\n0000000000 65535 f \n" % (n + 1)
    for off in offsets:
        xref += b"%010d 00000 n \n" % off
    out.append(xref)
    out.append(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n + 1, xref_pos)
    )
    return b"".join(out)


class FakeLLM(LLMClient):
    """不发起网络请求的模拟 LLM，按提示词返回固定文本。"""

    def __init__(self) -> None:
        super().__init__(api_key="test-key")
        self.calls: list[str] = []

    def complete(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
        self.calls.append(prompt)
        if "开头行" in prompt:
            lines = [ln for ln in prompt.splitlines() if re.match(r"^\d+\.\s", ln)]
            out = []
            for ln in lines:
                m = re.search(r"(第\s*[0-9一二三四五六七八九十]+\s*[章节回部卷篇])", ln)
                marker = m.group(1) if m else "章节"
                out.append(f"{marker} 测试标题")
            return "\n".join(out)
        if "金句" in prompt:
            return "- 金句一\n- 金句二\n- 金句三"
        if "核心观点" in prompt:
            return "1. 观点一\n2. 观点二\n3. 观点三\n4. 观点四\n5. 观点五"
        if "全书概述" in prompt:
            return "这是一本关于自我提升的书籍，主旨是帮助读者成长。"
        if "大白话" in prompt:
            return "这一章用大白话讲：先把问题拆小，再一步步解决，就像搭积木一样。"
        if "章节" in prompt:
            return "本章摘要：这是本章的核心内容。"
        if "问题" in prompt:
            return "根据书籍内容，答案是：坚持每天阅读。"
        return "模拟回答"


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()

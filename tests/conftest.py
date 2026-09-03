"""测试共享的模拟 LLM。"""

from __future__ import annotations

import re

import pytest

from book_interpreter.llm import LLMClient


class FakeLLM(LLMClient):
    """不发起网络请求的模拟 LLM，按提示词返回固定文本。"""

    def __init__(self) -> None:
        super().__init__(api_key="test-key")

    def complete(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
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
        if "章节" in prompt:
            return "本章摘要：这是本章的核心内容。"
        if "问题" in prompt:
            return "根据书籍内容，答案是：坚持每天阅读。"
        return "模拟回答"


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()

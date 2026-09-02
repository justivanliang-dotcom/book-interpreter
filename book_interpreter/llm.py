"""LLM 客户端抽象，支持 OpenAI 兼容接口。

通过环境变量配置：
- LLM_API_KEY: API 密钥
- LLM_BASE_URL: API 基础地址（默认 https://api.openai.com/v1）
- LLM_MODEL: 模型名称（默认 gpt-4o-mini）
"""

from __future__ import annotations

import os

import requests


class LLMError(RuntimeError):
    """LLM 调用失败。"""


class LLMClient:
    """OpenAI 兼容的 LLM 客户端。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")

    def complete(self, prompt: str, system: str = "你是一位专业的书籍解读助手。", max_tokens: int = 2000) -> str:
        """发送单轮对话请求，返回模型输出文本。"""
        if not self.api_key:
            raise LLMError(
                "未配置 LLM_API_KEY。请设置环境变量 LLM_API_KEY（以及可选的 LLM_BASE_URL、LLM_MODEL）。"
            )
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.RequestException as e:
            raise LLMError(f"LLM 请求失败: {e}") from e
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"LLM 响应解析失败: {e}") from e

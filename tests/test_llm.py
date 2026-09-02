"""LLM 客户端与 .env 加载测试。"""

from __future__ import annotations

import os
from pathlib import Path

from book_interpreter.llm import _load_dotenv

_KEYS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


def test_load_dotenv_reads_key_values(monkeypatch, tmp_path: Path) -> None:
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_API_KEY=sk-test-123\n"
        "LLM_BASE_URL=\"https://api.example.com\"\n"
        "# 注释行应被忽略\n"
        "LLM_MODEL='deepseek-chat'\n",
        encoding="utf-8",
    )
    _load_dotenv(env_file)
    assert os.environ["LLM_API_KEY"] == "sk-test-123"
    assert os.environ["LLM_BASE_URL"] == "https://api.example.com"
    assert os.environ["LLM_MODEL"] == "deepseek-chat"


def test_load_dotenv_does_not_override_existing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_API_KEY", "existing-key")
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=file-key\n", encoding="utf-8")
    _load_dotenv(env_file)
    assert os.environ["LLM_API_KEY"] == "existing-key"


def test_load_dotenv_skips_empty_values(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=\n", encoding="utf-8")
    _load_dotenv(env_file)
    assert "LLM_API_KEY" not in os.environ


def test_load_dotenv_missing_file_is_noop() -> None:
    _load_dotenv(Path("nonexistent") / ".env")

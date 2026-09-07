"""IP 限流与每日 LLM 调用额度（内存实现，单实例部署足够）。

阈值通过环境变量配置：
- RATE_LIMIT_PER_MINUTE：每 IP 每分钟 API 请求上限（默认 30）
- DAILY_LLM_LIMIT：每 IP 每天 LLM 调用上限（默认 100）
"""

from __future__ import annotations

import os
import time

_LLM_PATHS = ("/summarize", "/plain", "/interpret", "/ask")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


class RateLimiter:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.per_minute = _env_int("RATE_LIMIT_PER_MINUTE", 30)
        self.daily_llm = _env_int("DAILY_LLM_LIMIT", 100)
        self._minute: dict[str, tuple[int, int]] = {}  # ip -> (分钟桶, 次数)
        self._daily: dict[str, tuple[str, int]] = {}  # ip -> (日期, 次数)

    def allow(self, ip: str, path: str) -> bool:
        """检查请求是否放行：每分钟限流 + LLM 端点的每日额度。"""
        now = int(time.time())
        bucket = now // 60
        prev_bucket, count = self._minute.get(ip, (bucket, 0))
        if prev_bucket != bucket:
            count = 0
        count += 1
        self._minute[ip] = (bucket, count)
        if count > self.per_minute:
            return False

        if any(p in path for p in _LLM_PATHS):
            today = time.strftime("%Y-%m-%d")
            prev_day, llm_count = self._daily.get(ip, (today, 0))
            if prev_day != today:
                llm_count = 0
            llm_count += 1
            self._daily[ip] = (today, llm_count)
            if llm_count > self.daily_llm:
                return False
        return True


limiter = RateLimiter()

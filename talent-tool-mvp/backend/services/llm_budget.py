"""LLM Budget - per-user token 配额 - T402."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Optional

logger = logging.getLogger("recruittech.services.llm_budget")


class LLMBudget:
    """每用户 token 配额控制."""

    def __init__(self, per_user_limit: int = 1_000_000, window_seconds: int = 86400):
        self.limit = per_user_limit
        self.window = window_seconds
        self._usage: dict[str, list[tuple[int, float]]] = defaultdict(list)

    def _clean(self, user_id: str, now: float):
        cutoff = now - self.window
        self._usage[user_id] = [
            (tokens, ts) for tokens, ts in self._usage[user_id] if ts > cutoff
        ]

    def check(self, user_id: str, requested: int = 0) -> bool:
        now = time.time()
        self._clean(user_id, now)
        used = sum(tokens for tokens, _ in self._usage[user_id])
        return used + requested <= self.limit

    def consume(self, user_id: str, tokens: int):
        now = time.time()
        self._usage[user_id].append((tokens, now))
        logger.debug(f"[budget] user {user_id} consumed {tokens} tokens")

    def usage(self, user_id: str) -> int:
        now = time.time()
        self._clean(user_id, now)
        return sum(tokens for tokens, _ in self._usage[user_id])

    def stats(self, user_id: str) -> dict:
        used = self.usage(user_id)
        return {
            "user_id": user_id,
            "used": used,
            "limit": self.limit,
            "remaining": self.limit - used,
            "utilization": round(used / self.limit, 4),
        }


llm_budget = LLMBudget()
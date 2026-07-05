"""i18n 服务 — locale resolver + message lookup."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml


class I18n:
    """从 prompts/{locale}/*.yaml 加载消息."""

    _cache: dict[str, dict[str, str]] = {}

    def __init__(self, default_locale: str = "zh"):
        self.default_locale = default_locale
        self.prompts_root = Path(__file__).parent.parent / "prompts"

    def _load(self, locale: str) -> dict[str, str]:
        if locale in self._cache:
            return self._cache[locale]
        messages = {}
        locale_dir = self.prompts_root / locale
        if locale_dir.exists():
            for f in locale_dir.glob("*.yaml"):
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                messages.update(data)
        self._cache[locale] = messages
        return messages

    def resolve_locale(self, accept_language: Optional[str] = None) -> str:
        """从 Accept-Language 头解析 locale."""
        if not accept_language:
            return self.default_locale
        for entry in accept_language.split(","):
            lang = entry.split(";")[0].strip().lower()
            if lang.startswith("zh"):
                return "zh"
            if lang.startswith("en"):
                return "en"
        return self.default_locale

    def t(self, key: str, locale: Optional[str] = None, default: Optional[str] = None) -> str:
        loc = locale or self.default_locale
        msgs = self._load(loc)
        if key in msgs:
            return msgs[key]
        # fallback 到 default locale
        if loc != self.default_locale:
            return self.t(key, locale=self.default_locale, default=default)
        return default or key


i18n = I18n(default_locale=os.getenv("DEFAULT_LOCALE", "zh"))
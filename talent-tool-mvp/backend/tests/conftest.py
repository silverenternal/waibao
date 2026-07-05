"""全局 pytest 配置 + 共享 fixtures."""
import os
import sys

import pytest


@pytest.fixture
def mock_llm():
    from agents.runtime import LLMClient
    return LLMClient(openai_client=None, model="mock")


@pytest.fixture
def mock_memory():
    from agents.memory import InMemoryStore
    return InMemoryStore()


@pytest.fixture
def mock_supabase():
    class _Mock:
        def table(self, _): return self
        def select(self, *_): return self
        def insert(self, *_): return self
        def upsert(self, *_): return self
        def update(self, *_): return self
        def delete(self): return self
        def eq(self, *_): return self
        def or_(self, *_): return self
        def limit(self, *_): return self
        def maybe_single(self): return self
        def single(self): return self
        def execute(self):
            class R: data = []; count = 0
            return R()
    return _Mock()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("SUPABASE_URL", "http://localhost")
    monkeypatch.setenv("SUPABASE_KEY", "mock")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "mock")
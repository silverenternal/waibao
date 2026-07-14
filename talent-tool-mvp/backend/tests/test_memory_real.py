"""T5021 — Mem0 real LLM extractor + validation tests."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.memory.extractor import EntityExtractor  # noqa: E402
from services.memory.models import MemoryType  # noqa: E402
from services.memory.validation import MemoryValidator, detect_pii  # noqa: E402


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------

class FakeLLM:
    def __init__(self, response: str):
        self._response = response
        self.calls = 0

    async def async_chat(self, messages):
        self.calls += 1
        return self._response

    def chat(self, messages):
        self.calls += 1
        return self._response


class FailingLLM:
    async def async_chat(self, messages):
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def test_heuristic_extract_without_llm():
    ex = EntityExtractor()
    items = ex.extract([
        {"role": "user", "content": "I prefer remote work. I work at Acme."},
    ])
    assert items
    assert all("content" in it and "type" in it and "confidence" in it for it in items)


def test_real_llm_extracts_structured_items():
    llm = FakeLLM(json.dumps({"items": [
        {"content": "prefers remote work", "type": "preference", "confidence": 0.9},
        {"content": "works at Acme as Staff Engineer", "type": "fact", "confidence": 0.85,
         "entities": {"org": ["Acme"]}},
    ]}))
    ex = EntityExtractor(llm=llm)
    items = asyncio.run(ex.extract_async([
        {"role": "user", "content": "I want remote. I'm at Acme."}
    ]))
    assert llm.calls == 1
    assert len(items) == 2
    assert items[0]["type"] is MemoryType.PREFERENCE
    assert items[0]["confidence"] == pytest.approx(0.9)
    assert items[1]["entities"] == {"org": ["Acme"]}


def test_llm_extracts_strips_markdown_fence():
    llm = FakeLLM('```json\n{"items":[{"content":"x","type":"fact","confidence":0.7}]}\n```')
    ex = EntityExtractor(llm=llm)
    items = asyncio.run(ex.extract_async([{"role": "user", "content": "x"}]))
    assert len(items) == 1
    assert items[0]["content"] == "x"


def test_llm_failure_falls_back_to_heuristic():
    ex = EntityExtractor(llm=FailingLLM())
    items = asyncio.run(ex.extract_async([
        {"role": "user", "content": "I prefer remote work."}
    ]))
    assert items  # heuristic fallback produced candidates


def test_unknown_type_defaults_to_fact():
    llm = FakeLLM(json.dumps({"items": [{"content": "x", "type": "garbage", "confidence": 0.5}]}))
    ex = EntityExtractor(llm=llm)
    items = asyncio.run(ex.extract_async([{"role": "user", "content": "x"}]))
    assert items[0]["type"] is MemoryType.FACT


def test_confidence_clamped_to_unit_interval():
    llm = FakeLLM(json.dumps({"items": [{"content": "x", "type": "fact", "confidence": 5.0}]}))
    ex = EntityExtractor(llm=llm)
    items = asyncio.run(ex.extract_async([{"role": "user", "content": "x"}]))
    assert items[0]["confidence"] == 1.0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_detect_pii_flags_email_and_phone():
    flags = detect_pii("reach me at a@b.com or 13800138000")
    assert "email" in flags


def test_rule_validator_rejects_questions_and_pii():
    v = MemoryValidator()
    r = asyncio.run(v.validate_async("Is the candidate good?", declared_confidence=0.9))
    assert not r.valid
    assert "question" in r.reason

    r2 = asyncio.run(v.validate_async("contact a@b.com please", declared_confidence=0.9))
    assert not r2.valid
    assert r2.pii_flags


def test_llm_validator_fuses_confidence_and_type():
    llm = FakeLLM(json.dumps({
        "is_atomic": True, "is_factual": True, "stores_pii": False,
        "correct_type": "preference", "confidence": 0.9, "reason": "ok",
    }))
    v = MemoryValidator(llm=llm, min_confidence=0.5)
    r = asyncio.run(v.validate_async(
        "prefers remote work", declared_type=MemoryType.FACT, declared_confidence=0.5,
    ))
    assert r.valid
    assert r.type is MemoryType.PREFERENCE
    # fused = 0.4*0.5 + 0.6*0.9 = 0.74
    assert r.confidence == pytest.approx(0.74)


def test_llm_validator_rejects_when_pii_detected_by_llm():
    llm = FakeLLM(json.dumps({
        "is_atomic": True, "is_factual": True, "stores_pii": True,
        "correct_type": "fact", "confidence": 0.95, "reason": "has ssn",
    }))
    v = MemoryValidator(llm=llm)
    r = asyncio.run(v.validate_async("ssn 123456789", declared_confidence=0.9))
    assert not r.valid


def test_validator_handles_malformed_llm_output():
    llm = FakeLLM("not json at all")
    v = MemoryValidator(llm=llm)
    r = asyncio.run(v.validate_async("works at Acme", declared_confidence=0.8))
    # rule fallback used
    assert r.reason

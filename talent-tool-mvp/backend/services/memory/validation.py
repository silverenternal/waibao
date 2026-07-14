"""Memory validation — T5021 LLM validation + confidence scoring.

Before a memory candidate is persisted we validate it:

1. **Structural check** — content non-empty, type known, confidence in
   ``[0, 1]``.
2. **LLM validation** — an LLM judges whether the candidate is atomic,
   factual (not a guess), free of PII that should not be stored, and
   correctly typed. It returns a calibrated confidence and, optionally,
   a corrected ``type``.
3. **Confidence fusion** — the final confidence blends the extractor's
   self-reported confidence with the validator's verdict.

The LLM is optional; when absent we fall back to a deterministic
rule-based validator so the pipeline still works offline.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from .models import MemoryType

logger = logging.getLogger("waibao.memory.validation")


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    valid: bool
    confidence: float
    type: MemoryType
    reason: str = ""
    pii_flags: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "confidence": self.confidence,
            "type": self.type.value,
            "reason": self.reason,
            "pii_flags": self.pii_flags or [],
        }


# ---------------------------------------------------------------------------
# PII patterns (cheap pre-filter before the LLM)
# ---------------------------------------------------------------------------

_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}\b"),
    "id_card_cn": re.compile(r"\b\d{15}(?:\d{2}[\dXx])?\b"),
    "passport": re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
    "bank_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
}


def detect_pii(text: str) -> list[str]:
    flags: list[str] = []
    for name, pat in _PII_PATTERNS.items():
        if pat.search(text or ""):
            flags.append(name)
    return flags


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

_VALIDATOR_SYSTEM_PROMPT = (
    "You validate a single memory candidate extracted from a recruitment "
    "conversation. Decide:\n"
    "  1. is_atomic  : one self-contained fact/preference/event/task (not compound)\n"
    "  2. is_factual : a real assertion about the user, not speculation or a question\n"
    "  3. stores_pii : would storing the literal text retain sensitive PII?\n"
    "  4. correct_type : the best type in fact|preference|event|task|summary\n"
    "  5. confidence : calibrated 0..1 that this memory is worth persisting\n\n"
    "Output STRICT JSON:\n"
    '{"is_atomic": bool, "is_factual": bool, "stores_pii": bool, '
    '"correct_type": "...", "confidence": 0.0..1.0, "reason": "..."}'
)


class MemoryValidator:
    """Validate + calibrate confidence for memory candidates."""

    def __init__(self, llm: Any | None = None, *, min_confidence: float = 0.5) -> None:
        self.llm = llm
        self.min_confidence = min_confidence

    # ------------------------------------------------------------------
    async def validate_async(
        self,
        content: str,
        *,
        declared_type: MemoryType = MemoryType.FACT,
        declared_confidence: float = 0.5,
    ) -> ValidationResult:
        # 1) cheap structural + PII pre-filter
        pii = detect_pii(content)
        if not content or not content.strip():
            return ValidationResult(False, 0.0, declared_type, reason="empty content", pii_flags=pii)

        if self.llm is None:
            return self._rule_validate(content, declared_type, declared_confidence, pii)

        # 2) LLM validation
        try:
            if hasattr(self.llm, "async_chat"):
                raw = await self.llm.async_chat([
                    {"role": "system", "content": _VALIDATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Candidate: {content!r}\nDeclared type: {declared_type.value}"},
                ])
            elif hasattr(self.llm, "chat"):
                raw = self.llm.chat([
                    {"role": "system", "content": _VALIDATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Candidate: {content!r}\nDeclared type: {declared_type.value}"},
                ])
            else:
                return self._rule_validate(content, declared_type, declared_confidence, pii)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM validate failed, rule fallback: %s", exc)
            return self._rule_validate(content, declared_type, declared_confidence, pii)

        try:
            data = json.loads(_extract_json(raw))
        except Exception:  # noqa: BLE001
            return self._rule_validate(content, declared_type, declared_confidence, pii)

        try:
            corrected = MemoryType(data.get("correct_type", declared_type.value))
        except ValueError:
            corrected = declared_type
        llm_conf = float(data.get("confidence", declared_confidence))
        llm_conf = max(0.0, min(1.0, llm_conf))

        # fuse extractor + validator confidence
        fused = 0.4 * declared_confidence + 0.6 * llm_conf
        is_atomic = bool(data.get("is_atomic", True))
        is_factual = bool(data.get("is_factual", True))
        stores_pii = bool(data.get("stores_pii", False)) or bool(pii)
        valid = is_atomic and is_factual and not stores_pii and fused >= self.min_confidence
        reason = data.get("reason", "")
        if stores_pii:
            reason = (reason + " (pii detected)").strip()
        return ValidationResult(valid, fused, corrected, reason=reason, pii_flags=pii)

    # ------------------------------------------------------------------
    def _rule_validate(
        self,
        content: str,
        declared_type: MemoryType,
        declared_confidence: float,
        pii: list[str],
    ) -> ValidationResult:
        words = content.split()
        is_atomic = 3 <= len(words) <= 40
        is_factual = not content.strip().endswith("?")
        valid = is_atomic and is_factual and not pii and declared_confidence >= self.min_confidence
        reasons: list[str] = []
        if not is_atomic:
            reasons.append("not atomic")
        if not is_factual:
            reasons.append("looks like a question")
        if pii:
            reasons.append("pii detected")
        return ValidationResult(
            valid=valid,
            confidence=declared_confidence,
            type=declared_type,
            reason=", ".join(reasons) if reasons else "ok",
            pii_flags=pii,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw

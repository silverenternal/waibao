"""v10.0 T5001 — Agent input governance: PII policy + injection guard.

The :class:`AgentGateway` sits at the trust boundary between untrusted user
input and the agent runtime.  This module provides two deterministic
pre-flight checks the gateway can run before an agent ever sees the payload:

* :class:`PIIPolicy` — detects Chinese / global PII (mobile, ID card, bank
  card, email) and produces a masked copy so the input can either be
  rejected or scrubbed in place.
* :class:`InjectionGuard` — detects classic prompt-injection / jailbreak
  patterns (role overrides, instruction leaks, delimiter smuggling) and
  returns a structured rejection.

Both are pure (regex / string) — no LLM, no network — so they are fast and
unit-testable.  They are intentionally conservative: false positives (a
legitimate 11-digit reference number flagged as a phone) are acceptable;
false negatives (a novel injection phrasing) are not, so the pattern lists
are broad.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from services.platform.errors import ServiceError, ServiceErrorCode


# ===========================================================================
# PII policy
# ===========================================================================
@dataclass(frozen=True)
class PIIMatch:
    """A single PII finding inside the input text."""

    kind: str          # phone | id_card | bank_card | email
    value: str         # the matched substring
    start: int
    end: int
    masked: str        # masked rendition, e.g. 138****1234


# Regexes deliberately anchored on surrounding non-digit boundaries so we do
# not over-match inside long numeric identifiers.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # China mobile: 1 + 10 digits, 11 total.
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    # China resident ID card: 17 digits + check digit/X, 18 total.
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    # Bank card: 16-19 digits (UnionPay / Visa / MC).  Must not match the
    # 11-digit phone (excluded by length) or 18-digit ID (overlaps are fine,
    # we report both if present).
    ("bank_card", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
    # Email — keep simple and conservative.
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
)


def _mask(kind: str, value: str) -> str:
    if kind == "email":
        name, _, domain = value.partition("@")
        if len(name) <= 1:
            return "*" + "@" + domain
        return name[0] + "***@" + domain
    digits = value
    if len(digits) <= 4:
        return "*" * len(digits)
    if kind == "phone":  # 138****1234
        return f"{digits[:3]}****{digits[-4:]}"
    if kind == "id_card":  # 110***********1234 (keep check char)
        return f"{digits[:3]}{'*' * (len(digits) - 7)}{digits[-4:]}"
    # bank_card: **** **** **** 1234
    return f"************{digits[-4:]}"


@dataclass
class PIIPolicy:
    """Detect + (optionally) scrub PII from agent input text.

    ``mode``:
      * ``"detect"``  — report findings, do not alter the input.
      * ``"mask"``    — rewrite the input text with masked values.
      * ``"reject"``  — raise :class:`ServiceError` (AGENT_PII_DETECTED) on
        the first finding.
    """

    mode: str = "detect"
    kinds: tuple[str, ...] = ("phone", "id_card", "bank_card", "email")

    def scan(self, text: str) -> list[PIIMatch]:
        """Return all PII findings in ``text`` (ordered by position)."""
        if not text:
            return []
        findings: list[PIIMatch] = []
        for kind, pat in _PII_PATTERNS:
            if kind not in self.kinds:
                continue
            for m in pat.finditer(text):
                findings.append(
                    PIIMatch(
                        kind=kind,
                        value=m.group(0),
                        start=m.start(),
                        end=m.end(),
                        masked=_mask(kind, m.group(0)),
                    )
                )
        # Deduplicate overlapping matches (id_card vs bank_card) keeping the
        # more specific / longer one at the same start.
        findings.sort(key=lambda f: (f.start, -(f.end - f.start)))
        deduped: list[PIIMatch] = []
        last_end = -1
        for f in findings:
            if f.start < last_end and f.end <= last_end:
                continue  # fully contained in previous match
            deduped.append(f)
            last_end = max(last_end, f.end)
        return deduped

    def apply(self, text: str) -> tuple[str, list[PIIMatch]]:
        """Apply the policy; return ``(possibly_rewritten_text, findings)``.

        In ``reject`` mode this raises instead of returning.
        """
        findings = self.scan(text)
        if self.mode == "reject" and findings:
            raise ServiceError(
                ServiceErrorCode.AGENT_PII_DETECTED,
                f"PII detected in agent input ({len(findings)} finding(s))",
                details={"kinds": sorted({f.kind for f in findings})},
            )
        if self.mode == "mask" and findings:
            out = text
            # apply right-to-left so indices stay valid
            for f in sorted(findings, key=lambda x: x.start, reverse=True):
                out = out[: f.start] + f.masked + out[f.end:]
            return out, findings
        return text, findings

    def scrub_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Recursively mask PII inside a context dict (best-effort)."""
        if self.mode != "mask":
            return context
        return _scrub(self, context)


def _scrub(policy: PIIPolicy, obj: Any) -> Any:
    if isinstance(obj, str):
        return policy.apply(obj)[0]
    if isinstance(obj, dict):
        return {k: _scrub(policy, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(policy, v) for v in obj]
    return obj


# ===========================================================================
# Prompt-injection guard
# ===========================================================================
# Patterns are matched case-insensitively against the raw text.  Each entry
# is (label, compiled_regex).  These cover the most common public jailbreak
# templates; operators can extend via :attr:`InjectionGuard.extra_patterns`.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_prior", re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|messages?)", re.I)),
    ("disregard_system", re.compile(r"disregard\s+(all\s+)?(previous|prior|system)\s+(instructions?|prompts?)", re.I)),
    ("new_instructions", re.compile(r"(you\s+have\s+new\s+instructions|here\s+are\s+your\s+(new\s+)?(real|true)\s+instructions)", re.I)),
    ("role_override", re.compile(r"(?:you\s+are\s+now|act\s+as|pretend(?:\s+to\s+be|\s+you\s+are))\s+(?:a\s+|an\s+)?(dan|developer\s+mode|root(?:\s+admin)?|admin|jailbreak)", re.I)),
    ("dan_mode", re.compile(r"\b(dan|do anything now|developer\s+mode|jailbreak)\b", re.I)),
    ("reveal_system", re.compile(r"(reveal|show|print|repeat|output|disclose|leak)\s+.*?(system|hidden|secret|internal)\s+(prompt|instructions?|rules?)", re.I)),
    ("delimiter_smuggle", re.compile(r"</?(system|assistant|instruction|prompt)>", re.I)),
    ("base64_instruction", re.compile(r"decode\s+(the\s+following|this)\s+(base64|b64|encoded)", re.I)),
    ("unrestrict", re.compile(r"(you\s+have\s+been\s+)?(freed|unrestricted|no\s+longer\s+(bound|limited|restricted))(?:\s+\w+){0,3}\s+(from|by)\s+(your\s+)?(rules?|guidelines?|restrictions?|policies?)", re.I)),
    ("simulate_no_rules", re.compile(r"(simulate|enable)\s+(a\s+|an\s+)?(mode|environment)\s+(with|where|in\s+which)\s+(there\s+(is|are)\s+)?no\s+(rules|restrictions|content policies|policies|limits?)", re.I)),
)


@dataclass
class InjectionMatch:
    label: str
    snippet: str
    start: int
    end: int


@dataclass
class InjectionGuard:
    """Detect prompt-injection / jailbreak attempts in agent input."""

    extra_patterns: tuple[tuple[str, re.Pattern[str]], ...] = field(default_factory=tuple)

    def patterns(self) -> tuple[tuple[str, re.Pattern[str]], ...]:
        return _INJECTION_PATTERNS + self.extra_patterns

    def scan(self, text: str) -> list[InjectionMatch]:
        if not text:
            return []
        out: list[InjectionMatch] = []
        for label, pat in self.patterns():
            for m in pat.finditer(text):
                out.append(
                    InjectionMatch(
                        label=label,
                        snippet=m.group(0),
                        start=m.start(),
                        end=m.end(),
                    )
                )
        out.sort(key=lambda x: x.start)
        return out

    def is_injection(self, text: str) -> bool:
        return bool(self.scan(text))

    def enforce(self, text: str) -> list[InjectionMatch]:
        """Raise :class:`ServiceError` (AGENT_INJECTION_BLOCKED) if injected."""
        matches = self.scan(text)
        if matches:
            raise ServiceError(
                ServiceErrorCode.AGENT_INJECTION_BLOCKED,
                f"Prompt injection blocked ({len(matches)} pattern(s))",
                details={"labels": sorted({m.label for m in matches})},
            )
        return matches


# ===========================================================================
# v11.0 T6110 — Mandatory human-escalation rules
# ===========================================================================
# Per 甲方要求, two conversation topics *must always* be escalated to a human
# and never handled autonomously by the AI:
#
#   1. 自伤风险 (self-harm / suicide)   → critical, immediate HR ping + warm
#      popup with the national psychological-aid hotline.
#   2. 劳动争议 (labour dispute)         → high, create a ticket routed to HR /
#      legal.
#
# The AI never "eliminates" (淘汰) a candidate over these — it only surfaces a
# recommendation and hands off.  Original private conversation is NEVER exposed
# to admins/HR: the escalation record carries only ``risk_level`` + ``reason``
# (+ an opaque evidence count), never the raw message text.

# Self-harm keywords — broad on purpose; false positives are acceptable, false
# negatives are not.  Mixed simplified + spoken Chinese phrasings.
SELF_HARM_KEYWORDS: tuple[str, ...] = (
    "自杀", "自残", "自伤", "轻生", "想死", "不想活", "了结自己",
    "活不下去", "解脱", "割腕", "服毒", "跳楼", "结束生命", "寻死",
    "没有意义", "活着没意思", "suicide", "self-harm", "self harm",
    "kill myself", "end my life", "hurt myself",
)

# Labour-dispute keywords.
LABOUR_DISPUTE_KEYWORDS: tuple[str, ...] = (
    "仲裁", "劳动仲裁", "诉讼", "起诉", "违法", "非法", "欠薪", "拖欠工资",
    "克扣工资", "辞退补偿", "经济补偿", "n+1", "赔偿金", "违法解除",
    "无理解雇", "强制辞退", "劳动法", "劳动监察", "工伤认定", "维权",
)

# Risk levels are ordered low→critical so callers can compare severity.
RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high", "critical")

# Warm self-harm popup copy + the national 24h psychological-aid hotline.
SELF_HARM_HOTLINE: str = "400-161-9995"
SELF_HARM_MESSAGE: str = (
    "我注意到你可能正在经历困难。你不是一个人,建议联系专业心理援助热线: "
    f"{SELF_HARM_HOTLINE}。我会同时帮你转接给 HR。"
)
LABOUR_DISPUTE_MESSAGE: str = (
    "这个问题涉及劳动争议,建议联系 HR 或法务部门,我帮你创建一个工单转给他们处理。"
)


@dataclass(frozen=True)
class EscalationRuleHit:
    """A mandatory human-escalation rule match.

    ``raw_text`` / the triggering message is deliberately **not** stored here:
    escalation records and risk alerts must carry only ``risk_level`` +
    ``reason`` so admins/HR never read the user's private conversation.
    """

    rule: str            # self_harm | labour_dispute
    risk_level: str      # critical | high
    reason: str          # human-readable, no PII / no verbatim quote
    matched_keywords: tuple[str, ...]
    message: str         # warm copy shown to the user in the popup


@dataclass
class EscalationRules:
    """Detect mandatory-escalation topics (self-harm + labour dispute).

    Two layers:

    * **Keyword pre-screen** (deterministic, fast, zero network) — catches the
      explicit high-signal phrasings.  This is the authoritative gate: any hit
      forces escalation regardless of what an LLM later says.
    * **Optional LLM confirmation** — ``llm_confirm`` runs a small classifier
      over borderline inputs so that euphemisms ("我不想再醒过来") are caught
      too.  It can only *add* detections, never suppress a keyword hit.
    """

    self_harm_keywords: tuple[str, ...] = SELF_HARM_KEYWORDS
    labour_dispute_keywords: tuple[str, ...] = LABOUR_DISPUTE_KEYWORDS
    # When True, an LLM is consulted to confirm self-harm on borderline text.
    llm_confirm: bool = True

    # ---- keyword layer --------------------------------------------------
    def _keyword_hits(self, text: str) -> list[EscalationRuleHit]:
        if not text:
            return []
        hits: list[EscalationRuleHit] = []
        lower = text.lower()
        sh = tuple(kw for kw in self.self_harm_keywords if kw.lower() in lower)
        if sh:
            hits.append(EscalationRuleHit(
                rule="self_harm",
                risk_level="critical",
                reason="检测到自伤/自杀风险信号,需立即转人工",
                matched_keywords=sh,
                message=SELF_HARM_MESSAGE,
            ))
        ld = tuple(kw for kw in self.labour_dispute_keywords if kw.lower() in lower)
        if ld:
            hits.append(EscalationRuleHit(
                rule="labour_dispute",
                risk_level="high",
                reason="检测到劳动争议信号,建议转 HR/法务",
                matched_keywords=ld,
                message=LABOUR_DISPUTE_MESSAGE,
            ))
        return hits

    # ---- full scan ------------------------------------------------------
    def scan(self, text: str, *, llm=None) -> list[EscalationRuleHit]:
        """Return all mandatory-escalation hits in ``text``.

        Keyword hits are always authoritative.  When ``llm_confirm`` is True
        and an ``llm`` callable is supplied, a borderline self-harm classifier
        may add an additional ``self_harm`` hit when keywords missed it.
        """
        hits = self._keyword_hits(text)
        if (
            self.llm_confirm
            and llm is not None
            and not any(h.rule == "self_harm" for h in hits)
        ):
            try:
                flagged = _llm_self_harm_check(llm, text)
            except Exception:  # noqa: BLE001 — LLM is advisory, never fatal
                flagged = False
            if flagged:
                hits.append(EscalationRuleHit(
                    rule="self_harm",
                    risk_level="critical",
                    reason="LLM 判定存在自伤风险,需立即转人工",
                    matched_keywords=(),
                    message=SELF_HARM_MESSAGE,
                ))
        # Critical sorts first so callers can act on hits[0].
        hits.sort(key=lambda h: RISK_LEVELS.index(h.risk_level), reverse=True)
        return hits

    def highest(self, text: str, *, llm=None) -> EscalationRuleHit | None:
        """Return the highest-severity hit, or ``None`` if clean."""
        hits = self.scan(text, llm=llm)
        return hits[0] if hits else None

    def must_escalate(self, text: str, *, llm=None) -> bool:
        """True if ``text`` triggers any mandatory-escalation rule."""
        return bool(self.scan(text, llm=llm))


def _llm_self_harm_check(llm: Any, text: str) -> bool:
    """Best-effort LLM self-harm classifier (advisory only).

    Returns True when the model judges the text expresses intent to harm
    oneself.  Any error / unparsable response → False (keywords remain the
    authoritative gate).  The prompt is explicit that the AI must NOT make a
    hiring decision — only flag the risk.
    """
    prompt = (
        "你是安全审核助手。判断下面这段话是否表达了对自身的伤害意图(自杀/自残/自伤)。"
        "注意:只判断风险,不做任何招聘淘汰决定。只回答 'YES' 或 'NO'。\n\n"
        f"文本: {text[:500]}"
    )
    resp = llm.complete(prompt) if hasattr(llm, "complete") else llm(prompt)
    raw = (resp.text if hasattr(resp, "text") else str(resp)).strip().upper()
    return raw.startswith("Y")


__all__ = [
    "PIIMatch",
    "PIIPolicy",
    "InjectionMatch",
    "InjectionGuard",
    "EscalationRuleHit",
    "EscalationRules",
    "SELF_HARM_HOTLINE",
    "SELF_HARM_MESSAGE",
    "LABOUR_DISPUTE_MESSAGE",
    "RISK_LEVELS",
]

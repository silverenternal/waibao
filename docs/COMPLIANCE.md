# COMPLIANCE.md — Privacy & Data Protection (v10.0)

> Owner: waibao DPO / engineering · Covers **GDPR (EU)**, **PIPL (CN)**, **CCPA / CPRA (US-CA)**.
> Related: [Security](SECURITY.md) · [SOC 2 Evidence](SOC2_EVIDENCE.md) · [Architecture §3.4](ARCHITECTURE.md)

v10.0 (T5016) implements a single region-aware privacy control surface that satisfies three jurisdictions at once. The same data-subject request APIs power export/erasure across regions; only the consent surface and cross-border declaration differ by jurisdiction.

---

## 1. Regulatory Mapping

| Requirement | GDPR (EU) | PIPL (CN) | CCPA / CPRA (CA) | Implementation |
|---|---|---|---|---|
| Right of access | Art. 15 | §45 | §1798.100 | `GET /api/gdpr-v2/access` — structured JSON bundle |
| Right to erasure | Art. 17 | §47 | §1798.105 | `POST /api/gdpr-v2/forget` — server-side `forget_user` RPC |
| Right to portability | Art. 20 | §45 | §1798.100(d) | `GET /api/gdpr-v2/access` returns machine-readable JSON |
| Do Not Sell / Share | — | — | §1798.120 / §1798.121 | `POST /api/gdpr-v2/ccpa/opt-out` |
| Global Privacy Control | — | — | §1798.135(b) | GPC header auto-opts-out; `source: gpc_header` |
| Records of processing | Art. 30 | §51 | — | `audit_log_v2` (append-only) |
| Breach notification | Art. 33 | §57 | §1798.82 | Alert pipeline → 72h authority notice workflow |
| Cross-border transfer | Ch. V | §38–§43 | — | PIPL declaration banner + transfer record |

---

## 2. Region-Aware Consent Surface

`frontend/components/privacy/PrivacyRightsPanel.tsx` renders jurisdiction-appropriate controls based on a `region` prop (`EU | CN | CA | GLOBAL`):

- **EU (GDPR):** access / erasure / portability buttons + RoPA link.
- **CN (+ HK/MO/TW) (PIPL):** a cross-border transfer declaration banner is surfaced on every data export, and the export bundle includes the PIPL transfer declaration.
- **CA (CCPA/CPRA):** Do-Not-Sell + Do-Not-Share toggles; honours the `Sec-GPC` header (auto-opt-out, attributed via `source: gpc_header`).
- **GLOBAL:** access + erasure only (baseline rights).

API surface:

```
GET  /api/gdpr-v2/access            Art. 15 structured export (JSON bundle)
POST /api/gdpr-v2/forget            Art. 17 erasure
GET  /api/gdpr-v2/ccpa/status       current CCPA opt-out preference
POST /api/gdpr-v2/ccpa/opt-out      set Do-Not-Sell / Do-Not-Share
POST /api/gdpr-v2/ccpa/request      open a verifiable consumer request
```

---

## 3. GDPR (EU)

### Data subject rights
- **Access (Art. 15):** `GET /api/gdpr-v2/access` returns all personal data we hold, structured by category, in a downloadable JSON bundle.
- **Erasure (Art. 17):** `POST /api/gdpr-v2/forget` triggers the server-side `forget_user` RPC which anonymises/hard-deletes PII, preserves legally-required audit rows, and revokes active consent.
- **Portability (Art. 20):** the same access endpoint returns machine-readable JSON the subject can transmit to another controller.
- **Rectification (Art. 16):** profile self-service in the Jobseeker/Profile surface.

### Records of processing (Art. 30)
`audit_log_v2` is the system of record: append-only, every PII access via the `@audit` decorator, admin-only read, CSV export for supervisory-authority submissions.

### Breach notification (Art. 33)
The alerting pipeline (`docs/ALERTING.md`) routes high-severity security events to the on-call DPO. The documented runbook covers the 72-hour authority notification window.

### Lawful basis & retention
- Lawful bases: contract (core service), legitimate interest (matching/analytics — with objection right), consent (optional analytics/marketing — per-purpose, withdrawable).
- Retention: default 730 days; a background job archives/expunges expired records.

---

## 4. PIPL (China, 个人信息保护法)

### Cross-border transfer (§38–§43)
When a data subject is in a PIPL region (`CN` and the territories `HK/MO/TW`), every export bundle carries a **cross-border personal-information transfer declaration** recording purpose, recipient jurisdiction, and the legal transfer mechanism. The frontend surfaces a PIPL banner before the download so the subject is informed.

### Separate consent for sensitive PI
Sensitive categories (ID numbers, biometrics from video interviews) require **separate, explicit consent** — never bundled with the general ToS. Withdrawal is one-click and propagates to all downstream processors.

### Data subject rights (§44–§50)
Mapped to the same `gdpr-v2` endpoints (access / copy / correction / deletion / withdrawal). PIPL additionally requires a response within a defined window; the request queue tracks SLA per request.

### Localisation
The multi-region topology (`docs/MULTI_REGION.md`) supports a CN-resident deployment so that, where required, personal information of mainland subjects is stored and processed within the PRC.

---

## 5. CCPA / CPRA (California)

### Do Not Sell / Do Not Share (§1798.120 / §1798.121)
- `POST /api/gdpr-v2/ccpa/opt-out` toggles `do_not_sell` and `do_not_share` independently so toggling one does not reset the other.
- Opted-out subjects are excluded from "sale"/"share" (including cross-context behavioural advertising) downstream.

### Global Privacy Control (§1798.135(b))
The backend honours the `Sec-GPC: 1` request header: it auto-opts-out the consumer and records `source: gpc_header` so the preference is attributable and auditable. The frontend panel surfaces the GPC badge.

### Verifiable consumer requests (§1798.105 / §1798.130)
`POST /api/gdpr-v2/ccpa/request` opens a verifiable consumer request; identity is confirmed via the authenticated session / bearer token before any data is released or deleted.

### Non-discrimination
Exercising privacy rights never degrades service quality or price for the consumer.

---

## 6. Consent Architecture

- **Per-purpose consent** (v6.0+): consent is recorded per processing purpose, not a single blanket toggle.
- **Granular + withdrawable**: each purpose can be independently withdrawn; withdrawal propagates to downstream processors via the event bus.
- **Versioned policy**: the privacy policy is versioned; consent is bound to the policy version in force at the time.

---

## 7. Evidence & Audit

| Control | Evidence |
|---|---|
| Consent records | `consent` table (per-purpose, versioned) |
| PII access log | `audit_log_v2` (append-only, `@audit` decorator) |
| Erasure proof | `forget_user` RPC produces a deletion manifest |
| Export bundle | `/api/gdpr-v2/access` JSON includes provenance + PIPL declaration |
| SOC 2 mapping | `docs/SOC2_EVIDENCE.md` (Privacy P1–P8 family) |

For the full control-to-implementation trace, see [SOC2_EVIDENCE.md](SOC2_EVIDENCE.md).

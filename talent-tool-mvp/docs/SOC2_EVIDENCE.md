# SOC 2 Trust Services Criteria — Control Evidence (v10.0)

**Status:** Living evidence map. Each row links a SOC 2 Trust Services
Criterion (TSC) to the concrete code, config, or CI job that implements it.
Auditors should be able to trace any criterion → implementation → automated
test in under two minutes.

**Scope:** RecruitTech backend (`talent-tool-mvp/backend`) + frontend
(`talent-tool-mvp/frontend`) + CI (`.github/workflows/`).

**Control categories covered (the 5 SOC 2 TSC families):**

| # | Family | Criteria prefix | Controls |
|---|--------|-----------------|----------|
| 1 | **Security** (Common Criteria) | CC1–CC9 | 23 |
| 2 | **Availability** | A1 | 8 |
| 3 | **Processing Integrity** | PI1 | 6 |
| 4 | **Confidentiality** | C1 | 7 |
| 5 | **Privacy** | P1–P8 | 12 |
|   | **Total** |   | **56** |

> "Implementation" column uses repo-rooted paths. "Automated check" is the
> CI job or test that fails the build if the control regresses.

---

## 1. Security — Common Criteria (CC1–CC9)

| Criterion | Control | Implementation | Automated check |
|-----------|---------|----------------|-----------------|
| CC1.1 | Code of conduct / security responsibilities documented | `CLAUDE.md`, `docs/AUDIT_SECURITY.md` | — |
| CC2.1 | Structured audit log of all sensitive actions | `services/platform/audit_v2.py` (`audit_log_v2`) | `tests/test_audit_v2.py`, `test_audit_coverage.py` |
| CC2.2 | Every PII touch is audited with PII fields tagged | `audit_pii` AST decorator | `tests/test_pii_coverage.py` (100% PII coverage gate) |
| CC3.2 | Risk assessment drives control selection | `docs/audits/AUDIT_SECURITY.md` (attack surface) | — |
| CC4.1 | Continuous vulnerability scanning (deps + OS + image) | `.github/workflows/security.yml` (safety), `container-ci.yml` (trivy) | CI fails on HIGH/CRITICAL CVE with fix |
| CC4.2 | Static analysis (SAST) | `security.yml` (bandit), `container-ci.yml` (hadolint) | CI on push + PR |
| CC5.1 | Secrets never committed | `security.yml` (detect-secrets), `container-ci.yml` (gitleaks) | CI fails on drift |
| CC5.2 | Multi-tenant data isolation (RLS) | `services/platform/tenant_context.py` + DB `USING/WITH CHECK` | `tests/test_api_tenant_isolation.py` |
| CC6.1 | Authenticated access only (JWT bearer) | `api/auth.py` (`get_current_user`, `require_role`) | `tests/test_security.py` |
| CC6.1 | Weak/placeholder JWT secrets rejected at boot | `services/auth/session.py` (`WEAK_JWT_SECRETS`, fail-fast) | `tests/test_kms.py`, `test_fail_fast.py` |
| CC6.2 | 3-tier rate limiting (IP / user / tenant) | `services/security/rate_limiter.py` (L1/L2/L3) | `tests/test_security_t5017.py` |
| CC6.3 | SSRF blocked on outbound webhooks | `services/security/ssrf.py` + `webhook/dispatcher.py` | `tests/test_security_t5017.py` (12 cases) |
| CC6.3 | CSRF double-submit on state-changing routes | `services/security/csrf.py` | `tests/test_security_t5017.py` (8 cases) |
| CC6.5 | PII encrypted at rest (field-level) | `services/platform/crypto.py`, `pii_field_encryption.py` | `tests/test_pii_encryption.py` |
| CC6.5 | KMS-managed encryption keys | `services/platform/crypto.py` (env-driven secret) | `tests/test_kms.py` |
| CC6.6 | Prompt-injection guard on all 16 agents | `agents/governance.py` + `agents/gateway.py` (default guard) | `tests/test_governance_t5018.py` |
| CC6.6 | JIT account linking off by default | `services/auth/jit.py` (`link_by_email=False`) | `tests/test_governance_t5018.py` |
| CC6.6 | JIT email-domain allow-list | `services/auth/jit.py` (`allowed_domains`) | `tests/test_governance_t5018.py` |
| CC6.7 | Session idle/absolute/impossible-travel policy | `services/auth/session_policy.py` (30m / 8h / geo) | `tests/test_governance_t5018.py` |
| CC7.1 | Unified error envelope (no stack-trace leak) | `services/platform/errors.py` + `api/middleware.py` | `tests/test_error_envelope.py` |
| CC7.2 | Incident breach workflow (Art. 33 clock) | `api/breach.py`, `services/compliance/breach.py` | `tests/test_compliance_t5016.py` |
| CC7.4 | Anomaly detection + alerting | `services/platform/anomaly_detector.py`, `auto_report.py` | `tests/test_alerting.py` |
| CC8.1 | Change management: all code via PR + CI gate | `.github/workflows/*` (5 jobs on PR) | CI required check |

---

## 2. Availability (A1)

| Criterion | Control | Implementation | Automated check |
|-----------|---------|----------------|-----------------|
| A1.1 | Capacity / load tested | `tests/load/` (Locust) | `tests/load/` runs on release |
| A1.2 | Health endpoint for orchestrators | `main.py` `/api/health` | Dockerfile `HEALTHCHECK` |
| A1.2 | Resilient retries with backoff | `services/platform/retry.py` + `resilience.py` | `tests/test_retry.py` |
| A1.2 | Provider fail-fast + degradation | `agents/gateway.py` (degrade path) | `tests/test_agent_gateway.py` |
| A1.3 | Backup + restore scripts | `scripts/` (T2003 灾备), `services/platform/backup.py` | `tests/test_backup.py` |
| A1.3 | Partitioning + full-text for scale | DB migrations (T5011/T5013) | DB audit |
| A1.3 | Multi-region deployment verification | `docs/` (T2002) | — |
| A1.4 | SLA monitor (DSR + breach clocks) | `api/gdpr_v2.py` `/sla`, `sla_monitor.py` | `tests/test_compliance_t5016.py` |

---

## 3. Processing Integrity (PI1)

| Criterion | Control | Implementation | Automated check |
|-----------|---------|----------------|-----------------|
| PI1.1 | Strong agent I/O contracts (Pydantic) | `agents/contracts.py`, `agents/gateway.py` | `tests/test_agent_contracts.py` (100+) |
| PI1.2 | Bias enforcement on matching/JD | `services/bias_enforcement.py`, `api/bias_enforce.py` | bias parity tests |
| PI1.2 | Fake-credential (PS) detection | `services/ps_detection.py` | `tests/` (T3702) |
| PI1.3 | Mutual evaluation + consensus | `agents/evaluator/mutual_evaluator.py`, `consensus_v2.py` | `tests/test_journal_evaluator.py` |
| PI1.4 | Data validation at API boundary | `api/middleware.py` (contract deps) | `tests/test_api_contract.py` |
| PI1.5 | Feature/service toggles for controlled rollout | `services/platform/service_toggle/` | `tests/test_service_toggle.py` (50+) |

---

## 4. Confidentiality (C1)

| Criterion | Control | Implementation | Automated check |
|-----------|---------|----------------|-----------------|
| C1.1 | Confidentiality classification on every audit row | `audit_v2.py` (`data_classification`) | `tests/test_audit_coverage.py` |
| C1.2 | PII field encryption | `services/pii_field_encryption.py` | `tests/test_pii_encryption.py` |
| C1.2 | Crypto-shred on right-to-be-forgotten | `api/gdpr_v2.py` `/forget` | `tests/test_gdpr_v2.py` |
| C1.3 | Secrets via env / KMS, never in image | `backend/.dockerignore`, `.env.example` | gitleaks + detect-secrets CI |
| C1.4 | Transmission encryption (TLS termination) | Ingress (documented `docs/`); HSTS-ready | — |
| C1.5 | Webhook payload HMAC-signed | `services/webhook/signer.py` | `tests/test_webhooks.py` |
| C1.6 | Retention periods in processing register | `api/gdpr_v2.py` `/processing-register` (Art. 30) | `tests/test_gdpr_v2.py` |

---

## 5. Privacy (P1–P8)

| Criterion | Control | Implementation | Automated check |
|-----------|---------|----------------|-----------------|
| P2.1 | Per-purpose consent management | `services/platform/consent.py` | `tests/test_consent.py` |
| P2.2 | Region-aware lawful basis (GDPR/PIPL/CCPA) | `api/gdpr_v2.py` `LAWFUL_BASIS_TEMPLATES` | `tests/test_gdpr_v2.py` |
| P3.1 | Data subject request (DSR) lifecycle + 30-day SLA | `api/gdpr_v2.py` `/dsr`, `/sla` | `tests/test_compliance_t5016.py` |
| P4.1 | Art. 15 right of access (structured export) | `api/gdpr_v2.py` `/access` + `data_export.py` | `tests/test_compliance_t5016.py` |
| P4.2 | Art. 17 right to erasure (crypto-shred) | `api/gdpr_v2.py` `/forget` | `tests/test_gdpr_v2.py` |
| P4.3 | Art. 20 data portability (JSON bundle) | `api/gdpr_v2.py` `/portability`, `/access` | `tests/test_compliance_t5016.py` |
| P5.1 | PIPL cross-border transfer declaration | `services/compliance/data_export.py` | `tests/test_compliance_t5016.py` |
| P5.1 | CCPA Do-Not-Sell / Do-Not-Share | `services/compliance/ccpa.py`, `api/gdpr_v2.py` `/ccpa/*` | `tests/test_compliance_t5016.py` |
| P5.1 | CCPA Global Privacy Control honoured | `ccpa.py` `apply_gpc_header` | `tests/test_compliance_t5016.py` |
| P6.1 | Art. 33/34 breach notification (72h clock) | `api/breach.py`, `services/compliance/breach.py` | `tests/test_compliance_t5016.py` |
| P7.1 | Consent withdrawal does not break prior processing | `consent.py` (`withdraw` is non-retroactive) | `tests/test_consent.py` |
| P8.1 | Privacy controls surfaced to users | `frontend/components/privacy/PrivacyRightsPanel.tsx` | frontend build |

---

## Automated gate summary

The following CI jobs collectively enforce these controls on every PR and
weekly (no control is documentation-only without an automated check unless
explicitly marked "—"):

| Workflow | Jobs | Controls enforced |
|----------|------|-------------------|
| `security.yml` | bandit, safety, detect-secrets, pnpm audit, sqlmap | CC4.1, CC4.2, CC5.1 |
| `container-ci.yml` | gitleaks, pip-compile, trivy (fs), trivy (image), hadolint | CC4.1, CC5.1, CC8.1 |
| `frontend-ci.yml` | tsc, next build, storybook a11y | PI1.4, P8.1 |
| pytest (local + CI) | 3800+ tests across `tests/test_*.py` | all rows with a test reference above |

## Change log
- **v10.0 (T5019)** — initial SOC 2 evidence map: 56 controls across 5 TSC
  families, cross-referenced to the T5016–T5018 implementation and the
  existing T5001–T5015 platform hardening.

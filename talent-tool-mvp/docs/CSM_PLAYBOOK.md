# Waibao CSM Playbook — T2001

> **Owner:** Customer Success team
> **Audience:** CSMs, Onboarding Engineers, Sales Engineers (post-sale)
> **Goal:** Land, expand, retain — first mid-market paying customer ARR ≥ ¥300k.

---

## 1. Customer lifecycle (4 phases)

```
[Onboarding 0–14d] → [Adoption 14–60d] → [Value Realisation 60–120d] → [Expansion 120d+]
```

Each phase has explicit **exit criteria**, **CSM time commitment**, and **risk triggers**.

---

## 2. Phase 1: Onboarding (Day 0 – 14)

### Goals
- Customer **goes live** with at least one real req running through Waibao
- All 3 user personas (Hiring Manager, Recruiter, Candidate) trained
- Tech integration smoke-tested (SSO, ATS sync, calendar)

### Day-by-day

| Day  | CSM action                                  | Deliverable                            |
|------|----------------------------------------------|----------------------------------------|
| 0    | Kickoff call (60 min)                        | Project plan in shared doc             |
| 1    | Provision tenant + SSO                       | Login works for all admins             |
| 2    | ATS integration call (Greenhouse/Lever/etc.) | Bi-directional sync verified           |
| 3    | Calendar + Slack/Teams install               | Recruiter hours tracked                |
| 5    | Hiring-manager training (30 min)             | 5+ managers onboarded                  |
| 7    | First req "test drive" with CSM shadowing    | Pipeline configured                    |
| 10   | Recruiter deep-dive (90 min)                 | AI matching + copilot mastered        |
| 14   | **Go-live review** + 30-day plan             | Exit onboarding gate                   |

### Exit criteria
- [ ] ≥ 3 active reqs in Waibao
- [ ] ≥ 5 hiring managers have logged in ≥ 3 times
- [ ] ATS sync verified end-to-end (candidates round-trip)
- [ ] Recruiter hours/week metric flowing into dashboard

### Risk triggers → escalate to Head of CS
- Day 5 with no ATS integration scheduled
- Day 10 with < 2 reqs migrated
- Any compliance / DPIA blocker not resolved by Day 7

---

## 3. Phase 2: Adoption (Day 14 – 60)

### Goals
- **Daily active recruiters ≥ 70% of paid seats**
- **Weekly active hiring managers ≥ 50%**
- **Subscription engine opt-in ≥ 60% of open reqs**

### Weekly cadence

| Cadence     | Activity                                                  | Metric reviewed                |
|-------------|-----------------------------------------------------------|--------------------------------|
| Weekly 30m  | CSM ↔ Recruiter lead check-in                             | DAU, req throughput, blockers  |
| Bi-weekly   | CSM ↔ Hiring-manager focus group (2–3 mgrs)               | Copilot satisfaction, NPS     |
| Weekly 15m  | CSM ↔ IT / Security contact                               | SSO, audit, incident tickets   |
| Monthly 60m | QBR (Quarterly Business Review) — pilot month 1           | Time-to-shortlist, ROI        |

### Adoption scorecard (per customer, weekly)

| Signal                          | Weight | Source                  | Healthy    |
|---------------------------------|--------|-------------------------|------------|
| Weekly active recruiters / seats| 30%    | Telemetry               | ≥ 70%      |
| Reqs created / week             | 20%    | DB                      | ≥ 5        |
| AI interview completion rate    | 15%    | AI interview service    | ≥ 60%      |
| Hiring manager NPS              | 15%    | In-app survey           | ≥ 30       |
| Copilot "thumbs up" ratio       | 10%    | Telemetry               | ≥ 60%      |
| Subscription opt-in             | 10%    | job_subscription        | ≥ 60%      |

**Adoption score < 60 = at-risk.** Trigger Phase 4 playbook.

---

## 4. Phase 3: Value Realisation (Day 60 – 120)

### Goals
- **Time-to-shortlist reduced by ≥ 50% vs baseline**
- **Recruiter hours/req reduced by ≥ 40%**
- **NPS ≥ 40** (recruiter) and **≥ 30** (hiring manager)
- **Customer submits case study**

### Customer evidence pack (built by Day 90)

Required artefacts for the first paying customer:

1. **Baseline metrics** captured at Day 0 (TTV, recruiter hours, offer-accept rate)
2. **Day-60 metrics** measured against baseline
3. **1 case study** (1-page PDF, see `case_study_1.md` template)
4. **2 references** willing to take a prospect call (recorded in CRM)
5. **1 video testimonial** (60 sec, MP4) — preferred but not blocking

### Renewal gating (annual contracts)

| Day 90   | Renewal risk register updated; CSM aligns w/ AE            |
| Day 120  | **Renewal forecast** in CRM; green / yellow / red            |
| Day 180  | Renewal proposal sent if not auto-renewal                    |
| Day 270  | Renewal signed (target: 60 days before end-of-term)          |

---

## 5. Phase 4: Expansion (Day 120+)

### Expansion levers (in order of priority)

1. **Seat expansion** — easiest, CSM-led. **Target: +20% seats Year 1.**
2. **Tier upgrade** Pro → Enterprise — needs exec sponsorship.
3. **Add-on attach:** Dedicated CSM, AI interview minutes, custom integrations.
4. **Multi-region** — UK/EU/CN/SG VPC roll-out.
5. **Multi-year commit** — `VOLUME` discount (20% off).

### Expansion playbook

```
Recruiter lead says "we're going to hire 50 more this year"
        ↓
CSM schedules Value Realisation review
        ↓
AE presents expansion proposal (seats + tier + multi-year)
        ↓
Sales Engineer scopes integration work
        ↓
Legal redlines → MSA addendum signed
        ↓
BillingService auto-charges new tier on Day 1 of next period
```

---

## 6. Risk & intervention matrix

| Risk signal                                       | Severity | CSM action                                     | Escalation                |
|---------------------------------------------------|----------|-------------------------------------------------|---------------------------|
| DAU drops > 30% week-over-week                    | High     | Same-day call; identify root cause              | Head of CS within 24h     |
| Hiring manager complains AI scoring is biased     | Critical | Pause AI interview, run bias audit (T1801)      | CTO + Compliance Lead      |
| Payment fails repeatedly                          | High     | Coordinate with billing@; update card flow      | AE + Finance              |
| Customer requests custom feature                  | Medium   | Triage vs roadmap; respond within 5 business days | Product via triage board |
| Customer churns intent (cancellation request)     | Critical | Win-back within 48h; exec sponsor call          | Head of CS + AE           |
| Region data residency requirement not met         | High     | Engineering assessment within 1 wk               | CTO                       |
| Security incident at customer site (their breach) | Critical | Coordinate with their CISO; ours is read-only   | CISO                       |

---

## 7. Tools & systems

| System                   | Use                                | Owner            |
|--------------------------|------------------------------------|------------------|
| CRM (HubSpot)            | Account, contacts, renewal dates   | Sales / CSM      |
| Intercom                 | In-app messaging, NPS              | CSM              |
| Linear                   | Customer feature requests          | Product          |
| Notion                   | Playbooks, customer wiki           | CSM              |
| Looker dashboard         | Adoption scorecard                 | CS Ops           |
| PagerDuty                | Customer-impacting incident        | SRE + CSM        |
| `BillingService`         | Subscription state, AR, renewals   | Engineering      |
| `subscription_service.py`| Trial-to-paid + auto-renew + alerts| Engineering (T2001) |

---

## 8. CSM KPIs (quarterly)

| KPI                              | Target |
|----------------------------------|--------|
| Net Revenue Retention            | ≥ 110% |
| Gross churn (logo)               | ≤ 5%   |
| CSAT (post-call survey)          | ≥ 4.5 / 5 |
| Time to first value (TTFV)       | ≤ 14 days |
| % customers with health score ≥ 80 | ≥ 80% |
| Expansion ARR / CSM              | ≥ ¥400k |
| NPS (recruiter)                  | ≥ 40   |

---

## 9. First paying customer — Day-90 plan

| Week | Activity                                                |
|------|----------------------------------------------------------|
| W0   | Pilot kickoff, baseline metrics locked                   |
| W2   | Go-live review; first req migrated                       |
| W4   | Adoption scorecard week 2; identify power users         |
| W6   | First value-realisation review; recruiter hours trending |
| W8   | Hiring-manager focus group; collect quotes               |
| W10  | Co-author case study (1 page)                            |
| W12  | **QBR** — share ROI, propose expansion                  |
| W13  | Renewal / expansion close                                |

**Done definition for first ARR ≥ ¥300k:**
- Pro tier × Yearly × 1 customer, **OR**
- Starter × Yearly × 10 customers, **OR**
- Enterprise × any interval × 1 customer
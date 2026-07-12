# Waibao Pricing — T2001

> **Effective:** 2026-07-12
> **Version:** v1.0 (companion to Sales Deck v1.0)
> **Owner:** Sales + Finance

---

## 1. Tier matrix

|                  | Starter             | **Pro** ⭐           | Enterprise                  |
|------------------|---------------------|----------------------|------------------------------|
| **Monthly**      | ¥299 / £36          | ¥999 / £120          | Quote-based                 |
| **Yearly**       | ¥2,990 / £360       | ¥9,990 / £1,200      | Quote-based                 |
| **Yearly disc.** | 16.7% off           | 16.7% off            | n/a                          |
| **Trial**        | 14 days, no card    | 14 days, no card     | 30 days, sales-assisted     |
| **Seats**        | 5 talent partners   | 20 talent partners   | Unlimited                   |
| **Candidates/mo**| 200                 | 5,000                | Unlimited                   |
| **AI interview** | 50 sessions/mo      | 500 sessions/mo      | Unlimited                   |
| **Storage**      | 50 GB               | 500 GB               | Custom                      |
| **Data residency** | UK / EU          | UK / EU / CN / SG    | Any region, dedicated VPC   |
| **Support SLA**  | Email, 24h          | Priority, 4h         | Named CSM, 1h, 24×7          |
| **SSO/SAML**     | —                   | —                    | ✓ (Okta, Azure AD, Google)  |
| **Audit logs**   | 30 days             | 90 days              | 7 years, exportable         |
| **API rate**     | 60 req/min          | 600 req/min          | Custom                       |
| **Custom rules** | —                   | 20 active            | Unlimited                    |
| **Webhooks**     | 5 endpoints         | 50 endpoints         | Unlimited                    |

> All prices **exclusive of VAT/sales tax**. Invoiced monthly or yearly in advance. Currency auto-binds to billing country (GBP for UK, CNY for CN, USD default elsewhere).

---

## 2. Add-ons

| Add-on                | Unit                | Price (monthly)         |
|-----------------------|---------------------|--------------------------|
| Extra seat            | per talent partner  | Starter ¥60 / Pro ¥50    |
| Extra candidates      | per 1,000           | Starter ¥80 / Pro ¥60    |
| AI interview minutes  | per 100 min         | Starter ¥40 / Pro ¥30    |
| Dedicated CSM         | per year            | £12,000 / ¥99,000        |
| Custom data residency | per region/year     | Quote                    |
| On-prem connector     | one-time            | Quote                    |
| Premium LLM tier      | per org             | +20% of base             |
| Background check      | per check           | Pass-through + 5%        |

---

## 3. Discounts

| Code        | Description                       | Eligibility                       | Discount   |
|-------------|-----------------------------------|-----------------------------------|------------|
| `NONPROFIT` | Registered charity / NGO          | Verified by charity register     | 30% off    |
| `EDU`       | Higher-ed institution             | .edu / .ac.uk domain              | 40% off    |
| `STARTUP`   | Seed to Series A, < 50 employees  | Crunchbase verified              | 50% off Year 1 |
| `VOLUME`    | Multi-year commit                 | 3-year upfront                    | 20% off    |
| `PARTNER`   | System integrator referral        | Signed partner agreement         | 10% referral fee |
| `PILOT`     | Reference customer willing to     | Case study + 2 references         | 25% off Year 1 |

**Discounts stack up to 50% off list price.** Annual prepay required for `STARTUP` and `VOLUME`.

---

## 4. Payment & billing mechanics

- **Provider:** Stripe (global) + WeChat Pay / Alipay (CN). Mock provider for trials.
- **Interval:** Monthly or yearly. Yearly saves ~17%.
- **Trial:** 14 days (Starter/Pro), 30 days (Enterprise). **No credit card required to start.**
- **Auto-renewal:** ON by default for monthly + yearly. Off by request for Enterprise.
- **Failed payment handling:** retry at D+1, D+3, D+7; alert at D+3 to billing email; status → `past_due` at D+7; suspend API at D+14 (data retained 60 days).
- **Cancellation:** Effective end of period by default. Immediate cancel available for Enterprise only.
- **Refund policy:** 30-day money-back guarantee on first subscription, full refund.

See `subscription_service.py` for the source-of-truth implementation.

---

## 5. ARR target & ramp

| Quarter | New customers | Net new ARR (CNY) | Cumulative ARR (CNY) |
|---------|---------------|--------------------|----------------------|
| 2026 Q3 | 3             | ¥300,000           | ¥300,000             |
| 2026 Q4 | 5             | ¥600,000           | ¥900,000             |
| 2027 Q1 | 8             | ¥1,200,000         | ¥2,100,000           |
| 2027 Q2 | 10            | ¥1,800,000         | ¥3,900,000           |

**First paying customer target:** ARR ≥ **¥300,000** (Pro × yearly × 1 customer, or Starter × yearly × 10) by end of 2026 Q3.

---

## 6. Competitive positioning

|                   | Waibao Pro  | Workable Standard | Greenhouse Essential | Lever Core |
|-------------------|-------------|--------------------|----------------------|------------|
| Yearly GBP        | £1,200      | £4,500             | £5,400               | £4,800     |
| Seats             | 20          | 10                 | 20                   | 15         |
| AI interview      | ✓ (500/mo)  | Add-on (£££)       | Add-on               | —          |
| RAG explainability| ✓           | —                  | Partial              | —          |
| UK GDPR audit log | 90 days     | 30 days            | 60 days              | 60 days    |
| Self-serve trial  | ✓ (14d)     | ✓ (14d)            | Sales-led             | Sales-led |

**Pricing principle:** we are **30–50% cheaper** than Greenhouse/Lever at comparable seats, with **stronger AI features**.

---

## 7. Sales ops checklist

- [ ] All outbound references `PRICING.md` v1.0
- [ ] Sales Engineers carry 3-year TCO calculator (Excel + web)
- [ ] Quote template auto-generates from `BillingService.create_checkout` API
- [ ] Discount codes enforced in `billing/discount_codes.py`
- [ ] Quarterly price review (next: 2026-09-30)

---

## 8. Change log

| Date       | Version | Change                       | Owner  |
|------------|---------|------------------------------|--------|
| 2026-07-12 | v1.0    | Initial public pricing       | Sales  |
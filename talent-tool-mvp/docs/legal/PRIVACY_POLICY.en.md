# Privacy Policy

**Version**: v1.0  
**Effective Date**: 2026-07-12  
**Product**: waibao — AI-powered recruitment collaboration platform  
**Operator**: Waibao Technology Co., Ltd.

---

This policy is prepared in accordance with the EU General Data Protection Regulation (GDPR), the UK Data Protection Act 2018, the Personal Information Protection Law of the People's Republic of China, and equivalent frameworks. Please read it carefully; by using the service, you confirm that you have read and understood the entire policy.

## 1. What We Collect

### 1.1 Information you provide
- **Account**: name, email, phone number, password hash, city, headline
- **Candidate**: candidate name, email, phone, ID number (optional), resume body, work history, education, skills
- **Company**: unified social credit code, company name, contact person, business license, invoice title
- **Collaboration**: text, images, files, voice transcripts, decision records in rooms

### 1.2 Information collected automatically
- **Device & log**: IP address (hashed), device model, browser UA, OS
- **Behavior**: pages visited, dwell time, feature usage (anonymized)
- **Cookies**: session, preferences, statistics (see Cookie Policy)

### 1.3 From third parties
- Public resumes from third-party job boards (Boss Zhipin, Lagou, Adzuna) with your authorization
- DingTalk / WeCom / Feishu OAuth profile data (only when you explicitly authorize)

## 2. How We Use Information

| Purpose | Fields involved | Legal basis |
|---|---|---|
| Account registration & login | email, phone, password hash | Contract necessity |
| Candidate profile & matching | resume, skills, experience | Explicit consent |
| Multi-party collaboration | uploaded content, chat records | Explicit consent |
| Real-name verification (China) | name, ID number | Legal obligation |
| Billing & invoicing | bank account (masked) | Contract necessity |
| Security & compliance | IP (hashed), activity logs | Legal obligation |
| Product improvement (anonymized stats) | anonymized behavior | Legitimate interest |
| Cross-border transfer (optional) | fields you explicitly consent to | Explicit consent |

## 3. Storage and Cross-Border Transfers

### 3.1 Storage location
- **Mainland China users**: data is stored by default in domestic data centers (Aliyun / Tencent Cloud), evaluated as MLPS 2.0 Level 3
- **Overseas users**: routed to the corresponding Supabase instance (SG / US) by region
- You may request an export copy at any time

### 3.2 Cross-border transfers
Cross-border transfers only occur when:
- You actively use overseas features (e.g., overseas job matching), or
- You explicitly consent to cross-border transfer (selectable in the Cookie banner)

Before any cross-border transfer we conduct a Personal Information Protection Impact Assessment (PIPIA), and we sign Standard Contractual Clauses or obtain certification.

### 3.3 Retention periods

| Category | Retention | Deletion method |
|---|---|---|
| Account information | Account lifetime + 30 days after cancellation | Soft + physical deletion |
| Resumes, collaboration content | 24 months (auto-archived on expiry) | Physical deletion |
| Operation & audit logs | At least 6 months (5 years for finance-critical roles) | Physical deletion |
| Real-name verification data | Raw ID images deleted within 24 hours after verification | Physical deletion |

## 4. Sharing and Disclosure

We do not sell your personal information. Sharing is limited to:

1. **Your explicit consent**: e.g., sharing your resume with a specific employer
2. **Service providers**: limited to necessary scope under a strict Data Processing Agreement (DPA)
3. **Regulators**: when required by law or competent authorities
4. **Dispute resolution**: as part of legally mandated proceedings

## 5. Your Rights

Under GDPR / UK GDPR / PIPL you have:

| Right | How to exercise |
|---|---|
| Right to be informed | This policy + processing inventory |
| Right of access | GET /api/gdpr/export |
| Right of rectification | PATCH endpoints per resource |
| Right to erasure (right to be forgotten) | DELETE /api/gdpr/all-data |
| Right to data portability | GET /api/gdpr/export (JSON / CSV) |
| Right to withdraw consent | Account → Privacy settings |
| Right to object to automated decision-making | Account → Privacy settings (disable AI matching) |
| Right to lodge a complaint | Contact DPO / local DPA |

We respond within 15 business days; in special cases no more than 30 days.

## 6. Security

- **Encryption**: PII fields use Fernet (AES-128-CBC + HMAC-SHA256); sensitive files encrypted at rest
- **Access control**: role-based least-privilege; MFA required for all PII access
- **Audit**: every PII access logged to audit_log; retained at least 6 months
- **Penetration tests**: third-party tests every quarter
- **Incident response**: users and regulators notified within 24 hours of any confirmed breach

## 7. Children

The Platform is not intended for users under 14. If we discover such data, we will proactively delete it.

## 8. Changes to this Policy

We may update this policy. Material changes will be notified via in-app notice or email. The updated policy is effective from the date of publication.

## 9. Contact

- **Data Protection Officer (DPO)**: dpo@waibao.example
- **Privacy email**: privacy@waibao.example
- **Address**: Zhangjiang Hi-Tech Park, Pudong New Area, Shanghai, China

---

*Effective from 12 July 2026.*
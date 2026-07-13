# v7.0 T3003 — White-label & Private Deployment

> Audience: engineering, customer success, and customer DevOps teams.

This document covers everything you need to ship Waibao as a
**branded product** for an enterprise customer and to **deploy it
inside their cloud**. White-label (UI / email / PDF theming) and
private deployment (Helm / Terraform / Docker Compose) are designed to
work independently, but most enterprise deals want both.

---

## 1. Architecture at a glance

```
┌──────────────────────────────────────────────────────────────┐
│                   Customer's Brand (CNAME)                    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│   Caddy / nginx-ingress  (TLS termination, HSTS, CSP)        │
└──────────────────────────────────────────────────────────────┘
        │                                       │
        ▼                                       ▼
┌──────────────────┐                ┌────────────────────────┐
│  Frontend        │                │  Backend               │
│  Next.js 16      │ ◄──SSE/JSON──► │  FastAPI + Python 3.12 │
│  WhiteLabelProv. │                │  WhitelabelService     │
└──────────────────┘                └──────────┬─────────────┘
                                                │
        ┌───────────────┬───────────────┬───────┼────────┐
        ▼               ▼               ▼       ▼        ▼
   Postgres        ClickHouse       Qdrant   Redis   S3/Storage
   (Supabase       (BI / DW)        (vector) (cache)  (uploads)
    RLS)
```

The `WhitelabelService` lives in `backend/services/platform/whitelabel.py`
and is the single source of truth for branding. The frontend reads it
through `frontend/lib/theme.ts` and pushes the values into CSS custom
properties at runtime via `<WhiteLabelProvider/>`.

---

## 2. Branding data model

Schema lives in `supabase/migrations/052_whitelabel.sql`. The
`tenant_branding` table is the per-tenant record:

| Column            | Type           | Notes                                          |
|-------------------|----------------|------------------------------------------------|
| `tenant_id`       | TEXT PK        | matches the tenant identifier in JWTs          |
| `product_name`    | TEXT           | 2-64 chars, validated                          |
| `domain`          | TEXT           | optional; used for canonical links             |
| `logo_url`        | TEXT           | https URL, recommended PNG/SVG transparent     |
| `favicon_url`     | TEXT           |                                                  |
| `primary_color`   | TEXT           | `#RRGGBB` validated via CHECK constraint       |
| `secondary_color` | TEXT           |                                                  |
| `accent_color`    | TEXT           |                                                  |
| `font_family`     | TEXT           | allow-list: Inter / Roboto / PingFang / etc.   |
| `support_email`   | TEXT           | shown in email footers                          |
| `footer_text`     | TEXT           | shown in email + PDF footers                    |
| `locale`          | TEXT           | zh-CN / en-US / ja-JP                            |
| `email_template`  | TEXT           | transactional / marketing / report / etc.       |
| `report_template` | TEXT           | ID referencing PDF template                     |
| `custom_css`      | TEXT           | ≤ 8 KiB, injected into `<style id="waibao-...">` |
| `hide_powered_by` | BOOLEAN        | private-deployment customers often enable      |
| `created_at`      | TIMESTAMPTZ    |                                                  |
| `updated_at`      | TIMESTAMPTZ    | auto-maintained via trigger                     |
| `updated_by`      | TEXT           | actor email / id                                |

Plus an audit log in `tenant_branding_audit` (append-only).

### RLS

Three policies:

1. `anon, authenticated` can `SELECT` any row (used by direct Supabase
   clients in self-hosted deployments without row-level isolation).
2. Authenticated users with a JWT claim `tenant_id = X` and
   `is_admin = true` can modify *their* row.
3. Service role bypass for the FastAPI server.

In hosted mode we **disable** RLS via service-role; the row is read
through the API which enforces tenant scoping via `TenantContext`.

---

## 3. Backend: WhitelabelService

`backend/services/platform/whitelabel.py` exposes:

```python
from services.platform.whitelabel import (
    get_whitelabel_service,
    render_email_html, render_pdf_report_brand,
    to_css_variables,
)

svc = get_whitelabel_service()
branding = svc.get("acme")             # Branding dataclass
css_vars = to_css_variables(branding)   # { "--color-primary": "#...", ... }
email   = render_email_html(branding, body_html="...", subject="...")
pdf_md  = render_pdf_report_brand(branding)
```

### REST endpoints (`backend/api/whitelabel.py`)

| Method | Path                                          | Notes                  |
|--------|-----------------------------------------------|------------------------|
| GET    | `/api/whitelabel/{tenant_id}`                 | public                 |
| GET    | `/api/whitelabel/{tenant_id}/email-preview`   | public                 |
| GET    | `/api/whitelabel/{tenant_id}/pdf-brand`       | public                 |
| PUT    | `/api/whitelabel/{tenant_id}`                 | admin (`x-actor` hdr)  |
| PATCH  | `/api/whitelabel/{tenant_id}`                 | admin                   |
| DELETE | `/api/whitelabel/{tenant_id}`                 | admin                   |
| GET    | `/api/whitelabel/`                            | admin (list)            |

Errors:

* `400 BrandingValidationError` — hex color invalid, URL not https, font not allow-listed, etc.
* `404 BrandingNotFoundError` — DELETE on a row that doesn't exist (strict variant `get_or_404()`).

---

## 4. Frontend: theme.ts + WhiteLabelProvider

`frontend/lib/theme.ts` is a *pure* module — every function works on the
server and the client so Storybook and unit tests can render branding
without a network. The runtime side is `WhiteLabelProvider.tsx`:

```tsx
// app/layout.tsx
import WhiteLabelProvider from "@/components/WhiteLabelProvider";

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>
        <WhiteLabelProvider>{children}</WhiteLabelProvider>
      </body>
    </html>
  );
}
```

The provider:

1. Resolves the tenant (`subdomain > ?tenant= > localStorage > "public"`).
2. Fetches `GET /api/whitelabel/{tenant_id}` on mount.
3. Pushes values into CSS custom properties on `document.documentElement`.
4. Injects `custom_css` into a `<style id="waibao-whitelabel-custom-css">` tag.
5. Updates `<link rel="icon">` and `document.title`.
6. Exposes a `useWhiteLabel()` hook so any component can read the live
   branding (e.g. for an email-preview page).

Consume the variables anywhere with either Tailwind utility classes
(`brand-bg-primary`, `brand-text-accent` from `styles/whitelabel.css`)
or directly via `style={{ color: 'var(--color-primary)' }}`.

---

## 5. Email + PDF rendering

The same `Branding` record is consumed by:

* **Transactional email** — `render_email_html()` produces a fully
  styled HTML doc with a header band in the customer's primary color,
  the customer's logo (or product name), and a footer with the support
  email + optional powered-by line.
* **PDF reports** — `render_pdf_report_brand()` returns a metadata
  dictionary that WeasyPrint / wkhtmltopdf / ReportLab can use to set
  the page header, footer, and primary colour swatch.

Templates:

| `email_template` value | Use case                                |
|------------------------|------------------------------------------|
| `transactional`        | verification codes / system notifications |
| `marketing`            | newsletter / nurture campaigns            |
| `report`               | weekly digests / funnel reports            |
| `interview_invite`     | calendar invite / reminder                 |
| `offer_letter`         | offer notification                         |

---

## 6. Private deployment topology

Three packaging options live in `infra/private-deployment/`:

### 6.1 Docker Compose (`docker-compose.yml`)

Single-host, single-command install. Use for:

* Demo / PoC
* Customer pilots (< 100 active users)
* On-premise where K8s isn't available

Pulls:

* `waibao/backend:v7.0.0`
* `waibao/frontend:v7.0.0`
* `supabase/postgres`, `supabase/gotrue`, `supabase/storage-api`
* `clickhouse/clickhouse-server:24.3`
* `qdrant/qdrant:v1.7.4`
* `redis:7.2-alpine`
* `caddy:2.7`

See `infra/private-deployment/OPERATIONS_MANUAL.md` for upgrade /
backup / scale procedures.

### 6.2 Helm chart (`helm/waibao/`)

Production-grade K8s install. Use for:

* Customers running their own EKS / AKS / GKE / Rancher cluster
* Multi-tenant deployments with > 1000 users

Highlights:

* `whitelabel` block at the top of `values.yaml` seeds branding at boot.
* `ingress` block points at `nginx-ingress` + cert-manager.
* `secrets.create=false` by default — pre-create via kubectl for prod.
* HPA + PDB + PodSecurityContext baked in.
* ServiceMonitor for Prometheus Operator.

### 6.3 Terraform (`terraform/main.tf`)

Reference architecture for AWS. Provisions:

* VPC (3 AZs, public/private/database subnets)
* EKS cluster (k8s 1.29, managed node groups, 4 add-ons)
* RDS Postgres with PITR (14 days)
* ElastiCache Redis
* S3 buckets (uploads) with versioning + public-access block
* ACM cert + Route53 record
* ALB
* ECR repos for backend + frontend

The `whitelabel_config` output is the exact block you copy-paste into
`helm/waibao/values.yaml`.

---

## 7. End-to-end onboarding flow

```
Day 0: Sales closes deal
       ├─ CS creates tenant row + Stripe subscription
       └─ Eng spins up infra (terraform apply)

Day 1: Customer DevOps
       ├─ terraform output helm_install_command  → kubectl apply
       ├─ Edit helm values.whitelabel{...}        (logo, color, email)
       └─ Verify: curl https://hire.example.com/admin/whitelabel

Day 2: Customer admin
       ├─ Configure SSO via /admin/sso
       ├─ Invite first hiring managers
       └─ Optional: bulk-import 10k candidates via /admin/data-import

Day 3+: Customer DevOps
       └─ Follow OPERATIONS_MANUAL.md day-2 ops (backup, scale, rotate)
```

---

## 8. Testing

* Backend: `tests/test_whitelabel.py` covers validation, CRUD,
  caching, email/PDF rendering, audit log, default fallbacks, and
  the FastAPI surface. ~50 tests, fully offline.
* Frontend: vitest tests for `lib/theme.ts` cover `to_css_variables`,
  `applyCssVariables`, `resolveTenantId`, and `applyBranding`.
* Storybook: `WhiteLabelProvider.stories.tsx` exercises the
  default + a customer-themed variant.

---

## 9. Security + compliance notes

* Branding overrides are *non-privileged* — they change visuals, not
  authentication. SSO/SAML remains the source of identity.
* `custom_css` is sanitised at the API layer (no `<script>`, max 8 KiB).
* All admin mutations emit an audit event (`tenant_branding_audit` +
  EventBus `whitelabel.branding.updated`).
* Logos are loaded over https only — no mixed-content warnings.
* The default CSP allows `'unsafe-inline'` for `style-src` so customer
  custom CSS works; admins can tighten this in Caddy / ingress if
  needed.

---

## 10. Roadmap

* v7.1 — per-page branding overrides (e.g. corporate blog can differ
  from app dashboard).
* v7.2 — localisation bundles per tenant.
* v8.0 — fully server-rendered theme for SEO-critical landing pages
  (currently the provider runs on the client; SSR will pre-paint CSS
  variables to avoid FOUC).
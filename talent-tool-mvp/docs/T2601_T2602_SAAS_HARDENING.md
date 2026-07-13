# T2601 + T2602 — Strict Multi-Tenant Isolation + Rate Limiting

> v7.0 SaaS hardening.  Two together: per-tenant isolation (authz) and
> per-tenant usage quotas (rate).

## What's New

| Layer | Component | Purpose |
|------|-----------|---------|
| DB | `migrations/046_tenant_context.sql` | Adds `tenant_id` + RLS policies + `set_tenant_context()` helper to every business table. |
| Backend | `services/platform/tenant_context.py` | `TenantContext` dataclass + `contextvars` binding. |
| Backend | `services/platform/tenant_resolver.py` | Resolve tenant from JWT > header > cookie. |
| Backend | `services/platform/rate_limiter.py` | slowapi singleton + 429 handler + middleware installer. |
| Backend | `services/platform/quota.py` | Free / Pro / Enterprise plans + counter store. |
| Backend | `setup.py` | Install tenant+quota middleware + slowapi middleware. |
| Frontend | `hooks/use-rate-limit.ts` | Read rate-limit headers, expose snapshot for UI. |
| Tests | `tests/test_tenant_isolation.py`, `tests/test_rate_limiter.py`, `tests/test_quota.py` | 60+ tests in total. |

---

## T2601 — Multi-Tenant Isolation

### Resolution priority

1. JWT `tenant_id` claim (most trusted — signed by Supabase)
2. `X-Tenant-ID` request header (browser override / SDK)
3. `waibao_tenant` cookie (legacy session storage)

```python
from services.platform.tenant_resolver import get_tenant_context_dep

@app.get("/api/foo")
def foo(ctx: TenantContext = Depends(get_tenant_context_dep)):
    return {"tenant": str(ctx.tenant_id), "plan": ctx.plan}
```

### Database enforcement (Supabase / Postgres)

`migrations/046_tenant_context.sql` is idempotent:

* Adds `tenant_id uuid` to every business table (if missing).
* Back-fills from `organisation_id` so existing rows still work.
* Enables + **forces** `ROW LEVEL SECURITY`.
* Defines policy `tenant_isolation` comparing `tenant_id` to the
  session-local GUC `app.tenant_id`.
* Trigger `trg_tenant_id` rejects inserts whose `tenant_id` ≠
  `current_setting('app.tenant_id')` — the only escape hatch is service_role
  or an explicit `set_tenant_context(tid, bypass=true)` call for admin tooling.

### Run the migration

```bash
psql "$DATABASE_URL" -f supabase/migrations/046_tenant_context.sql
```

Verify with:

```sql
SELECT tablename, rowsecurity
FROM pg_tables WHERE schemaname='public' AND rowsecurity = true
ORDER BY tablename;
```

---

## T2602 — Rate Limiting + Quotas

### Plan table

| Plan        | req / min | req / day | ai tokens / month | storage | seats |
|-------------|-----------|-----------|-------------------|---------|-------|
| free        | 100       | 20 000    | 200 000           | 2 GB    | 3     |
| pro         | 1 000     | 200 000   | 2 000 000         | 50 GB   | 25    |
| enterprise  | 10 000    | 2 000 000 | 20 000 000        | 500 GB  | 500   |

### How a request is enforced

```
HTTP request
  ↓
CORS / logging middleware
  ↓
tenant_and_quota_middleware  (resolves tenant, enforces per-tenant quota)
  ↓
slowapi SlowAPIMiddleware    (per-route decorator limits if declared)
  ↓
API route handler
```

When a tenant exceeds budget the request short-circuits with:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 100
Content-Type: application/json

{
  "detail": "Rate limit exceeded (tenant quota)",
  "retry_after_seconds": 60,
  "path": "/api/foo"
}
```

### Backend usage

```python
from fastapi import Depends, FastAPI
from services.platform.tenant_resolver import get_tenant_context_dep
from services.platform.quota import enforce_resource

app = FastAPI()

@app.post("/api/llm/ask")
def ask(prompt: str, ctx: TenantContext = Depends(get_tenant_context_dep)):
    if not enforce_resource(ctx.tenant_id, "ai_tokens", delta=2000):
        raise HTTPException(status_code=429, detail="Plan token limit reached")
    ...
```

Per-route optional:

```python
from services.platform.rate_limiter import per_route_limit

@app.get("/api/heavy")
@per_route_limit("10/minute")
def heavy():
    ...
```

### Redis-backed storage

Set `REDIS_URL=redis://...` to share counters across replicas:

```python
# automatically picked up by get_limiter()
```

The in-memory fallback is used in tests and single-replica dev.

### Frontend usage

```tsx
"use client";
import { useRateLimit } from "@/hooks/use-rate-limit";

export function QuotaBanner() {
  const rl = useRateLimit();
  if (rl.isExhausted) {
    return <UpgradeCta plan={rl.plan} retryIn={rl.retryAfterSeconds} />;
  }
  if (rl.isWarning) {
    return <Banner tone="warn">Approaching rate limit ({rl.remaining}/{rl.limit})</Banner>;
  }
  return null;
}
```

The hook transparently wraps `window.fetch` and reads the rate-limit +
plan headers echoed by the backend.

---

## Running the tests

```bash
cd backend
python -m pytest ../tests/test_tenant_isolation.py ../tests/test_rate_limiter.py ../tests/test_quota.py -v
```

Expected: **63 tests pass**, including:

* Cross-tenant API access → 403
* 100 concurrent tenant contexts do not leak
* Per-minute bucket overflow → 429
* Plan hierarchy (Free < Pro < Enterprise)
* Token-tracking enforces monthly caps
* slowapi limiter singleton + middleware presence
* 429 JSON body + Retry-After + X-RateLimit-Limit

The DB-level RLS behaviour should be verified against a real Supabase
instance:

```bash
psql "$DATABASE_URL" -c "
  BEGIN;
  SELECT public.set_tenant_context('00000000-0000-0000-0000-000000000001');
  SELECT count(*) FROM candidates;   -- should only see tenant 1 rows
  COMMIT;
"
```

# Service Toggle Spec (v8.0)

> Status: **stable** (since v8.0.0)
> Owners: @platform-team
> Last updated: 2026-07-13

## 1. Why Service Toggle

In v6/v7, services were controlled by scattered `FeatureFlag` and hard-coded env vars. This made it impossible to:
- Roll out / roll back a service to all users in 1 click
- Provide different service levels to different customers (plan / org / role)
- Diagnose "why is this service not working for me?" in production

v8.0 introduces a **centralized Service Toggle** layer that sits between any service implementation and the public API.

## 2. Core Abstractions

### 2.1 Service
A logical capability offered by the platform. Examples: `ai_interview`, `matching`, `bias_detector`, `weekly_report`, `feedback_widget`.

### 2.2 ServiceStatus
- `enabled` — service is available to all eligible users
- `disabled` — service is hidden and 404'd
- `beta` — service is opt-in via explicit subscription
- `maintenance` — service is temporarily unavailable (returns 503 with reason)
- `deprecated` — service still works but is scheduled for removal (UI shows warning)

### 2.3 PlanTier
- `free`, `starter`, `growth`, `enterprise`, `internal`

### 2.4 Override dimensions (highest priority first)
1. **Global** status (admin toggle)
2. **Plan** requirement (e.g. `ai_interview` requires `growth+`)
3. **Per-org** override (allow/block a specific tenant)
4. **Per-role** override (e.g. admin can access even if plan doesn't allow)
5. **Default rule** (cohort, region, custom JSONLogic)

## 3. API surface

### 3.1 Public catalog (read)
- `GET /api/services` — list all services, current user
- `GET /api/services/{name}` — detail + current access decision + reason

### 3.2 Admin (write)
- `GET  /api/admin/services` — list + status + overrides
- `POST /api/admin/services` — register new service
- `PATCH /api/admin/services/{name}` — change status / plan / role
- `POST /api/admin/services/{name}/rollback` — revert to previous state
- `GET  /api/admin/services/{name}/audit` — full change history
- `GET  /api/admin/services/dependencies` — graph

### 3.3 Server-side guard
```python
from services.platform.feature_access import check_service_access

@router.post("/api/ai-interview/start")
async def start(
    user: CurrentUser = Depends(get_current_user),
    _guard=Depends(check_service_access("ai_interview")),
): ...
```

## 4. Frontend

```tsx
import { FeatureGate } from "@/components/FeatureGate";
import { useServiceAccess } from "@/hooks/use-service-toggle";

function InterviewPage() {
  const { allowed, reason } = useServiceAccess("ai_interview");
  if (!allowed) return <UpgradePrompt reason={reason} />;
  return <FeatureGate service="ai_interview"><InterviewUI /></FeatureGate>;
}
```

## 5. Storage

- `services` — service registry (name, status, plan, role, deps)
- `service_overrides` — per-org / per-role overrides
- `service_audit` — every change (who, what, when, before, after)

All in Supabase, RLS-protected (org_id from JWT).

## 6. Cache

- 60s TTL
- Redis primary, in-memory LRU fallback
- Key: `svc:access:{user_id}:{service_name}`
- Cache invalidated on:
  - service registry change
  - override add/remove
  - manual `cache_invalidate(service_name)`

## 7. Rollback

`POST /api/admin/services/{name}/rollback` reverts to the state captured in the most recent `service_audit` row. Multi-step rollback supported via `?steps=N`.

## 8. Observability

- EventBus event `service.changed` on every mutation
- Prometheus: `service_access_total{service, decision}`
- Sentry breadcrumb: every 4xx access denial
- Weekly auto report (T3901) includes service usage + denial rate

## 9. Testing

- 50+ unit tests (`test_service_toggle.py`)
- 30+ feature access tests (`test_feature_access.py`)
- 20+ catalog tests (`test_service_catalog.py`)
- 10+ end-to-end (close → 404 → frontend hidden)

## 10. Migration

- All 65+ critical APIs in v8.0 have `Depends(check_service_access)` wired
- Legacy `FeatureFlag.is_enabled` calls are kept as a secondary signal
- ConfigCenter (`backend/services/platform/config_service.py`) reads from `services` table when present, falls back to env vars

## 11. Roadmap

- v8.1: Service-level metrics (calls/sec, p99 latency per service)
- v8.2: Service-level cost tracking (LLM token usage / API cost)
- v9.0: Auto-rollback on error rate spike (anomaly-driven)

# Service Toggle vs Feature Flag vs Config Center — when to use which

v8.0 ships three orthogonal control planes that decide whether a user can do
something at runtime. They are layered, complementary, and not interchangeable.
This document explains the boundary, the priority order, and concrete examples
for each.

## TL;DR decision tree

```
Need to gate access?
├── Need to take the whole service offline (one switch for everyone)?
│   └── Service Toggle        — admin → Disable "matching.engine"
├── Need to roll out gradually (10% → 50% → 100%)?
│   └── Feature Flag          — admin → rollout_percent = 10
└── Need to tune a runtime parameter per tenant (timeout, threshold)?
    └── Config Center         — admin → set "matching.engine.timeout_ms" = 250
```

The `feature_access.check()` helper composes all three in fixed order
(Config → Toggle → Flag). Any single layer can deny the request.

## Layer 1 — Config Center (most fine-grained)

* **Unit:** typed key/value (bool, int, float, str, JSON)
* **Granularity:** per-tenant override + global default
* **Lifetime:** persistent, edited by ops via `/admin/config`
* **Cache TTL:** 60 s (Redis), in-process fallback

When to use:

* Adjusting thresholds (`matching.score_threshold`)
* Tuning timeouts (`api.ai_interview.timeout_ms`)
* Kill-switching a specific integration at runtime

```python
from services.platform.config_service import get as cfg_get
cfg_get("matching.engine", "score_threshold", default=0.7)
```

## Layer 2 — Service Toggle (coarse)

* **Unit:** whole service
* **Granularity:** plan + role + per-org override
* **Lifetime:** persistent, edited via `/admin/services`
* **Cache TTL:** 60 s

When to use:

* Taking a service offline (`disabled`)
* Gating a feature behind `pro` or `enterprise`
* Allowing one beta customer to test before the public release
* Rolling back a broken release with one click

```python
from services.platform.service_toggle import service_toggle
service_toggle.disable("agent.career_planner", reason="bug hunt")
service_toggle.rollback("agent.career_planner")
```

## Layer 3 — Feature Flag (rolling out)

* **Unit:** named flag
* **Granularity:** percentage rollout + cohort rules + per-user/org override
* **Lifetime:** persistent, edited via `/admin/feature-flags`
* **Cache TTL:** 60 s

When to use:

* Canary releases (10% of traffic gets the new flow)
* A/B experiments
* Per-customer early access
* Temporary seasonal toggles (e.g. holiday banner)

```python
from services.platform.feature_flag import is_enabled
if is_enabled("new_matching_algo", user_id=u.id, org_id=u.org_id):
    return run_v2(...)
```

## How they interact — priority

`feature_access.check()` evaluates layers in **reverse priority order**:

1. **Config Center** may explicitly block by tenant (`org_id:name => false`)
2. **Service Toggle** must say the service is enabled (status + plan + role)
3. **Feature Flag** named after the service must be enabled for this user

If any layer returns False the whole check returns False. There is no way for
a lower layer to override an upper one — disabled wins.

This is enforced in `services/platform/feature_access.py`. Endpoint authors
should attach `Depends(check_service_access(name))` rather than calling layers
individually.

## Comparison matrix

| Dimension        | Config Center           | Service Toggle          | Feature Flag            |
|------------------|-------------------------|-------------------------|-------------------------|
| What it controls | Parameter value         | Whole service           | Single feature / cohort |
| Granularity      | Per key                 | Per service             | Per flag                |
| UI               | `/admin/config`         | `/admin/services`       | `/admin/feature-flags`  |
| Persistence      | Supabase `config_kv`    | Supabase `services`     | Supabase `feature_flags`|
| Plan gating      | No (manual)             | Yes (plan_required)     | No (manual)             |
| Rollout %        | No                      | No                      | Yes                     |
| Override expiry  | No                      | Yes (expires_at)        | Yes (expires_at)        |
| When to delete   | Never (small KV)        | When service deprecated | When experiment done    |
| Cache key        | `cfg:<ns>:<key>`        | `service_toggle:...`    | `feature_flag:...`      |

## Anti-patterns

| Anti-pattern                                    | Use instead                        |
|-------------------------------------------------|------------------------------------|
| Disable service for one org via Toggle override | Use Config Center (`org_id:name`)  |
| Use Flag to toggle entire service on/off        | Use Service Toggle                 |
| Use Toggle to limit 1% rollout                  | Use Feature Flag                   |
| Use Config to hide a button                     | Use Feature Flag (with rollout)    |

## When in doubt

Ask three questions:

1. Is the *whole* service broken or not yet ready? → **Service Toggle**
2. Do I want to expose this to a subset gradually? → **Feature Flag**
3. Am I tweaking a number/threshold per tenant? → **Config Center**

When still in doubt, pick the *coarsest* layer that solves the problem — the
finer ones can layer on top later without code changes.

## Reference

- `backend/services/platform/feature_access.py` — `check()` / `require()` / `check_service_access`
- `backend/api/public_services.py` — public catalog exposing toggle state
- `frontend/components/FeatureGate.tsx` — React wrapper for the 3-layer check
- `backend/services/platform/service_toggle.py` — Toggle implementation
- `backend/services/platform/feature_flag.py` — Flag implementation
- `backend/services/platform/config_service.py` — Config Center implementation
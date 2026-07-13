# API Versioning — T2904

RecruitTech ships two parallel API surfaces under versioned prefixes. This
document explains the routing model, deprecation headers, SDK migration and
how the developer portal maps onto the same scheme.

> **TL;DR**
> * Recommended: `/api/v2/*` (add headers `X-API-Version: v2`).
> * Legacy `/api/<x>` continues to work — middleware 308s it to `/api/v1/<x>`.
> * v1 returns the `Sunset`, `Deprecation` and `X-API-Deprecated` headers
>   pointing at v2 as the successor.
> * v2 has a runtime discovery endpoint: `GET /api/v2/version`.

---

## 1. Versions registered

| Version | Status     | Sunset (UTC)          | Successor | Notes                                |
|---------|------------|------------------------|-----------|--------------------------------------|
| v1      | deprecated | 2027-01-01T00:00:00Z   | v2        | all current routers mounted at `/api/v1` |
| v2      | current    | —                      | v2        | re-exported v2 modules + new surfaces |

The single source of truth is `backend/api/versioning.py:VERSION_REGISTRY`.

## 2. Endpoint surface

```
/api/health                  # never-redirected system probe
/api/v1/candidates           # canonical v1 (deprecated)
/api/v2/candidates           # recommended v2
/api/v2/version              # discovery endpoint
/api/developer/...           # self-versioned Developer Portal (T2902)
```

Legacy paths of the form `/api/<path>` are matched against
`NEVER_REDIRECT_PREFIXES` (segment-aware). Everything else 308-redirects to
`/api/v1/<path>`. Examples:

```bash
$ curl -i https://api.recruittech.com/api/candidates/foo
HTTP/1.1 308 Permanent Redirect
location: /api/v1/candidates/foo
x-api-version: v1
x-api-deprecated: true
sunset: 2027-01-01T00:00:00Z
link: </api/v2>; rel="successor-version"
```

## 3. Deprecation headers (RFC 8594 / RFC 9745)

Every response served from a deprecated version carries:

| Header                    | Example                              | Purpose                                   |
|---------------------------|--------------------------------------|-------------------------------------------|
| `X-API-Version`           | `v1`                                 | Backing version.                          |
| `X-API-Deprecated`        | `true`                               | Boolean on/off for monitoring tools.       |
| `Deprecation`            | `true`                               | RFC 9745 signal for generic tooling.       |
| `Sunset`                  | `2027-01-01T00:00:00Z`               | RFC 8594 sunset date.                      |
| `Link`                    | `</api/v2>; rel="successor-version"` | Linked successor.                          |
| `X-API-Successor-Version` | `v2`                                 | Convenience for non-Link-aware clients.    |

## 4. Frontend client

* `lib/api-v2.ts` — preferred. Targets `/api/v2/*`.
* `lib/api-v1.ts` — kept for backward compatibility; logs a `console.warn`
  on first use and surfaces a `:class:` ``DeprecatedVersionBanner`` in any
  component that still uses it.
* `lib/api-versioning.ts` — shared constants (sunset date, version policy).
* `components/VersionSwitcher.tsx` — drop-in banner that automatically
  fetches `/api/v2/version` to render the live sunset date.

## 5. SDK auto-generation

Run `scripts/generate_sdk.sh` to regenerate the OpenAPI-derived SDKs
(Python / TypeScript / Go) and publish them to GitHub Releases.

```bash
./scripts/generate_sdk.sh --upload v3.0.0
```

The generated SDKs are pinned to **v2** by default.

## 6. Migration cookbook

```ts
// Old (deprecated)
import { apiV1 } from "@/lib/api-v1";
const c = await apiV1.fetch("/candidates");

// New (recommended)
import apiV2 from "@/lib/api-v2";
const c = await apiV2.fetch("/candidates");
```

To roll a new endpoint on v2 only:

```python
# backend/api/v2/foo.py
router = APIRouter()
@router.post("/foo")
async def new_foo(): ...
```

The endpoint will be mounted under `/api/v2/foo` automatically by
``api.versioning.install_versioning(app)``.

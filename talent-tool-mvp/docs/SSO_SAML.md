# T2901 — SSO / SAML (Authlib + NextAuth + Keycloak)

## What

Enterprise single sign-on. Six identity providers, two protocols,
one backend, one frontend.

| IdP                  | Protocol   | Vendor         |
|----------------------|------------|----------------|
| Okta                 | SAML 2.0   | python3-saml   |
| Microsoft Entra ID   | OIDC       | authlib        |
| Google Workspace     | OIDC       | authlib        |
| DingTalk (钉钉)       | OIDC       | authlib        |
| Feishu (飞书)         | OIDC       | authlib        |
| WeCom (企业微信)       | OIDC       | authlib        |

Frontend: **NextAuth.js** (Auth.js v5) with a dynamic provider list
sourced from the backend.

IdP: **Keycloak** (self-hosted) as the federation broker — the realm
`RecruitTechSSO` is bootstrapped via `infra/keycloak/realm-export.json`.

## Architecture

```
Browser  ─►  NextAuth (frontend)  ─►  /api/auth/sso/{provider}/login
                                              │
                                              ▼
                                       backend (FastAPI)
                                       ├─ providers.py  (registry of 6)
                                       ├─ sso.py        (SAML + OIDC)
                                       ├─ jit.py        (provisioning)
                                       └─ session.py    (JWT + refresh)
                                              │
                       ┌──────────────────────┴────────────────────┐
                       ▼                                           ▼
            python3-saml  /  authlib                       Keycloak (IdP)
            (SAML SP)     (OIDC RP)                         (federation)
```

## Session model

* **Access token** — short JWT (15 min), claims: `sub`, `email`,
  `provider`, `role`, `organisation_id`, `iss=waibao-sso`. Signed HS256.
* **Refresh token** — opaque 48-byte URL-safe string, 30 d TTL, stored
  in a thread-safe in-process map (production: Redis). Rotated on every
  use (defence against token theft).
* Both delivered as HttpOnly cookies (`at` / `rt`) and echoed in the
  JSON body so SPAs can use either transport.

## JIT provisioning

* First login via any IdP creates a `users` row.
* A default organisation is created on demand and the user is added as
  `member`.
* Existing users with the same email are linked automatically.
* Subsequent logins refresh the profile (display name, picture, groups)
  but do **not** create duplicate rows.

## Run

```bash
# 1) Backend
pip install -r requirements.txt  # adds authlib + python3-saml
cd backend && uvicorn main:app --reload --port 8000

# 2) Keycloak (optional — only needed for the full IdP-federation flow)
docker compose -f infra/keycloak/docker-compose.yml up -d

# 3) Frontend
cd frontend && npm install       # adds next-auth
npm run dev
```

## Endpoints

| Method | Path                                | Description                          |
|--------|-------------------------------------|--------------------------------------|
| GET    | `/api/auth/sso/providers`           | List enabled IdPs (no secrets)       |
| GET    | `/api/auth/sso/{provider}/login`    | Begin SSO flow                       |
| GET    | `/api/auth/sso/{provider}/redirect` | 302 redirect straight to IdP         |
| POST   | `/api/auth/sso/{provider}/callback` | IdP posts the user back              |
| POST   | `/api/auth/sso/refresh`             | Rotate access token                  |
| POST   | `/api/auth/sso/logout`              | Revoke refresh token                  |
| GET    | `/api/auth/sso/me`                  | Current session info                 |

## Tests

```bash
python -m pytest tests/test_sso.py -v
# 57 passed
```

Coverage:

* Provider registry (6 IdPs, all metadata paths)
* SAML request building + response parsing
* OIDC id_token claim parsing + verification
* JIT provisioner (create / link / re-link)
* Session manager (create / refresh rotation / revoke)
* Full FastAPI route surface (login / callback / refresh / me / logout)
* End-to-end SAML → JIT → session → refresh → logout

## Files

* `backend/services/auth/__init__.py`
* `backend/services/auth/providers.py`
* `backend/services/auth/sso.py`
* `backend/services/auth/session.py`
* `backend/services/auth/jit.py`
* `backend/api/auth_sso.py`
* `tests/test_sso.py` (57 tests)
* `infra/keycloak/docker-compose.yml`
* `infra/keycloak/realm-export.json`
* `frontend/lib/auth-sso.ts`
* `frontend/components/auth/SSOButton.tsx`
* `frontend/components/auth/SSOButtonGroup.tsx`
* `frontend/app/auth/sso-callback/page.tsx`
* `frontend/app/login/page.tsx` (SSO integrated)

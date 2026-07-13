# T2901 — Keycloak (self-hosted IdP)

Self-hosted Keycloak 26.x used as the enterprise IdP for the
`RecruitTechSSO` realm. Keycloak federates **6 upstream identity
providers** so the application only needs to talk OIDC/SAML to *one*
endpoint.

## Services

| Service   | Port | Notes |
|-----------|------|-------|
| Keycloak  | 8080 (HTTP) / 8443 (HTTPS) | Quarkus distribution |
| Postgres  | 5432 (internal) | Keycloak's storage |

## Quick start

```bash
docker compose -f infra/keycloak/docker-compose.yml up -d
# wait ~30s for Keycloak to start
open http://localhost:8080/admin
# admin / admin
```

The realm configuration is imported from `realm-export.json` on first
boot via `KC_IMPORT`.

## Federated IdPs (6)

| Alias      | Display name           | Protocol | Vendor config |
|------------|------------------------|----------|---------------|
| `okta`     | Okta                   | SAML 2.0 | `OKTA_*` envs |
| `azure-ad` | Microsoft Entra ID     | OIDC     | `AZURE_*` envs |
| `google`   | Google Workspace       | OIDC     | `GOOGLE_*` envs |
| `dingtalk` | DingTalk (钉钉)        | OIDC     | `DINGTALK_*` envs |
| `feishu`   | Feishu (飞书)          | OIDC     | `FEISHU_*` envs |
| `wecom`    | WeCom (企业微信)        | OIDC     | `WECOM_*` envs |

Each IdP is enabled by default but can be flipped off in the realm
admin console under **Identity Providers**.

## Token lifetimes

| Token                | TTL    |
|----------------------|--------|
| Access token (JWT)   | 15 min |
| SSO session (idle)   | 30 min |
| Refresh token        | 30 d   |

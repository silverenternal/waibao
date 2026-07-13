# Instatus Self-Hosted Status Page

Public status page deployed on **status.waibao.cn**, backed by the open-source
[Instatus Open Status Page](https://github.com/instatushq/Open-Status-Page)
container.

## Five monitored services

| Key      | Display name                          |
|----------|---------------------------------------|
| api      | Public API & Authentication           |
| llm      | LLM Inference (multi-provider)        |
| storage  | Object Storage & File Uploads         |
| webhook  | Outbound Webhooks & Integrations      |
| database | Primary Database (Postgres+Supabase)  |

These map exactly to `services.platform.sla_monitor.PLATFORM_SERVICES`.

## How syncing works

1. The backend SLA monitor (`backend/services/platform/sla_monitor.py`) is the
   single source of truth — uptime, P95 latency, error rate, target uptime.
2. A lightweight cron (typically every 60 seconds) calls
   `GET /api/admin/sla/30d` and pushes the response into the status page via
   the Instatus `POST /api/sync` endpoint. The bridge container in
   `docker-compose.yml` is the recommended runtime.
3. The status page surfaces both realtime state and 90-day history.
4. Subscribers (email / webhook) are managed inside Instatus itself; see
   `docs/STATUS_PAGE.md` for the operator runbook.

## Local dev

```bash
docker compose -f infra/instatus/docker-compose.yml --env-file .env up -d
```

Environment variables (in `.env`):

```
STATUS_PAGE_AUTH_SECRET=...
STATUS_PAGE_ENCRYPTION_KEY=...
STATUS_PAGE_SYNC_TOKEN=...
```

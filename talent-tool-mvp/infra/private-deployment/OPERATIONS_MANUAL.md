# Waibao Private Deployment — Customer Operations Manual

> v7.0 T3003 — Audience: customer DevOps / SRE who run a self-hosted Waibao stack.

This manual covers the four day-2 operations you will perform most often:
upgrade, backup/restore, scale, and rotate secrets. It assumes the stack
was installed via `infra/private-deployment/docker-compose.yml` or the
`helm/waibao` chart — pick the right column for each task.

---

## 1. Upgrade

### Docker Compose

```bash
# 1. Pull new images
docker compose -f infra/private-deployment/docker-compose.yml pull

# 2. Apply DB migrations
docker compose -f infra/private-deployment/docker-compose.yml run --rm backend \
    python -m alembic upgrade head

# 3. Restart with new images (zero-downtime if you front with a LB)
docker compose -f infra/private-deployment/docker-compose.yml up -d

# 4. Smoke
curl -fsS https://hire.example.com/health
```

### Helm

```bash
helm repo update waibao
helm upgrade waibao waibao/waibao \
    --version 7.0.0 \
    --reuse-values \
    --set image.backend.tag=v7.0.0 \
    --set image.frontend.tag=v7.0.0

kubectl rollout status deploy/waibao-backend
kubectl rollout status deploy/waibao-frontend
```

---

## 2. Backup & Restore

### Postgres (RDS or supabase-db)

```bash
# Manual snapshot (RDS)
aws rds create-db-snapshot \
    --db-instance-identifier waibao-acme-db \
    --db-snapshot-identifier waibao-acme-$(date +%F)

# Logical dump (for compose)
docker compose exec supabase-db pg_dump -U postgres -Fc postgres > backup.dump

# Restore
docker compose exec -T supabase-db pg_restore -U postgres -d postgres < backup.dump
```

RDS has PITR enabled with a 14-day retention by default (see `aws_db_instance.postgres.backup_retention_period`). To restore to a point in time:

```bash
aws rds restore-db-instance-to-point-in-time \
    --source-db-instance-identifier waibao-acme-db \
    --target-db-instance-identifier waibao-acme-db-restored \
    --restore-time 2026-07-10T03:00:00Z
```

### ClickHouse

```bash
# Full backup
docker compose exec clickhouse \
    clickhouse-backup create --name manual-$(date +%F)

# Restore
docker compose exec clickhouse \
    clickhouse-backup restore --name manual-2026-07-10
```

### Object storage (S3 / supabase-storage)

Enable versioning on the bucket (Terraform does this by default):

```bash
aws s3api put-bucket-versioning \
    --bucket waibao-acme-uploads \
    --versioning-configuration Status=Enabled
```

---

## 3. Scaling

### Docker Compose (single host)

Increase CPU/RAM on the host, then:

```bash
docker compose up -d --scale backend=3 --scale frontend=3
```

For real HA, put the host behind a TCP load balancer (HAProxy / nginx) and run 2-3 hosts with the same compose file (use a shared `postgres` and `redis` on a dedicated DB host).

### Helm / EKS

```bash
# Manual scale
kubectl scale deploy/waibao-backend --replicas=6

# HPA is enabled by default — confirm with:
kubectl get hpa

# EKS node group scale
aws eks update-nodegroup-config \
    --cluster-name waibao-acme-cluster \
    --nodegroup-name main \
    --scaling-config minSize=4,maxSize=20,desiredSize=8
```

---

## 4. Secret rotation

| Secret | File / K8s secret | Rotation frequency |
|---|---|---|
| `SECRET_KEY` (app JWT) | compose `.env` / `waibao-secrets` K8s Secret | every 90 days |
| `POSTGRES_PASSWORD` | RDS console / supabase-db env | every 180 days |
| `SUPABASE_JWT_SECRET` | compose `.env` / K8s Secret | every 180 days |
| LLM provider keys | compose `.env` / External Secrets | every 90 days |

Procedure:

```bash
# 1. Generate new value
NEW=$(openssl rand -base64 48)

# 2. Update K8s secret
kubectl create secret generic waibao-secrets \
    --from-literal=secret-key=$NEW \
    --dry-run=client -o yaml | kubectl apply -f -

# 3. Restart workloads to pick it up
kubectl rollout restart deploy/waibao-backend

# 4. Invalidate old JWTs by bumping JWT_ISSUED_AT epoch
kubectl set env deploy/waibao-backend JWT_ISSUED_AT=$(date +%s)
```

---

## 5. Troubleshooting

| Symptom | Check |
|---|---|
| `502 Bad Gateway` from frontend | `kubectl logs -l app.kubernetes.io/component=backend` for traceback |
| Login fails with 401 | `SUPABASE_JWT_SECRET` matches between `supabase-auth` and `backend` |
| Email not delivered | `SMTP_HOST` reachable from backend container; check `docker logs backend` for SMTP errors |
| RAG returns empty | Qdrant container up? `curl http://qdrant:6333/healthz` |
| BI dashboard 500 | ClickHouse container up? `curl http://clickhouse:8123/ping` |

---

## 6. White-label configuration

All branding is editable at runtime through the admin UI:
`https://hire.example.com/admin/whitelabel`

Required fields:

- **product_name** — shown in browser tab, email subject, PDF header
- **logo_url** — public https URL; PNG/SVG with transparent background recommended
- **primary_color** — hex color (`#RRGGBB`), used for buttons and accents
- **support_email** — shown in email footers and `/support` page

To bulk-set branding at install time, seed the `tenant_branding` table:

```bash
docker compose exec supabase-db psql -U postgres -c "
INSERT INTO public.tenant_branding (tenant_id, product_name, logo_url, primary_color)
VALUES ('default', 'Acme Talent', 'https://cdn.acme.com/logo.svg', '#FF6B35')
ON CONFLICT (tenant_id) DO UPDATE
  SET product_name=EXCLUDED.product_name,
      logo_url=EXCLUDED.logo_url,
      primary_color=EXCLUDED.primary_color;
"
```

---

## 7. Compliance + audit

- **Audit log**: every admin action is recorded in `audit_log_v2` (immutable, 7-year retention).
- **GDPR**: tenants can request data export via `POST /api/gdpr/export`.
- **Backups**: see §2. PITR window is 14 days.
- **TLS**: enforced by Caddy / ingress; min TLS 1.2.

---

## 8. Support escalation

- L1 → your internal IT (this manual)
- L2 → `support@waibao.example.com` (response SLA 4 business hours)
- L3 → 24×7 on-call (contract customers only; see SLA-99.9 plan)

Include in any ticket: tenant_id, deployment version (`helm list` / `docker compose ps`), and a `kubectl describe` / `docker logs` excerpt.
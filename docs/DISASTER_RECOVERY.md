# waibao 灾备手册 (Disaster Recovery)

> **v4.0.0** · RTO ≤ 15 分钟 · RPO ≤ 5 分钟 · **最后更新**: 2026-07-12

---

## 1. 概述

### 1.1 灾备目标

| 指标 | 目标 | 实测 (2026-Q2) |
|---|---|---|
| **RTO** (Recovery Time Objective) | ≤ 15 分钟 | 8 分钟 |
| **RPO** (Recovery Point Objective) | ≤ 5 分钟 | 12 秒 (replica lag 中位数) |
| **可用性 SLA** | 99.9% 月度 | 99.94% (2026-06) |

### 1.2 灾备分级

| 等级 | 描述 | 响应时间 | 触发条件 |
|---|---|---|---|
| **P0** | 全站不可用 / 多区域同时挂 | 5 分钟 | ≥ 2 个区域 5xx > 5% |
| **P1** | 单区域不可用 | 15 分钟 | 1 个区域 5xx > 5% |
| **P2** | 性能严重降级 | 30 分钟 | P95 > 3x 基线 |
| **P3** | 第三方依赖挂 | 1 小时 | Stripe / OpenAI / Zoom |

---

## 2. 备份策略

### 2.1 数据库备份 (PostgreSQL)

| 备份类型 | 频率 | 保留 | 存储位置 |
|---|---|---|---|
| 自动快照 (RDS/Supabase) | 每日 02:00 UTC | 7 天 | 同区 |
| 跨区只读副本 | 实时流复制 | 持续 | 异区 |
| 手动 pg_dump | 按需 | 30 天 | S3 / OSS |
| PITR (Point-In-Time Recovery) | 持续 WAL 归档 | 7 天 | 异区 |
| 季度全量归档 | 季度首日 | 永久 | Glacier / 冷归档 |

### 2.2 文件 / 对象存储

| 区域 | Bucket | 跨区复制 |
|---|---|---|
| region-cn | `waibao-cn-prod` (OSS) | → cn-shanghai (同城灾备) |
| region-sg | `waibao-sg-backups` (S3) | → us-west-1 |
| region-us | `waibao-us-backups` (S3) | → ap-southeast-1 |

### 2.3 配置 / Secret

- K8s Secret: Velero 每日备份 → S3 (加密)
- Terraform state: S3 + DynamoDB 锁 (版本化)
- PII_ENCRYPTION_KEY: 离线冷备份 (2 份, 2 个地理位置)

---

## 3. 恢复流程

### 3.1 单数据库损坏 (P1)

```bash
# 1. SRE 在 PagerDuty ack
# 2. 评估: 是 schema 损坏 / 数据误删 / 实例挂?
# 3. 根据情况选策略:

# 策略 A: PITR (Point-In-Time Recovery) — 数据丢失 < 5 分钟
#   - Supabase: dashboard → Database → Point in time recovery
#   - RDS: aws rds restore-db-instance-to-point-in-time
#   - 选择目标时间 (例如 5 分钟前)
#   - 等待实例创建 (5-10 分钟)
#   - 更新 DNS / 连接串 → 重启 backend

# 策略 B: 手动 pg_dump 恢复 (staging 先验证)
./scripts/restore-prod.sh s3://waibao-cn-backups/manual/2026-07-01/backup.sql \
  --signer1=sre-a --signer2=sre-b --confirm

# 4. 验证数据完整性
psql -c "SELECT count(*) FROM candidates;"
psql -c "SELECT max(created_at) FROM candidates;"

# 5. 通知: "DB restored at <time>, lost <N> minutes of data"
# 6. postmortem (24h 内)
```

### 3.2 单区域整体故障 (P0/P1)

```bash
# 1. PagerDuty 触发 (5xx > 5% 持续 90s)
# 2. ack, 在 Slack #inc 通知

# 3. 自动 / 手动切流
#    - 自动: Cloudflare LB 健康检查失败 ≥3 次 → weight=0
#    - 手动: 通过 Cloudflare API 强制切换

# 切流到备用区域 (例: region-us → region-sg)
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/.../load_balancers/..." \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"default_pools":["sg-primary"],"random_steering":{"pool_weights":{"us-primary":0,"sg-primary":1}}}'

# 国内 (region-cn) — alidns 修改 A 记录
aliyun alidns UpdateDomainRecord --RecordId xxx --Value $BACKUP_SLB_IP

# 4. 监控: 看备用区域 QPS / 错误率
watch -n 5 'curl -fsS https://api.sg.waibao.io/health'

# 5. 通知用户 (status.waibao.io)
# 6. postmortem
```

### 3.3 数据库主库永久丢失 (P0)

```bash
# 1. 切流到其他区域的主库 (跨区)
#    region-us 主库挂 → 切到 region-sg 主库 (Supabase SG)

# 2. 在 SG 区域提升跨区副本为新主库
#    Supabase: dashboard → Database → Promote replica
#    RDS: aws rds promote-read-replica

# 3. 更新所有 backend 的 DATABASE_URL
kubectl create secret generic waibao-us-secrets \
  --from-literal=supabase-url=$NEW_URL \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/waibao-us-backend -n waibao-us

# 4. 重建跨区副本 (在原 US 区域)
terraform apply -target=aws_db_instance.waibao_us_primary

# 5. 验证 + 监控
```

### 3.4 全站灾难 (所有区域挂) (P0)

```bash
# 1. 启用"降级模式"
#    - 仅返回缓存 (Redis snapshot)
#    - 写操作排队 (DB 不可用时入 Kafka)
#    - 用户看到 "服务正在恢复" 页面

# 2. 在新区域启动 (新 AWS 账号 / 新阿里云账号)
terraform apply  # 全新 region
kubectl apply -f infra/region-sg/k8s/  # 起最小副本

# 3. 从 Glacier 拉取最新备份 (PITR)
# 4. 恢复数据
# 5. 启动 + 切流

# RTO 目标: 60 分钟 (P0)
# RPO 目标: 1 小时 (灾难恢复级别, 接受更多数据丢失)
```

---

## 4. 演练计划

### 4.1 季度演练 (必做)

| 季度 | 演练场景 | 负责人 |
|---|---|---|
| Q1 | region-cn 主库挂 → PITR | 数据工程师 |
| Q2 | region-us 整区挂 → 切到 region-sg | SRE |
| Q3 | region-sg 整区挂 → 切到 region-us | SRE |
| Q4 | DNS 劫持 → 强制 GeoDNS 重路由 | SRE |

### 4.2 演练步骤

```bash
# 1. Slack #inc: "开始 Q2 DR drill"
# 2. 在测试环境模拟故障 (不要直接动生产)
#    - Terraform 临时把 region-us 主 LB weight=0
#    - 或 stop ALB
# 3. 验证自动 / 手动切流
watch -n 5 'curl -fsS https://api.us.waibao.io/health 2>&1 || echo FAILED'

# 4. 跑 smoke test 验证业务
./scripts/smoke_test.sh --region=us --via=sg

# 5. 记录 RTO / RPO
#    RTO = 故障到 100% 流量恢复
#    RPO = replica lag 中位数

# 6. 还原 + 写 postmortem
```

---

## 5. 演练历史

| 日期 | 演练 | RTO 实测 | RPO 实测 | postmortem |
|---|---|---|---|---|
| 2026-Q1 | cn 主库 PITR | 12 min | 2 min | #inc-2026-001 |
| 2026-Q2 | us → sg 切流 | 8 min | 12 s | #inc-2026-014 |
| 2026-Q3 | (待定) | | | |
| 2026-Q4 | (待定) | | | |

---

## 6. 关联文档

- [MULTI_REGION.md](MULTI_REGION.md) — 多区域架构
- [RUNBOOK.md](RUNBOOK.md) — 运维手册
- [DEPLOYMENT.md](DEPLOYMENT.md) — 部署指南
- [PERFORMANCE.md](PERFORMANCE.md) §7.4 — 备份恢复性能

---

**维护**: SRE team (`sre@waibao.io`)
**变更**: 任何灾备策略变更须 PR + SRE 双签

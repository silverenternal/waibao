# 灾备方案 — Disaster Recovery

**Owner:** SRE / Platform Team
**Last reviewed:** 2026-07-12
**Status:** Active

---

## 1. 目标

| 指标 | 目标 | 当前值 |
|---|---|---|
| **RTO** (Recovery Time Objective) | < 4 小时 | ~30 分钟 (基于 staging 演练) |
| **RPO** (Recovery Point Objective) | < 1 小时 | 默认每日 1 次,关键数据 PITR < 5 分钟 |
| **Availability** (生产) | 99.9% (8.7h 年停机) | 99.95% (FY2025) |
| **Backups per day** | ≥ 1 | 1 (UTC 03:00) + Supabase PITR 持续 |
| **Off-site copies** | ≥ 2 (跨区域) | S3 CRR + OSS 国内 |

---

## 2. 备份策略

### 2.1 PITR (Point-in-Time Recovery)

通过 **Supabase Pro / Team** 计划开启,默认 7 天 retention。

- 启用状态: `infra/monitoring/backup-alerts.yml` 包含 `PITRWindowTooSmall` 告警
- 验证脚本: `python backend/scripts/backup_to_s3.py --verify-only`
- 数据库修改 `pg_settings.wal_level = replica`; Supabase 后台自动启用 WAL archiving
- 启用 Binary CDC 以缩短 RPO: `infra/pg/cdc.cnf` (开发中)

### 2.2 逻辑备份 (每日)

`backend/services/backup.py` 配合 `scripts/backup_to_s3.py`:

- 每日 UTC 03:00 (cron: `0 3 * * *`)
- `pg_dump --format=custom --no-owner` (压缩归档)
- 立即上传到 S3 (`STANDARD_IA`) + 国内 OSS (`IA` / `Archive` / `ColdArchive`)
- 保留策略:S3 30 天 IA + 90 天 Glacier IR;OSS 30 天 IA + 90 天 Archive + 180 天 ColdArchive
- 跨区 CRR:S3 `us-east-1` → `ap-southeast-1`;OSS 国内 → 新加坡

### 2.3 重要数据增强

| 数据 | 备份频率 | 额外措施 |
|---|---|---|
| `users`, `candidates`, `jobs`, `tickets`, `*_audit` | 每日 + PITR | WAL streamed to S3 |
| 文件存储 (S3 / 阿里云 OSS) | 持续 | 跨区复制 + WORM 锁定 1 年 |
| PII 加密密钥 | 每次轮换后 | KMS 自动备份 |
| 日志 (审计) | 流式 (Loki) | 6 个月 retention |

---

## 3. 恢复流程

### 3.1 决策矩阵

| 故障 | 行动 |
|---|---|
| 单实例 / 单 AZ 故障 | 自动迁移 (k8s / 多副本) |
| AZ 级别中断 (但 region 内可用) | DNS 流量切换到健康 AZ (Route53 / DNSPod) |
| Region 级别中断 | 切换到备用 region,执行 `restore_from_s3.py` |
| 数据损坏 | 从最近 PITR + 逻辑备份恢复 |
| 误删 (逻辑性) | 锁定账号, 使用 row-level 时间点恢复 |

### 3.2 RTO 4h 流程

1. **0-15 分钟**:值班 SRE 确认事件,启动 incident bridge
2. **15-60 分钟**:
   - 决策 PITR vs 逻辑备份恢复
   - 执行 `python scripts/disaster_recovery_test.py --apply --bucket waibao-prod-backups`
   - 监控 `pg_restore` 进度 (通常 < 30 分钟,1 TB 实测 ~ 45 分钟)
3. **60-180 分钟**:staging 校验 + 业务 smoke test
4. **180-240 分钟**:DNS 切换 + 上线

### 3.3 命令速查

```bash
# 当前备份状态
PYTHONPATH=backend python backend/scripts/backup_to_s3.py --verify-only

# 手动触发备份
PYTHONPATH=backend python backend/scripts/backup_to_s3.py

# 从 S3 拉取 + 校验 + 准备恢复
PYTHONPATH=backend python backend/scripts/restore_from_s3.py \
    --key postgresql/waibao-20260712T030000Z.dump

# 实际恢复 (会触发 pg_restore)
PYTHONPATH=backend python backend/scripts/restore_from_s3.py \
    --key postgresql/waibao-20260712T030000Z.dump \
    --target-db postgresql://staging-user:pwd@host:5432/restored \
    --execute

# 季度演练
PYTHONPATH=backend python backend/scripts/disaster_recovery_test.py \
    --bucket waibao-prod-backups --apply \
    --target-db postgresql://staging-user:pwd@host:5432/drill
```

---

## 4. 演练计划

### 4.1 频率

每 **季度** (3 个月) 一次全量灾备演练 + 每月一次抽查。

### 4.2 季度演练 checklist

- [ ] 启动 SRE on-call (PagerDuty primary)
- [ ] 创建一个干净的 staging 数据库
- [ ] 执行 DR 演练脚本 (`disaster_recovery_test.py --apply`)
- [ ] 比对 staging 行数 vs 生产 (允许 ±5% 误差)
- [ ] 运行关键 API 冒烟测试
- [ ] 记录 RTO / RPO 测量结果
- [ ] 双签确认演练通过,关闭 incident
- [ ] 在 `/sre/dr-drills/{YYYY-Qn}.md` 中归档报告

### 4.3 报告模板

每次演练必须产出 `sre/dr-drills/2026-Q3.md`,包含:

- 时间窗口 (开始 / 结束 / 关键 timestamp)
- 备份 SHA256 / size
- 实际 RTO / RPO
- 失败点 (如有)
- 改进措施 (fired TODOs)
- 双签:Tech Lead + SRE Lead

---

## 5. 责任人与联系方式

| 角色 | 主责 | 备份 |
|---|---|---|
| **SRE Lead** | 灾备流程 owner | Tech Lead |
| **Database Lead** | Supabase / 备份脚本 | Backend Lead |
| **Tech Lead** | 全栈恢复协调 | SRE Lead |
| **Product** | 业务影响评估 | CTO |

联系方式:

- SRE on-call rotation: PagerDuty schedule `sre-primary`
- 数据库值班: PagerDuty `db-primary`
- 工单系统: `#incident-channel` Slack
- 关键事件升级:在 `#incident-channel` 提 `@incident-commander`

---

## 6. 相关文件

- 备份服务实现: `backend/services/backup.py`
- 备份脚本: `backend/scripts/backup_to_s3.py`、`restore_from_s3.py`、`disaster_recovery_test.py`
- 数据库迁移: `supabase/migrations/`
- 备份基础设施:
  - `infra/backup/s3-lifecycle.yml` (海外 S3 策略)
  - `infra/backup/oss-lifecycle.yml` (国内 OSS 策略)
- 监控告警: `infra/monitoring/backup-alerts.yml`
- Prometheus 指标抓取: `infra/prometheus/prometheus.yml`

---

## 7. 修订历史

| 日期 | 作者 | 变更 |
|---|---|---|
| 2026-07-12 | SRE on-call | 初版 (T1502 实施) |

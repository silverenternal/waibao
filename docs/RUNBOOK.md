# waibao 运维手册 (Runbook)

> **v4.0.0** · 7×24 SRE on-call · **最后更新**: 2026-07-12

---

## 目录

1. [值班与响应](#1-值班与响应)
2. [常见告警处理](#2-常见告警处理)
3. [区域故障切换](#3-区域故障切换)
4. [数据库运维](#4-数据库运维)
5. [K8s 运维](#5-k8s-运维)
6. [应用发布与回滚](#6-应用发布与回滚)
7. [灾备演练](#7-灾备演练)
8. [安全事件响应](#8-安全事件响应)
9. [第三方服务故障](#9-第三方服务故障)
10. [巡检清单](#10-巡检清单)

---

## 1. 值班与响应

### 1.1 值班表

- 排班: PagerDuty schedule `waibao-primary`
- 轮转: 一周一轮 (周一 09:00 交接)
- 升级路径: primary → secondary → manager → CTO

### 1.2 响应时间 (SLO)

| 严重度 | 描述 | 响应 | 解决 |
|---|---|---|---|
| **P1** | 全站不可用 / 数据丢失 | 5 分钟 | 1 小时 |
| **P2** | 单区域 / 核心功能降级 | 15 分钟 | 4 小时 |
| **P3** | 非核心功能 / 性能下降 | 1 小时 | 1 工作日 |
| **P4** | 文档 / 体验问题 | 1 工作日 | 1 周 |

### 1.3 沟通渠道

- **告警**: PagerDuty → 手机 + 钉钉 + Slack
- **事故沟通**: Slack `#inc` (SRE 全员 + on-call 经理)
- **用户通知**: status.waibao.io
- **事后总结**: Notion + GitHub Discussion

---

## 2. 常见告警处理

### 2.1 后端 5xx 错误率 > 1% (P1)

```bash
# 1. 看是哪个区域
kubectl logs -n waibao-{region} -l app=waibao-{region}-backend --tail=200 | grep ERROR

# 2. 检查依赖
curl -fsS https://api.{region}.waibao.{cn|io}/health
psql $DATABASE_URL -c "SELECT 1"
redis-cli -u $REDIS_URL ping

# 3. 若是 DB 问题, 看连接数 / 慢查询
psql -c "SELECT count(*) FROM pg_stat_activity;"
psql -c "SELECT pid, query, state FROM pg_stat_activity WHERE state='active';"

# 4. 若是新版本引入, 回滚
kubectl rollout undo deployment/waibao-{region}-backend -n waibao-{region}
```

### 2.2 健康检查失败 / 区域不可达 (P1)

```bash
# 1. 看 pod 状态
kubectl get pods -n waibao-{region} -l app=waibao-{region}-backend

# 2. 看 events
kubectl describe pod -n waibao-{region} <pod-name>

# 3. 检查 LB / Ingress
kubectl get ingress -n waibao-{region}

# 4. 检查上游依赖 (DB / Redis / OSS)
# 详见 §4 数据库运维
```

### 2.3 LLM Token 超预算 (P2)

```bash
# 1. 看是哪个租户 / 用户
psql -c "SELECT tenant_id, sum(tokens) FROM llm_usage WHERE created_at > NOW() - INTERVAL '1 hour' GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"

# 2. 临时封禁滥用用户
psql -c "UPDATE tenants SET llm_budget_override = 0 WHERE id = '...';"

# 3. 调整全局限流
kubectl set env deployment/waibao-{region}-backend -n waibao-{region} \
  LLM_BUDGET_PER_USER=50000
```

### 2.4 Replica Lag > 60s (P2)

```bash
# 1. 看是哪个副本
psql -h <replica-host> -c "SELECT now() - pg_last_xact_replay_timestamp() AS lag;"

# 2. 检查主库写入压力
psql -c "SELECT count(*) FROM pg_stat_activity WHERE state='active';"

# 3. 检查网络
mtr -rwbzc 100 <replica-host>

# 4. 若是网络问题, 临时切流到其他副本 (region_router)
```

### 2.5 OSS / S3 错误率上升 (P3)

```bash
# 1. 看 Grafana 哪个 bucket
# 2. 检查 IAM / AK 配置
kubectl get secret waibao-{region}-secrets -o jsonpath='{.data.oss-ak}' | base64 -d

# 3. 重试: 应用层有指数退避, 看是否只是抖动
# 4. 切到备用 bucket (terraform apply 切换)
```

---

## 3. 区域故障切换

> 详见 [MULTI_REGION.md](MULTI_REGION.md) §4

### 3.1 自动切换 (推荐)

健康检查失败 ≥ 3 次 → Cloudflare LB 自动把该 region weight=0。

### 3.2 手动切换

```bash
# Cloudflare API (region-us 切到 region-sg)
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/.../load_balancers/..." \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"default_pools":["sg-primary"],"random_steering":{"pool_weights":{"us-primary":0,"sg-primary":1}}}'

# alidns (region-cn 故障切到备用)
aliyun alidns UpdateDomainRecord --RecordId xxx --Value $BACKUP_SLB_IP
```

### 3.3 回切 (主区域恢复后)

```bash
# 1. 等健康检查通过 5 分钟
# 2. 检查 replica lag = 0
psql -c "SELECT pg_last_wal_replay_lsn() = pg_last_wal_receive_lsn();"
# 3. 灰度: weight 0.1 → 0.5 → 1.0 (各 10 分钟)
```

---

## 4. 数据库运维

### 4.1 备份

```bash
# 自动备份 (RDS / Supabase 已配)
# 手动全量
./scripts/backup-full.sh --region={region}

# 上传 S3
aws s3 cp backup-*.sql s3://waibao-{region}-backups/manual/$(date +%F)/
```

### 4.2 恢复 (staging 测试)

```bash
./scripts/restore-test.sh s3://waibao-cn-backups/manual/2026-07-01/backup.sql
```

### 4.3 恢复 (生产 — 双签)

```bash
# 需 2 个 SRE 确认
./scripts/restore-prod.sh s3://waibao-cn-backups/manual/2026-07-01/backup.sql \
  --signer1=sre-a --signer2=sre-b --confirm
```

### 4.4 慢查询

```sql
-- Top 20 慢查询 (最近 1 小时)
SELECT round(mean_exec_time::numeric, 2) AS mean_ms,
       calls, query
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC LIMIT 20;

-- 索引建议
SELECT * FROM pg_stat_user_tables WHERE seq_scan > idx_scan AND n_live_tup > 1000;
```

### 4.5 连接数满

```bash
# 1. 看谁占着
psql -c "SELECT pid, usename, application_name, state, query FROM pg_stat_activity ORDER BY backend_start;"

# 2. 杀空闲
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle' AND query_start < NOW() - INTERVAL '10 minutes';"

# 3. 应用层检查连接池 (Supabase pgbouncer / SQLAlchemy pool)
```

---

## 5. K8s 运维

### 5.1 集群信息

```bash
# 列出 3 个集群
kubectl config get-contexts

# 当前命名空间
kubectl config set-context --current --namespace=waibao-{region}
```

### 5.2 Pod 排查

```bash
# Pod 状态
kubectl get pods -n waibao-{region}

# 详情
kubectl describe pod -n waibao-{region} <pod>

# 日志
kubectl logs -n waibao-{region} <pod> --tail=200 -f

# 上一实例 (崩溃前的日志)
kubectl logs -n waibao-{region} <pod> --previous
```

### 5.3 扩缩容

```bash
# 手动扩
kubectl scale deployment/waibao-{region}-backend -n waibao-{region} --replicas=5

# 改 HPA
kubectl edit hpa waibao-{region}-backend-hpa -n waibao-{region}
```

### 5.4 节点 drain (升级)

```bash
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
# 升级完成
kubectl uncordon <node-name>
```

### 5.5 Secret 管理

```bash
# 查看
kubectl get secret waibao-{region}-secrets -o yaml

# 更新 (从 .env 文件)
kubectl create secret generic waibao-{region}-secrets \
  --from-env-file=.env.{region} \
  --dry-run=client -o yaml | kubectl apply -f -

# 重启 pod 让 secret 生效
kubectl rollout restart deployment/waibao-{region}-backend -n waibao-{region}
```

---

## 6. 应用发布与回滚

### 6.1 发布流程

```bash
# 1. 构建镜像
docker build -t waibao/backend:v4.0.0-{region} ./backend
docker push registry.{region}/waibao/backend:v4.0.0-{region}

# 2. 更新 kustomize / helm values
yq -i '.images[0].newTag = "v4.0.0-{region}"' infra/region-{region}/k8s/kustomization.yaml

# 3. 应用
kubectl apply -k infra/region-{region}/k8s/

# 4. 看滚动状态
kubectl rollout status deployment/waibao-{region}-backend -n waibao-{region}

# 5. 监控 30 分钟
watch -n 30 'curl -fsS https://api.{region}.waibao.{cn|io}/metrics | grep -E "5xx|latency"'
```

### 6.2 回滚

```bash
# 1. 一键回滚
kubectl rollout undo deployment/waibao-{region}-backend -n waibao-{region}

# 2. 看历史
kubectl rollout history deployment/waibao-{region}-backend -n waibao-{region}

# 3. 回滚到指定版本
kubectl rollout undo deployment/waibao-{region}-backend -n waibao-{region} --to-revision=3

# 4. 数据库迁移回滚 (罕见, 慎用)
psql $DATABASE_URL -f supabase/migrations/rollback/{version}.sql
```

### 6.3 数据库迁移

```bash
# 1. 看新迁移
ls supabase/migrations/*.sql | sort | tail -3

# 2. dry run (staging)
psql $STAGING_DATABASE_URL -f supabase/migrations/030_xxx.sql --single-transaction

# 3. 生产 (按 sg → us → cn 顺序)
for region in sg us cn; do
  psql $PROD_${region^^}_DATABASE_URL -f supabase/migrations/030_xxx.sql --single-transaction
done

# 4. 回滚 (如果失败)
psql $DATABASE_URL -c "BEGIN; ... ROLLBACK;"
```

---

## 7. 灾备演练

### 7.1 季度演练计划

| 季度 | 演练 |
|---|---|
| Q1 | region-cn 主库挂 → 切到只读副本 + 应用层排队 |
| Q2 | region-us 整区挂 → 切到 region-sg (海外用户) |
| Q3 | region-sg 整区挂 → 切到 region-us |
| Q4 | DNS 劫持 → 强制 GeoDNS 重路由 |

### 7.2 演练步骤

```bash
# 1. 通知
# Slack #inc: "开始 Q2 DR drill"

# 2. 模拟故障 (在测试账号)
# 把 region-us 主 LB 在 Route53 weight=0 (或者直接 stop ALB)

# 3. 验证切流
watch -n 5 'curl -fsS https://api.us.waibao.io/health 2>&1 || echo "FAILED"'
# 应该自动切到 sg, 200 持续

# 4. 验证功能
./scripts/smoke_test.sh --region=us --via=sg

# 5. 记录 RTO / RPO
# RTO = 从故障到 100% 流量恢复 (目标 ≤ 15 min)
# RPO = replica lag 中位数 (目标 ≤ 5 min)

# 6. 回切 + postmortem
```

---

## 8. 安全事件响应

### 8.1 PII 泄露

```bash
# 1. 立即停服 (受影响 region)
kubectl scale deployment/waibao-{region}-backend -n waibao-{region} --replicas=0

# 2. 审计日志
psql -c "SELECT * FROM audit_log WHERE created_at > NOW() - INTERVAL '1 hour' AND action LIKE '%export%';"

# 3. 通知 DPO + Legal (24h 内 GDPR 通报, 72h 内 PIPL 通报)
# 4. 修复漏洞
# 5. 写 incident report (Notion 模板)
```

### 8.2 API Key 泄露

```bash
# 1. 立即 rotate
# 阿里云 / AWS / Stripe / OpenAI / Anthropic
# 2. 更新 K8s Secret
kubectl create secret generic waibao-{region}-secrets \
  --from-literal=openai-key=$NEW_KEY \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl rollout restart deployment/waibao-{region}-backend -n waibao-{region}

# 3. 通知 vendor (OpenAI / Stripe) 封禁旧 key
```

---

## 9. 第三方服务故障

| 服务 | 影响 | 降级策略 |
|---|---|---|
| OpenAI 挂了 | AI 面试 / Offer 谈判 / 简历解析 | 切换到 Qwen / DeepSeek / Claude |
| Stripe 挂了 | 支付失败 | 重试 + 排队 + 用户通知 |
| Zoom 挂了 | 视频面试 | 切腾讯会议 (cn) / Google Meet (海外) |
| 钉钉 / 飞书 挂了 | 通知失败 | 重试 + Slack 备份 |
| Supabase 挂了 | Auth / DB | 切到自建 PostgreSQL (region_router) |

---

## 10. 巡检清单

### 每日 (自动化)

- [x] Prometheus 抓取率 (应 > 99%)
- [x] Alertmanager 队列
- [x] 各 region 健康检查
- [x] 备份完整性 (昨天)
- [x] LLM 预算使用率
- [x] Replica lag

### 每周 (人工)

- [ ] 看 Grafana [Weekly Overview] 仪表板
- [ ] 看慢查询报告
- [ ] 检查 cert-manager 证书有效期 (应 > 30 天)
- [ ] 看 Sentry 错误趋势
- [ ] 看 OSS / S3 存储增长

### 每月 (人工)

- [ ] DR 演练 (轮转)
- [ ] Secret 轮换 (30% 抽样)
- [ ] K8s 版本升级 (有 minor release)
- [ ] DB vacuum / analyze
- [ ] 看 cost report (AWS / 阿里云)

### 每季度

- [ ] 完整 DR 演练
- [ ] 合规审计 (GDPR / PIPL / SOC2)
- [ ] 容量规划 (下季度预估)
- [ ] 第三方 vendor 安全 review

---

## 附录

- [MULTI_REGION.md](MULTI_REGION.md) — 多区域架构
- [DEPLOYMENT.md](DEPLOYMENT.md) — 部署指南
- [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) — 灾备
- [PERFORMANCE.md](PERFORMANCE.md) — 性能 / 压测
- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统架构

**维护人**: SRE team (`sre@waibao.io`)
**变更**: 任何 runbook 变更须 PR 评审 + 在 #sre 通知

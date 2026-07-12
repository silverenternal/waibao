# waibao 多区域部署 (Multi-Region Deployment)

> **状态**: v4.0.0 Production · **SLA**: 99.9% 可用性 · **最后更新**: 2026-07-12

---

## 1. 概述

waibao 在 3 个地理区域独立部署, 通过智能 DNS 把用户路由到最近的健康区域:

| 区域 | 用户群 | 云服务商 | 主域 | 写主库 | 状态 |
|---|---|---|---|---|---|
| **region-cn** (中国) | 中国大陆用户 | 阿里云 cn-hangzhou | waibao.cn (ICP 备案) | 阿里云 RDS 主 | ✅ GA |
| **region-sg** (新加坡) | 东南亚 / 全球 | AWS ap-southeast-1 | waibao.io | Supabase SG + RDS 跨区副本 | ✅ GA |
| **region-us** (美西) | 北美 / 欧洲 | AWS us-west-1 | waibao.io | Supabase US + RDS 主 | ✅ GA |

3 个区域共同组成一个全球 SaaS 服务, 数据通过 PostgreSQL 跨区只读副本 + 应用层事件总线同步。

---

## 2. 部署架构图

```
                                    ┌─────────────────────────────────────┐
                                    │   Cloudflare (海外)                 │
                                    │   alidns  (国内)                    │
                                    │   GeoDNS + WAF + DDoS               │
                                    └──────┬───────────────────┬──────────┘
                                           │                   │
                          中国 ISP ────────┘                   └─────── 海外 ISP
                              │                                          │
                              ▼                                          ▼
                  ┌──────────────────────────┐         ┌──────────────────────────────────────┐
                  │ region-cn (阿里云)         │         │ region-sg / region-us (AWS)         │
                  │  SLB → ACK (K8s)          │         │  ALB → EKS (K8s)                    │
                  │  ┌──────────────────┐    │         │  ┌──────────────────────────────┐    │
                  │  │ backend (3 pods) │    │         │  │ backend (2/3 pods)           │    │
                  │  │ frontend (2 pods)│    │         │  │ frontend (2/3 pods)          │    │
                  │  └────────┬─────────┘    │         │  └────────┬─────────────────────┘    │
                  │           │              │         │           │                           │
                  │  ┌────────▼─────────┐    │         │  ┌────────▼─────────────────────┐    │
                  │  │ RDS PG 15 主      │◀───RDS────▶│  │ Supabase PG (主)             │    │
                  │  │ + 1 只读副本      │  跨区同步   │  │ RDS PG (跨区只读副本)        │    │
                  │  └──────────────────┘    │         │  └──────────────────────────────┘    │
                  │  ┌──────────────────┐    │         │  ┌──────────────────────────────┐    │
                  │  │ Redis 主从        │    │         │  │ ElastiCache Redis (3 节点)   │    │
                  │  └──────────────────┘    │         │  └──────────────────────────────┘    │
                  │  ┌──────────────────┐    │         │  ┌──────────────────────────────┐    │
                  │  │ OSS (cn-hangzhou)│    │         │  │ S3 (区域隔离)                │    │
                  │  └──────────────────┘    │         │  └──────────────────────────────┘    │
                  └──────────────────────────┘         └──────────────────────────────────────┘
                              ▲                                          ▲
                              │       事件总线 (Pub/Sub + Outbox)        │
                              └──────────────────────────────────────────┘
```

### 区域角色

| 区域 | 写主库 | 跨区副本 | 主要第三方 |
|---|---|---|---|
| **region-cn** | RDS 主 | → sg / us 只读 | 钉钉, 飞书, 微信小程序, OSS-CN, 阿里云 ACK |
| **region-sg** | Supabase PG | → cn / us 只读 | Stripe (SG), Zoom, Greenhouse, Checkr (备份) |
| **region-us** | Supabase PG / RDS 主 | → cn / sg 只读 | Stripe (US), Zoom, Greenhouse, Lever, Checkr |

---

## 3. 数据同步策略

### 3.1 写主库 (Primary)

- **用户登录 / 创建**: 按用户 `region_pref` 字段路由到对应主库
- **新用户默认**: 中国 IP → region-cn, 其他 → region-us (Cloudflare geo header)
- **登录后 cookie 锁定 region**: `waibao_region=cn|sg|us`, 1 年有效

### 3.2 跨区只读副本

- **PostgreSQL streaming replication** (异步, lag 通常 < 5s)
- **读路由**:
  - 同区域读 → 主库 (强一致)
  - 跨区域读 → 只读副本 (最终一致)
- **典型场景**: 海外用户在中国有订单, 美国后台查 → region-us 副本读

### 3.3 事件总线 (Outbox + Pub/Sub)

关键事件 (订单 / Offer / 候选人状态) 通过 **outbox pattern** 跨区域同步:

```
1. 业务事务 + outbox row (同事务写入)
2. outbox-relay 进程 (每区域 1 个) 轮询 → 推送到 Pub/Sub
3. 接收区域订阅 → 幂等写入本地表
4. 失败重试 (指数退避) → 3 次后入 dead letter queue
```

- region-cn 用 阿里云 RocketMQ
- region-sg / region-us 用 AWS SNS+SQS (跨 region SNS topic)

### 3.4 文件 / 媒体

- 用户上传 (简历 PDF / 视频) 默认存本区域 OSS/S3
- 跨区访问通过预签名 URL (2h TTL)
- 不做实时跨区复制 (太大); 异步 ETL 到只读备份桶

### 3.5 合规与数据驻留

| 区域 | 数据驻留 | 合规要求 |
|---|---|---|
| region-cn | 仅境内 | PIPL, MLPS 2.0, ICP 备案, 不出境 |
| region-sg | SG + APAC | GDPR, PDPA-SG |
| region-us | US | CCPA, SOC2 Type II |

每个 backend pod 通过 `DATA_RESIDENCY` env 强制只能连接本区主库 (跨区只能读只读副本)。

---

## 4. 切换流程 (Failover)

### 4.1 自动故障检测

- 健康检查: 3 区域每 30s `GET /health`
- 失败 ≥ 3 次 → region 标记 unhealthy
- DNS LB pool weight → 0 (自动)

### 4.2 手动切换 (SRE)

```
场景: region-us 整个区域挂, 海外用户切到 region-sg

1. ack PagerDuty alert
2. Cloudflare LB: us-primary.weight=0, sg-primary.weight=2.0
3. 监控: SRE dashboard 看 region-sg QPS / 错误率
4. ETA: ≤ 5 分钟
5. #inc Slack: "Failing over US → SG"
6. 演练后: 写 postmortem (RCA + 改进行动)
```

### 4.3 回切

主区域恢复后:

1. 健康检查通过 5 分钟
2. SRE 评估数据库一致性 (replica lag = 0)
3. 灰度切回: `us.weight=0.1` → 0.5 → 1.0 (各 10 分钟观察)

### 4.4 RTO / RPO

| 指标 | 目标 | 实测 |
|---|---|---|
| **RTO** (Recovery Time Objective) | ≤ 15 分钟 | 8 分钟 (2026-Q2 DR drill) |
| **RPO** (Recovery Point Objective) | ≤ 5 分钟 | 12 秒 (replica lag 中位数) |

---

## 5. SLA & 可用性

- **目标**: 99.9% 月可用性 (43.2 分钟停机/月)
- **三区域并联**: 单区域故障不影响其他区域
- **跨区降级模式** (catastrophic): DB 主库挂了 → 切到最近只读副本 + 应用层排队写入, 主库恢复后回放

### 月度统计 (样例)

```
2026-06:
  region-cn:  99.97% (10 分钟停机 - 阿里云 RDS 主从切换)
  region-sg:  100%
  region-us:  99.95% (22 分钟 - EKS node drain)
  总计:       99.94% (按用户加权)
```

---

## 6. 部署变更流程

1. PR 提到 master → CI 跑测试 (pytest + tsc + build + smoke)
2. Merge → 自动构建镜像 (GHCR + ACR 镜像同步)
3. 部署顺序: `region-sg` → `region-us` → `region-cn`
   - 海外先上, 国内放最后 (合规 + 用户活跃度)
4. 灰度: HPA 缩 1 个 pod 升级 → 观察 5 分钟 → 全量
5. 回滚: `kubectl rollout undo deployment/waibao-*-backend`

详见 [RUNBOOK.md](RUNBOOK.md) §6。

---

## 7. 监控 & 告警

| 指标 | 阈值 | 告警渠道 |
|---|---|---|
| 5xx 错误率 | > 1% (5 分钟) | PagerDuty + Slack |
| P99 延迟 | > 800 ms | Slack |
| 健康检查失败 | ≥ 3 次 | 自动切流 + PagerDuty |
| Replica lag | > 60 秒 | Slack |
| DB 连接数 | > 80% | Slack |
| OSS/S3 4xx 错误率 | > 0.5% | Slack |

仪表盘: Grafana → [Multi-Region Overview] (链接见 RUNBOOK.md)

---

## 8. 相关文档

- [DEPLOYMENT.md](DEPLOYMENT.md) — 单区域部署详细步骤
- [RUNBOOK.md](RUNBOOK.md) — 运维操作手册
- [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) — 灾备演练
- [PERFORMANCE.md](PERFORMANCE.md) — 压测报告
- [ARCHITECTURE.md](ARCHITECTURE.md) §多区域

---

**维护人**: SRE team (`sre@waibao.io`)
**变更**: 任何 region 拓扑变更须先发 RFC 到 `#sre` 评审

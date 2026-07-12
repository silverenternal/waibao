# 部署指南 (Deployment Guide)

> **v4.0.0** · 单区域 / 多区域部署 · **SLA**: 99.9% · **最后更新**: 2026-07-12

---

## 目录

1. [部署架构](#1-部署架构)
2. [依赖服务](#2-依赖服务)
3. [单区域部署 (开发 / staging)](#3-单区域部署)
4. [多区域部署 (生产)](#4-多区域部署)
5. [环境变量](#5-环境变量)
6. [监控](#6-监控)
7. [备份与恢复](#7-备份与恢复)
8. [故障排查](#8-故障排查)
9. [升级流程](#9-升级流程)
10. [运维联系](#10-运维联系)

---

## 1. 部署架构

### 1.1 整体拓扑

```
                          ┌──────────────────────────┐
                          │  alidns / Cloudflare     │
                          │  GeoDNS + WAF + DDoS     │
                          └──────┬──────────┬────────┘
                                 │          │
                       中国 ISP  │          │  海外 ISP
                                 ▼          ▼
                  ┌────────────────────┐  ┌────────────────────────────────┐
                  │ region-cn          │  │ region-sg + region-us         │
                  │ 阿里云 cn-hangzhou │  │ AWS ap-southeast-1 + us-west-1│
                  │ SLB → ACK          │  │ ALB → EKS                     │
                  │ RDS 主 + 1 副本    │◀─▶│ Supabase / RDS 主 + 跨区副本  │
                  │ Redis 主从         │  │ ElastiCache Redis (3 节点)    │
                  │ OSS                │  │ S3 (区域隔离)                 │
                  └────────────────────┘  └────────────────────────────────┘
```

详细架构 / 数据同步 / 切流: [MULTI_REGION.md](MULTI_REGION.md)

### 1.2 服务清单

| 服务 | 用途 | 推荐供应商 | 区域 |
|---|---|---|---|
| PostgreSQL + pgvector | 主数据库 | 阿里云 RDS / Supabase / AWS RDS | cn / sg / us |
| Realtime | WebSocket 订阅 | Supabase Realtime | sg / us |
| Auth | JWT 鉴权 | Supabase Auth | all |
| Storage / OSS / S3 | CV / 资质文件 / 视频 | 阿里云 OSS / AWS S3 | all |
| LLM | GPT-4o / Claude / Qwen / DeepSeek | OpenAI / Anthropic / 阿里云 | all |
| Embedding | text-embedding-3 | OpenAI | all |
| Container | 部署运行时 | 阿里云 ACK / AWS EKS | cn / sg / us |
| CDN | 前端分发 | Cloudflare | all |
| 智能 DNS | GeoDNS | alidns / Cloudflare | cn / sg / us |
| 监控 | 指标 / 日志 | Prometheus + Grafana + Loki | all |
| 告警 | 通知 | 钉钉 / 飞书 / PagerDuty | all |

---

## 2. 依赖服务

### 2.1 必装 (生产)

| 服务 | 最低规格 | 高可用要求 |
|---|---|---|
| PostgreSQL 15 | 2 vCPU / 4 GB / 100 GB | 主从 + 跨区只读副本 |
| Redis 7.0 | 1 GB 主从 | 主从 + Sentinel / Cluster |
| Object Storage | 100 GB 起 | 跨区复制 (CRR) |
| Container 编排 | K8s 1.30 | 多 AZ, HPA |
| 负载均衡 | HTTPS 443 | WAF + DDoS |
| DNS | GeoDNS | 健康检查 + 自动切流 |

### 2.2 可选

- WebSocket 网关 (Supabase Realtime / 自建)
- 视频转码 (ffmpeg + S3 + CloudFront)
- 邮件 / 短信 (阿里云 / Twilio / 阿里大于)

---

## 3. 单区域部署

### 3.1 本地 / Staging (Docker Compose)

```bash
git clone https://github.com/silverenternal/waibao.git
cd waibao/talent-tool-mvp

# 配置环境变量
cat > .env <<EOF
SUPABASE_URL=http://supabase-kong:8000
SUPABASE_KEY=eyJhbGc...
SUPABASE_SERVICE_KEY=eyJhbGc...
SUPABASE_JWT_SECRET=your-jwt-secret
OPENAI_API_KEY=sk-xxx
PII_ENCRYPTION_KEY=$(openssl rand -base64 32)
CORS_ORIGINS=http://localhost:3000
DEFAULT_LOCALE=zh
REGION=local
DATA_RESIDENCY=local
EOF

# 启动
docker-compose up -d

# 验证
curl http://localhost:8000/health
# → {"status":"ok","region":"local"}
```

### 3.2 单区域生产 (Docker Compose)

```bash
docker-compose -f docker-compose.prod.yml up -d --build

# 健康检查
curl -fsS http://localhost:8000/health
```

---

## 4. 多区域部署

> 详见 [MULTI_REGION.md](MULTI_REGION.md) — 架构 / 数据同步 / 切流

### 4.1 区域概览

| 区域 | 用户群 | 部署 | 域名 |
|---|---|---|---|
| **region-cn** | 中国大陆 | `infra/region-cn/` | waibao.cn (ICP 备案) |
| **region-sg** | 东南亚 / 全球 | `infra/region-sg/` | sg.waibao.io |
| **region-us** | 北美 / 欧洲 | `infra/region-us/` | us.waibao.io / waibao.io |

每个区域独立目录: `docker-compose.yml` (本地) + `k8s/` (生产) + `terraform/` (IaC)。

### 4.2 Terraform 初始化

```bash
# region-cn (阿里云)
cd infra/region-cn/terraform
export TF_VAR_rds_password=$(openssl rand -hex 16)
export ALICLOUD_ACCESS_KEY=...
export ALICLOUD_SECRET_KEY=...
terraform init
terraform plan
terraform apply

# region-sg (AWS Singapore)
cd ../../region-sg/terraform
export TF_VAR_rds_sg_ro_password=$(openssl rand -hex 16)
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
terraform init && terraform apply

# region-us (AWS us-west-1)
cd ../../region-us/terraform
export TF_VAR_rds_us_password=$(openssl rand -hex 16)
terraform init && terraform apply
```

### 4.3 K8s 部署

```bash
# region-cn
kubectl --context cn-hangzhou-prod apply -f infra/region-cn/k8s/

# region-sg
aws eks update-kubeconfig --name waibao-sg --region ap-southeast-1
kubectl apply -f infra/region-sg/k8s/

# region-us
aws eks update-kubeconfig --name waibao-us --region us-west-1
kubectl apply -f infra/region-us/k8s/
```

### 4.4 DNS 智能解析

```bash
# 国内 alidns (waibao.cn)
# 海外 Cloudflare (waibao.io)
# 配置见 infra/dns/geo-routing.yml
```

### 4.5 部署顺序

每次发版按 **sg → us → cn** 顺序:

```bash
./scripts/deploy-region.sh sg   # 海外先发
./scripts/deploy-region.sh us
./scripts/deploy-region.sh cn   # 国内放最后 (合规 + 用户活跃度)
```

---

## 5. 环境变量

### 5.1 必填

```bash
ENV=production
SUPABASE_URL=...
SUPABASE_KEY=...
SUPABASE_SERVICE_KEY=...      # ⚠️ 严格保密
SUPABASE_JWT_SECRET=...
PII_ENCRYPTION_KEY=<base64-32-bytes>  # ⚠️ 严格保密
CORS_ORIGINS=https://your-domain.com
DEFAULT_LOCALE=zh

# 多区域
REGION=cn|sg|us                # 当前区域
DATA_RESIDENCY=cn|sg|us        # 数据驻留约束
REGION_ROUTING_PRIMARY=cn
REGION_ROUTING_REPLICAS=sg,us
```

### 5.2 推荐

```bash
# 限流
RATE_LIMIT_PER_USER=100         # req/min
LLM_BUDGET_PER_USER=100000      # tokens/day

# 多区域读副本
READONLY_DATABASE_URL=...       # 跨区只读副本

# CDN
SENTRY_DSN=...
NEXT_PUBLIC_GA_ID=...
```

### 5.3 第三方 (按区域)

```bash
# region-cn
DEEPSEEK_API_KEY=...
QWEN_API_KEY=...
DINGTALK_APP_KEY=...
DINGTALK_APP_SECRET=...
WECHAT_MINIPROGRAM_APPID=...
WECHAT_MINIPROGRAM_SECRET=...
ICP_LICENSE=京ICP备2024xxxxxx号-1

# region-sg / region-us
ANTHROPIC_API_KEY=...
STRIPE_SECRET_KEY=...
ZOOM_API_KEY=...
ZOOM_API_SECRET=...
GREENHOUSE_API_KEY=...
LEVER_API_KEY=...
CHECKR_API_KEY=...
```

完整列表见 [backend/.env.example](../backend/.env.example)

---

## 6. 监控

### 6.1 Prometheus + Grafana

```bash
cd infra/monitoring
docker-compose -f docker-compose.monitoring.yml up -d

# 访问
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3001
# 仪表板:     infra/grafana-dashboard.json
```

### 6.2 关键指标

| 指标 | 类型 | 告警阈值 |
|---|---|---|
| `waibao_http_requests_total{status="5xx"}` | Counter | > 1% (5 分钟) |
| `waibao_http_request_duration_seconds` | Histogram | P99 > 800 ms |
| `waibao_llm_tokens_total` | Counter | > 预算 80% |
| `waibao_region_health` | Gauge | 0 持续 90s |
| `waibao_replica_lag_seconds` | Gauge | > 60s |
| `waibao_db_connections` | Gauge | > 80% |

### 6.3 告警 (Alertmanager)

```yaml
# infra/alertmanager.yml
# 已配置: 钉钉 / 飞书 / PagerDuty / Slack
channels:
  critical: pagerduty
  warning:  dingtalk-webhook
  info:     slack-#ops
```

---

## 7. 备份与恢复

详见 [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md)

### 7.1 备份策略

| 区域 | 自动备份 | 跨区复制 |
|---|---|---|
| region-cn | 阿里云 RDS 自动 7 天 + OSS 跨区 (cn-shanghai) | ✅ |
| region-sg | AWS RDS 自动 14 天 + S3 → us-west-1 | ✅ |
| region-us | AWS RDS 自动 14 天 + S3 → ap-southeast-1 | ✅ |

### 7.2 手动备份

```bash
# 单库
pg_dump $DATABASE_URL > backup-$(date +%F).sql

# 全量 (含 schema + data + globals)
./scripts/backup-full.sh

# 上传到对象存储
aws s3 cp backup-*.sql s3://waibao-$(region)-backups/manual/
```

### 7.3 恢复

```bash
# 测试恢复 (staging)
./scripts/restore-test.sh backup-2026-07-01.sql

# 生产恢复 (慎用, 需 SRE 双签)
./scripts/restore-prod.sh backup-2026-07-01.sql --confirm
```

---

## 8. 故障排查

### 8.1 后端 500 错误

```bash
# region-cn
kubectl logs -n waibao-cn -l app=waibao-cn-backend --tail=200

# 常见:
# - SUPABASE_URL 配错
# - OpenAI key 无效 / quota
# - JWT secret 不匹配
# - RDS 连接数满
```

### 8.2 LLM 调用超时

```python
# backend/services/llm_cache.py: 启用缓存减少重复调用
# backend/services/llm_budget.py: 调整 per-user 配额
# 切换到更快模型: gpt-4o-mini / claude-haiku / qwen-turbo
```

### 8.3 WebSocket 断开

```nginx
# nginx / ALB / SLB 都要支持 WebSocket 升级
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 86400;
```

### 8.4 跨区延迟高

```bash
# 检查 replica lag
psql -c "SELECT now() - pg_last_xact_replay_timestamp();"

# 排查:
# 1. 跨区网络 (CN ↔ US 正常 200-250ms)
# 2. 只读副本 IO 瓶颈
# 3. 应用是否误连了主库
```

完整 Runbook: [RUNBOOK.md](RUNBOOK.md)

---

## 9. 升级流程

```bash
# 1. 拉新代码
git pull origin master

# 2. 数据库迁移 (按顺序)
ls supabase/migrations/*.sql | sort | tail -3
psql $DATABASE_URL -f supabase/migrations/029_ats_sync.sql
psql $DATABASE_URL -f supabase/migrations/030_xxx.sql

# 3. 镜像构建 + 推送 (3 区域 registry)
docker build -t waibao/backend:v4.0.0 ./backend
docker push registry.cn-hangzhou.aliyuncs.com/waibao/backend:v4.0.0
docker push ghcr.io/silverenternal/waibao/backend:v4.0.0

# 4. 按 sg → us → cn 顺序滚动升级
for region in sg us cn; do
  ./scripts/deploy-region.sh $region
done

# 5. 验证 (每个区域)
for region in cn sg us; do
  curl -fsS https://api.${region}.waibao.$( [[ $region = cn ]] && echo cn || echo io )/health
done

# 6. 监控 30 分钟, 错误率 / 延迟无异常 → 关闭旧版本
```

回滚:

```bash
kubectl rollout undo deployment/waibao-${region}-backend -n waibao-${region}
```

---

## 10. 运维联系

- **文档**: [docs/](../)
- **Issues**: https://github.com/silverenternal/waibao/issues
- **监控**: Grafana 仪表板
- **告警**: 钉钉 #recruittech-ops / PagerDuty
- **值班**: SRE 7×24 (P1 15 分钟响应)
- **邮箱**: sre@waibao.io

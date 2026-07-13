# waibao Status Page — 订阅 & 运维手册

> **URL**: https://status.waibao.cn
> **后端**: Instatus 自托管 (`infra/instatus/docker-compose.yml`)
> **真实数据源**: `services/platform/sla_monitor.py`

---

## 1. 概述

`status.waibao.cn` 是 waibao 的 **公开** 状态页。任何访客都可以:

* 查看 **5 个核心服务** 的实时状态
* 查看 **90 天 uptime 历史** 与是否达成 99.9% 目标
* 订阅事故 / 维护通知 (Email + Webhook)
* 浏览 planned maintenance 公告

数据每 60 秒从后端的 SLA 监控服务同步一次。

---

## 2. 监控的 5 个服务

| Key      | Display name                          |
|----------|---------------------------------------|
| `api`     | Public API & Authentication           |
| `llm`     | LLM Inference (multi-provider)        |
| `storage` | Object Storage & File Uploads         |
| `webhook` | Outbound Webhooks & Integrations      |
| `database`| Primary Database (Supabase+pgvector)  |

这与 `sla_monitor.PLATFORM_SERVICES` 严格 1:1 对应;增删服务需同步修改。

---

## 3. 数据流

```
┌──────────────────────┐  60 s pull  ┌────────────────────────┐
│  sla_monitor.py      │────────────▶│ Instatus /api/sync     │
│  GET /api/admin/sla  │  JSON       │                        │
└──────────────────────┘             └────────────────────────┘
                                                    │
                                                    ▼
                                         status.waibao.cn (公开)
```

1. SLA Monitor (Python, in-backend) 持续记录 5 服务的请求样本。
2. `GET /api/admin/sla/30d` 返回结构化指标(JSON)。
3. Bridge container (`infra/instatus/docker-compose.yml` 中的 `sla-bridge`)
   每 60 秒调用 `GET .../sla/30d` → POST `/api/sync`。
4. 状态页组件读取 Instatus 数据,渲染给访客。

---

## 4. 订阅 (Subscribe)

### 4.1 Email 订阅

访问 https://status.waibao.cn 在底部表单填:

* 邮箱
* 通知类型 (事故 / 计划维护 / 全部)

链接确认邮件会在 10 分钟内送达。

### 4.2 Webhook 订阅

支持通用 webhook (Slack-compatible):

```bash
POST https://status.waibao.cn/api/public/status/subscribers
Content-Type: application/x-www-form-urlencoded

email=&channel=webhook&webhook_url=https://hooks.slack.com/services/T0/B0/XYZ
```

订阅方接收:

```json
{
  "incident_id": "INC-2026-07-04-001",
  "service": "llm",
  "status": "investigating",
  "title": "LLM provider intermittent 5xx",
  "started_at": "2026-07-04T03:21:00Z",
  "url": "https://status.waibao.cn/incidents/INC-2026-07-04-001"
}
```

### 4.3 Slack 直连

把 webhook URL 换成 `https://hooks.slack.com/services/XXX`,Instatus 会以
原生 Block Kit 卡片样式转发。

---

## 5. 事故响应流程

| 步骤 | 动作                                                | 时限     |
|------|---------------------------------------------------|---------|
| 1    | 自动检测 (AlertingService P0/P1)                  | < 60 秒  |
| 2    | 在状态页创建 Incident, 状态置为 `investigating`     | < 5 分钟 |
| 3    | 发送通知给订阅者                                     | < 5 分钟 |
| 4    | 每 30 分钟更新一次 postmortem 草稿                  | 直到解决 |
| 5    | 关闭事故 + 发 90 天 follow-up 邮件 + 写 public RCA | < 72 小时 |

详见 `docs/INCIDENT_RESPONSE.md` (后续 T2605 +)。

---

## 6. 自托管 Instatus 部署

```bash
# 1. Copy env file
cp infra/instatus/.env.example .env

# 2. Boot
docker compose -f infra/instatus/docker-compose.yml --env-file .env up -d

# 3. Behind a reverse proxy (Caddy shown):
status.waibao.cn {
    reverse_proxy waibao-statuspage:3000
    tls ops@waibao.cn
}
```

依赖:

* Docker 24+
* Postgres 16 (由 docker-compose 启动)
* 一个公开域名 + TLS 证书

---

## 7. 内部故障演练

每季度执行一次:

1. **Chaos day**: 随机挑选一个服务,主动制造 5xx,验证状态页 + 通知流转
2. **Metrics audit**: 比对状态页 uptime vs `GET /api/admin/sla/30d`,
   确保数据零差异
3. **Subscriber test**: 端到端验证 Email + Slack 通知触达

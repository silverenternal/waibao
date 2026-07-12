# ALERTING.md — Waibao v5.0 告警体系 (T1704)

> Owner: SRE + 实施工程师
> Status: ✅ 服务 + 通道 + 规则 + 演练全栈就绪 (2026-Q3)
> 目标: 7×24 生产告警端到端 (Prometheus → AlertManager → 钉钉/飞书/PagerDuty/Webhook)

---

## 1. 架构总览

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│ Prometheus  │ ──> │ AlertManager │ ──> │  通道 (4个)  │
│  alerts.yml │     │   routes     │     │ • 钉钉       │
│  30+ rules  │     │   receivers  │     │ • 飞书       │
└─────────────┘     └──────────────┘     │ • PagerDuty  │
       │                                  │ • Webhook    │
       │                                  └──────────────┘
       │                                          │
       │            ┌─────────────────────────────┘
       │            ▼
       │    ┌──────────────────────────┐
       │    │ services/observability/  │
       │    │ alerting.py (内部)        │
       └────┤ - Alert / Severity       │
            │ - 4 Channel 实现         │
            │ - 限流 / 历史 / dry-run  │
            └──────────────────────────┘
                     │
                     ▼
            ┌────────────────────┐
            │ 应用内部触发         │
            │ (e.g. budget 超)   │
            └────────────────────┘
```

**双轨设计**:
- **Prometheus 路径**: 指标 → 规则 → AlertManager → 通道 (适合延迟/错误率/资源)
- **应用内路径**: 代码主动调用 `fire()` → AlertingService → 通道 (适合预算/业务事件)

---

## 2. 严重度与响应 SLA

| 级别 | Severity | 响应 SLA | 通知通道 | 升级 |
| --- | --- | --- | --- | --- |
| **P0** | `critical` | 5 min | PagerDuty (高优) + 钉钉 oncall + 飞书 oncall + Webhook | 5min 内无人 ack → 升级到值班经理 |
| **P1** | `high` | 15 min | 钉钉 + 飞书 + Webhook | 30min 内未 ack → 升级到 SRE Lead |
| **P2** | `warning` | 1 h | 钉钉 + 飞书 | 工作时间处理 |
| **P3** | `info` | 当天 | 飞书 | 仅记录, 周报汇总 |

---

## 3. 通道配置

### 3.1 钉钉 (DingTalk)
- **URL**: `DINGTALK_WEBHOOK_URL` (群机器人 webhook, 含 access_token)
- **签名密钥**: `DINGTALK_SECRET` (推荐开启加签)
- **@**: 支持 `@所有人` 或 `@指定手机号`
- **格式**: Markdown
- **获取步骤**: 群设置 → 智能群助手 → 添加机器人 → 自定义 (加签) → 复制 webhook

### 3.2 飞书 (Feishu)
- **URL**: `FEISHU_WEBHOOK_URL`
- **签名密钥**: `FEISHU_SECRET` (可选)
- **格式**: Interactive Card (按 severity 着色: 红/橙/黄/蓝)
- **@**: 支持 `@user_id`
- **获取步骤**: 群设置 → 群机器人 → 添加机器人 → 自定义机器人 → 复制 webhook

### 3.3 PagerDuty
- **Routing Key**: `PAGERDUTY_ROUTING_KEY` (Events API v2 integration)
- **API URL**: `PAGERDUTY_API_URL` (默认 `https://events.pagerduty.com/v2/enqueue`)
- **Dedup Key**: 用 `alert.fingerprint`, 自动合并 + resolve
- **Urgency**: P0 → high, 其他 → low
- **获取步骤**: PagerDuty → Service Directory → 选择 service → Integrations → Add an integration → Events API v2 → 复制 Integration Key (即 routing_key)

### 3.4 Webhook
- **URL**: `ALERT_WEBHOOK_URL` (任意 HTTP 端点)
- **Auth Header**: `ALERT_WEBHOOK_AUTH_HEADER` (如 `Bearer xyz`)
- **Payload**: 完整 `Alert.to_dict()` JSON
- **降级**: URL 未配置时, 告警写入 `logs/alerts.log` (永不丢告警)

---

## 4. Prometheus 规则 (30+)

文件: `infra/prometheus/alerts.yml`, 共 **37 条规则**, 分 7 个业务域:

| 域 | 规则数 | 覆盖 |
| --- | --- | --- |
| `api.rules` | 8 | 5xx / 4xx / P95 / P99 / 流量 / 实例存活 / 探针 |
| `llm.rules` | 7 | 预算 / 错误率 / 慢调用 / 缓存命中率 / 限流 / token 突增 |
| `db.rules` | 7 | Postgres 连接 / 复制延迟 / 慢查询 / 磁盘 / Redis 内存 / 宕机 / 驱逐 |
| `ws.rules` | 4 | 连接数 / 消息延迟 / 错误率 / Redis pub/sub backlog |
| `infra.rules` | 5 | CPU / 内存 / 磁盘 / 文件描述符 |
| `job.rules` | 3 | 卡住 / 失败率 / 超时 |
| `security.rules` | 3 | 401 突增 / 可疑调用 / Sentry 新错误 |

### 4.1 加载到 Prometheus
```yaml
# prometheus.yml
rule_files:
  - "alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

### 4.2 加载到 AlertManager
```yaml
# alertmanager.yml (已存在的)
route:
  receiver: "dingtalk-team"
  routes:
    - match:
        severity: critical
      receiver: "pagerduty-oncall"
```

### 4.3 常用 PromQL 切片
```promql
# 当前 firing 告警按 severity 计数
count by (severity) (ALERTS{alertstate="firing"})

# 单业务域 firing 数
count by (team) (ALERTS{alertstate="firing"})

# 误报率 (频繁 resolve → fire)
rate(ALERTS{alertstate="firing"}[1h])
```

---

## 5. 应用代码使用

### 5.1 主动触发 (推荐方式)

```python
from services.observability.alerting import (
    fire, AlertSeverity, AlertingService, Alert,
)

# 快捷方式
result = fire(
    name="LLMBudgetOver",
    severity=AlertSeverity.P0,
    summary="LLM 日成本已超预算 120%",
    labels={"provider": "openai", "model": "gpt-4o"},
    value=1.20,
    description="今日 LLM 成本 $1,200 / 预算 $1,000",
    runbook_url="https://wiki.waibao/runbook/llm-budget",
)
# result = {"status": "sent", "fingerprint": "...", "channels": {...}}
```

### 5.2 完整 Alert 对象

```python
from services.observability.alerting import Alert, AlertSeverity, get_default_service
from datetime import datetime, timezone

alert = Alert(
    name="DBReplicationLag",
    severity=AlertSeverity.P1,
    summary="主从延迟 90s",
    description="replica-us 落后 primary 90s",
    labels={"db": "primary", "replica": "replica-us"},
    annotations={"team": "data"},
    value=90.0,
    source="app",
    runbook_url="https://wiki.waibao/runbook/db-replication",
)

svc = get_default_service()
result = svc.fire(alert)
```

### 5.3 解决 (Resolve)

```python
from services.observability.alerting import resolve

# 当问题修复时调用, 会发 resolved 状态告警 (PagerDuty 自动 resolve)
resolve("DBReplicationLag", labels={"db": "primary"})
```

### 5.4 自定义服务

```python
from services.observability.alerting import (
    AlertingService, DingTalkChannel, FeishuChannel,
    AlertSeverity, AlertChannel, DEFAULT_ROUTING,
)

svc = AlertingService(
    channels={
        AlertChannel.DINGTALK: DingTalkChannel(at_all=True),
        AlertChannel.FEISHU: FeishuChannel(),
    },
    routing={
        AlertSeverity.P0: [AlertChannel.DINGTALK, AlertChannel.FEISHU],
        AlertSeverity.P1: [AlertChannel.DINGTALK],
    },
    suppress_window_sec=300,  # 5 分钟内同 fingerprint 抑制
    dry_run=False,
)
```

### 5.5 历史 & 统计

```python
svc = get_default_service()
recent = svc.history(limit=50)   # 最近 50 条
stats = svc.stats()              # {total, by_severity, channels}
```

---

## 6. 演练脚本 (T1704)

文件: `scripts/disaster_drill.sh`

```bash
# 默认 smoke: 触发 1 P0 + 1 P1
bash scripts/disaster_drill.sh

# 仅 P0
bash scripts/disaster_drill.sh alert-p0

# 全部 4 个 severity
bash scripts/disaster_drill.sh alert-all

# 4 类灾难 + 4 个 severity = 8 场景
bash scripts/disaster_drill.sh full

# DB failover
bash scripts/disaster_drill.sh db-failover
```

输出:
- `logs/disaster_drill_<ts>.log` — 原始执行日志
- `logs/disaster_drill_report_<ts>.md` — 自动汇总报告 (RTO 表格)

---

## 7. 值班 / 升级路径

### 7.1 值班轮值
- 主值班: 7×24, 每班 12 小时
- 备值班: 主值班 5 分钟未 ack 时自动接管
- 值班表: ops@pagerduty.com (PagerDuty Schedule)

### 7.2 升级路径
```
P0 触发
  ├─ 0 min: PagerDuty 高优 + 钉钉/飞书 oncall 群
  ├─ 5 min: 主值班未 ack → 备值班 + SRE Lead
  ├─ 15 min: 仍未 ack → 工程负责人
  └─ 30 min: CTO
```

### 7.3 Oncall 工具
- 钉钉群: `waibao-oncall` (P0 + P1)
- 飞书群: `招聘智能体-告警` (全 severity)
- PagerDuty: https://waibao.pagerduty.com
- 状态页: https://status.waibao.com

---

## 8. Runbook 索引

| 告警名 | 级别 | Runbook |
| --- | --- | --- |
| HighErrorRate5xx | P0 | wiki/runbook/HighErrorRate5xx |
| EndpointUnavailable | P0 | wiki/runbook/EndpointUnavailable |
| SlowP95Latency | P1 | wiki/runbook/SlowP95Latency |
| LLMBudgetOver80Percent | P1 | wiki/runbook/LLM-Budget |
| LLMHighErrorRate | P0 | wiki/runbook/LLM-Provider-Failover |
| PostgresConnectionsHigh | P1 | wiki/runbook/PG-Connection-Pool |
| PostgresReplicationLag | P1 | wiki/runbook/PG-Replication |
| RedisDown | P0 | wiki/runbook/Redis-Failover |
| WSConnectionCountHigh | P2 | wiki/runbook/WS-Scale-Out |
| WSMessageLatencyHigh | P1 | wiki/runbook/WS-Latency |
| DiskSpaceCritical | P0 | wiki/runbook/Disk-Cleanup |
| FileDescriptorExhausted | P1 | wiki/runbook/FD-Exhausted |
| JobStalled | P1 | wiki/runbook/Job-Stalled |
| AuthFailureSpike | P1 | wiki/runbook/Security-Brute-Force |

> 创建/更新 runbook: 修改 `docs/runbooks/` 或 wiki

---

## 9. 抑制 / 静音

### 9.1 AlertManager 静音
```bash
amtool silence add --alertmanager.url=http://localhost:9093 \
    --comment="v5.1 deploy" --duration=30m \
    --match alertname="HighErrorRate5xx"
```

### 9.2 应用层抑制
- `suppress_window_sec=60`: 同一 fingerprint 在 60s 内只发一次
- resolved 状态永远立即发出 (用于 PagerDuty dedup_key 解决)

---

## 10. 复测节奏

| 触发 | 频率 | Owner |
| --- | --- | --- |
| 新告警规则加入 | 必跑 (drill alert-pX) | SRE |
| 通道配置变更 | 必跑 | SRE |
| 月度 | full (4 disaster + 4 severity) | SRE |
| 季度 | 真实 RTO/RPO 验证 | SRE + 实施 |
| 年度 | 大规模灾备演练 | 全员 |

---

## 附录 A — 文件清单

| 路径 | 说明 |
| --- | --- |
| `backend/services/observability/alerting.py` | 告警服务核心 (Alert + 4 Channel + AlertingService) |
| `infra/prometheus/alerts.yml` | 30+ 告警规则 (7 业务域 / 4 severity) |
| `infra/alertmanager.yml` | AlertManager 路由 (钉钉 / PagerDuty) |
| `scripts/disaster_drill.sh` | 灾备演练 + 告警端到端验证 |
| `docs/ALERTING.md` | 本文档 |
| `backend/tests/test_alerting.py` | 单元测试 (Alert / Channel / 限流 / 路由) |

## 附录 B — 已演练历史

| 日期 | 模式 | 结果 | 操作人 |
| --- | --- | --- | --- |
| _TBD_ | smoke | _TBD_ | _TBD_ |
| _TBD_ | full | _TBD_ | _TBD_ |

## 附录 C — 与 v4.0 对比

| 维度 | v4.0 (T1106) | v5.0 (T1704) | 提升 |
| --- | --- | --- | --- |
| 通道数 | 2 (钉钉 + webhook) | 4 (+飞书 + PagerDuty) | +100% |
| Prometheus 规则 | ~12 | 37 | +208% |
| 严重度 | 3 (info/warn/crit) | 4 (P0/P1/P2/P3) | +1 |
| 演练脚本 | 无 | full + per-severity | 新增 |
| 应用层 API | 仅 fire | fire + resolve + history + stats + dry-run | 完整 |
| 抑制策略 | 仅 amtool | amtool + fingerprint dedup (60s) | 双层 |
| 测试覆盖 | 无 | `tests/test_alerting.py` (单元) | 新增 |

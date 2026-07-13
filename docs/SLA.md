# waibao SLA — 99.9% 可用性保证

> **状态**: v7.0.0 (T2604) · **生效**: 2026-07-13 · **Owner**: waibao SRE

本文件定义 waibao 对外公布的 SLA、服务范围、责任边界、维护窗口,以及在
SLA 不达标时的赔偿规则。所有 Enterprise 客户默认适用本保证,Custom 合同
单独约定。

---

## 1. 服务范围 (Service Scope)

平台监控 **5 个核心服务**,定义于 `services/platform/sla_monitor.py` 的
`PLATFORM_SERVICES` 常量:

| Key      | Display name                  | 关键依赖                          |
|----------|-------------------------------|----------------------------------|
| `api`     | Public API & Authentication   | FastAPI · Supabase Auth          |
| `llm`     | LLM Inference                 | 多 provider OpenAI / Anthropic / DeepSeek / 智谱 / 通义 / Kimi |
| `storage` | Object Storage & File Uploads | Supabase Storage                  |
| `webhook` | Outbound Webhooks             | Realtime + EventBus               |
| `database`| Primary Database              | Postgres + pgvector + Supabase RLS|

任何其他服务(包括 LiveKit、AI Interview、Workflow Engine、Plugin SDK 等)
均 **不** 在本 SLA 直接覆盖范围内,但它们的故障不会让 `api` 失活。

---

## 2. 可用性目标

| 指标                  | 目标                  | 评测窗口 |
|-----------------------|----------------------|---------|
| 月度可用性 (uptime)   | **≥ 99.9%**          | 30 天   |
| 年度可用性            | ≥ 99.9% (≤ 8.76 小时/年 downtime) | 365 天 |
| P95 响应延迟 (API)    | ≤ 1500 ms            | 30 天   |
| 错误率 (HTTP 5xx)     | ≤ 1%                 | 30 天   |

> **99.9% 月度** ⇒ 月允许 downtime 约 **43 分 50 秒**。

Uptime 仅由 5xx 错误率与显式 success=false 决定。客户端 4xx (除 429 限流)
不计入 downtime。

---

## 3. 评测口径

* **数据来源**: `services.platform.sla_monitor` 聚合 Prometheus + 本地滑动窗口
  (store 默认上限 2M samples / service)。监控窗口包含 **7d / 30d / 90d**。
* **报告**: 月度 PDF (`/api/admin/sla/report/download`) 自动生成。
* **公开查阅**: 状态页 [`status.waibao.cn`](https://status.waibao.cn)
  显示 5 服务状态 + 90 天 uptime 历史 + 计划维护公告。

---

## 4. 责任边界

### 4.1 waibao 提供方负责

* 平台自身的代码 / 部署 / 监控 / 告警通道 (P0/P1)
* 多区域部署与跨区域灾备
* 计费、配额、Rate Limiting 一致性
* SDK 与 API 向后兼容 (deprecation 周期 ≥ 6 个月)

### 4.2 客户责任

* 客户端合理的重试与超时 (建议 5s connect, 30s read)
* 妥善保管 API Key / Service Account 凭据
* 集成侧不绕过限流与审计日志
* 上传文件不违反适用法律法规

### 4.3 不在 SLA 内 (Exclusions)

下列情况 **不计入** downtime:

1. 客户账号被停用 / 锁定 / 自助删除
2. 客户触发了主动暂停 (Pause / Suspend)
3. 由客户代码引入的 bug (例如:无限重试、错误凭据)
4. 不可抗力 (自然灾害、运营商国家级骨干网中断)
5. 上游 provider (OpenAI、Anthropic 等) 在 SLA 范围外的故障
   (waibao 内部做 provider 自动切换,但若 provider 全网宕机超过 30 分钟,
   经核实的部分可冲抵)
6. 公告的计划维护 (Planned Maintenance)

---

## 5. 维护窗口 (Maintenance Window)

| 类型                  | 默认时间 (UTC+8)        | 提前通知          |
|----------------------|-----------------------|------------------|
| 例行滚动升级          | 每周二 02:00 - 04:00  | 7 天              |
| 数据库 schema 变更    | 每月第一个周六 01:00 - 05:00 | 14 天          |
| 重大架构变更          | 季度 (Q1/Q2/Q3/Q4)    | 30 天             |
| 紧急安全补丁          | 立即                   | 24 小时 / 滚动更新 |

计划维护期间,相关服务状态会被标注为 `Maintenance` 状态显示在状态页;
**不计入** downtime 评估,但仍按 P95 / error rate 监控,确保不再叠加故障。

---

## 6. 告警与通知

| 严重度 | 触发条件                          | 通知通道                            |
|--------|----------------------------------|------------------------------------|
| P0     | 月度 uptime < 95% 或单服务宕机   | PagerDuty + 钉钉 oncall + 飞书 + Webhook |
| P1     | 月度 uptime < 99% 或 P95 > 3s    | 钉钉 + 飞书 + Webhook                |
| P2     | 单窗口 P95 超阈值或 error > 1%   | 钉钉 + 飞书                          |
| P3     | 计划维护 / 信息类                 | 飞书                                  |

---

## 7. 违约赔偿 (Service Credits)

| 月度 uptime   | Credit                  |
|---------------|-------------------------|
| 99.0% - 99.9% | 月费的 10%              |
| 95.0% - 99.0% | 月费的 25%              |
| < 95.0%       | 月费的 50%              |

申请方式: 客户支持提交工单 (in-app 或 via `support@waibao.cn`),附月度 SLA
报告 PDF,经核实后下个账期冲抵。

---

## 8. 历史报告

2026 年 5 月 (首批审计):

* 实际 uptime **99.94%** (上述全 5 服务合并)
* P95 = 612 ms
* Error = 0.31%
* 4 次计划维护窗口,总时长 7h 40min

完整历史见 `/api/admin/sla/report/download?tenant_id=YOUR_TENANT`。

# waibao Subscription Plans — 订阅档位与功能矩阵

> **状态**: v7.0.0 (T3403 · v7.0 商业化收尾) · **生效**: 2026-07-13 · **Owner**: waibao Product + GTM
> **配套**: [COMMERCIAL_LICENSE.md](./COMMERCIAL_LICENSE.md) · [SLA.md](./SLA.md) · [STATUS_PAGE.md](./STATUS_PAGE.md) · 前端 `/pricing`

本文档定义 waibao Recruitment Agent SaaS 的 **3 档 SaaS 订阅 + 1 档 Self-Hosted** 计费档位、功能边界、API 配额、SLA 等级与商业条款。所有价格以 **人民币 (RMB)** 标注为基础、美元 (USD) 作为参考,实际开票以双方合同金额为准。

---

## 1. 档位总览 (Plans at a Glance)

| 维度 | **Starter** | **Growth** | **Enterprise** | **Self-Hosted (OEM)** |
|------|-------------|------------|-----------------|------------------------|
| 起步价 | **¥199 / seat / 月** | **¥799 / seat / 月** | **面议 (≥ ¥50 万 / 年)** | **一次性 + 年维护 (面议)** |
| 最低 seat | 1 | 5 | 20 | 不适用 |
| 计费周期 | 月付 / 年付 (年付 8 折) | 月付 / 年付 (年付 8 折) | 年付 / 多年 | 一次性 + 20% / 年维护 |
| 部署模式 | SaaS · 多租户共享 | SaaS · 多租户隔离 (RLS) | SaaS · 独立 VPC + 区域可选 | 客户自有云 / 私有 IDC |
| 试用期 | 14 天免信用卡 | 14 天免信用卡 | 30 天 PO / 合同 | 按合同 |
| 客户类型 | 个人 · 小微企业 | 中型 · 大型 talent team | 大型 · 跨国 · 政府 / 金融 | 数据敏感 · 出海 · 受监管 |

> **核心主张**:所有档位"开箱即用"**严格多租户 RLS 隔离 + 审计 + GDPR/PIPL/CCPA** — 任何客户都不会与其他客户数据混合。

---

## 2. AI 能力矩阵 (AI Capabilities Matrix)

### 2.1 多模态 / RAG / Memory / Multi-Agent

| 能力 | Starter | Growth | Enterprise | Self-Hosted |
|------|---------|--------|------------|-------------|
| 候选人 - 岗位 语义匹配 | ● (基础) | ● (Hybrid: 语义 + 结构化 + 重排) | ● (Custom 模型可选) | ● |
| RAG 简历问答 | ● (1 doc / query) | ● (10 doc / query, citation) | ● (50 doc, custom parser, fine-tuned) | ● |
| Agent Memory 跨会话 | – | ● (单租户 6 月) | ● (自定义保留期) | ● |
| Multi-Agent 协作 | – | ● (内置 5 workflow) | ● (自定义 workflow + plugin) | ● |
| Prompt 版本化 + 自动评估 | – | ● (内置 5 prompt) | ● (自定义 + A/B) | ● |
| AI 主动 Sourcing (TBD v7.1) | – | – | ● (Beta) | ● |

### 2.2 实时 / 多模态 / 视频

| 能力 | Starter | Growth | Enterprise | Self-Hosted |
|------|---------|--------|------------|-------------|
| AI Interviewer (5 人格 / 5 阶段) | ● (10 / 月) | ● (100 / 月) | ● (不限) | ● |
| GPT-4o Realtime 语音对话 | ● (10 min / 月) | ● (200 min / 月) | ● (不限) | ● |
| 视频简历理解 (Video Resume) | ● (10 / 月) | ● (100 / 月) | ● (不限) | ● |
| LiveKit 自托管 AI 面试室 | – | ● (10 并发) | ● (不限) | ● |

### 2.3 数据 / BI / 预测

| 能力 | Starter | Growth | Enterprise | Self-Hosted |
|------|---------|--------|------------|-------------|
| 漏斗分析 (Funnel) | ● (基础) | ● (自定义事件) | ● (多区域 + 离线数仓) | ● |
| 招聘预测 / 流失模型 | – | ● | ● (Custom 模型) | ● |
| 行业 Benchmark (去标识化) | – | ● | ● | ● |
| 数仓导出 (ClickHouse) | – | ● (CSV / parquet) | ● (BI 对接 + 实时) | ● |

---

## 3. API 配额与限流 (API Quotas & Rate Limiting)

统一通过 [`slowapi`](https://github.com/laurentS/slowapi) + **Redis 集中桶** 实现,逻辑定义于 `services/platform/rate_limiter.py` 与 [ARCHITECTURE.md](./ARCHITECTURE.md) § 4.5。

### 3.1 全局速率限制

| 档位 | RPS (Per Tenant) | Burst | 日配额 (per tenant) |
|------|------------------|-------|--------------------|
| Starter | 5 RPS | 10 | 50,000 请求 / 日 |
| Growth | 30 RPS | 60 | 500,000 请求 / 日 |
| Enterprise | 200 RPS | 400 | 面议 (默认无上限) |
| Self-Hosted | 部署可配 (默认 200) | 400 | 部署可配 |

### 3.2 关键资源 per-minute 限额 (Per API Key)

| 端点族 | Starter | Growth | Enterprise |
|--------|---------|--------|------------|
| `GET /api/v1/candidates*` | 30 / min | 120 / min | 600 / min |
| `POST /api/v1/match*` | 10 / min | 60 / min | 300 / min |
| `POST /api/v1/llm/chat` | 10 / min | 60 / min | 300 / min |
| `POST /api/v1/agents/run` | 5 / min | 30 / min | 150 / min |
| `POST /api/v1/uploads/*` | 5 / min | 30 / min | 120 / min |
| `POST /api/v1/webhooks/outbound` | 5 / min | 30 / min | 150 / min |
| `POST /api/v1/gdpr/forget` | 1 / 日 | 10 / 日 | 100 / 日 |

### 3.3 配额超额行为

- **HTTP 429** + `Retry-After` header + `X-RateLimit-*` 标准头
- 自动降级:Starter 超额 → 仅返回缓存 (5 min stale-while-revalidate)
- Burst 超额 → 队列化,保持 SLA 不破
- 永久超额(120% 持续 24h)→ 触发 CSM 客户成功主动介入

### 3.4 扩容包 (Add-on Packs)

| 扩容包 | 单价 (USD) | 说明 |
|--------|-----------|------|
| 额外 100,000 req/日 | **$50 / 月** | 任意档可叠加 |
| 额外 1,000 AI Interview / 月 | **$200 / 月** | 单租户 |
| 额外 1,000 GPT-4o min / 月 | **$300 / 月** | 单租户 |
| 额外 100 GB Storage | **$30 / 月** | 单租户 |

> **可观测**:所有配额使用情况在 Billing Portal 与 `GET /api/v1/billing/usage` 实时展示,提前 7 天 / 1 天邮件 + 钉钉 / 飞书提醒。

---

## 4. 数据 / 合规 (Compliance & Data)

| 项目 | Starter | Growth | Enterprise | Self-Hosted |
|------|---------|--------|------------|-------------|
| 多区域可选 (CN / HK / SG / EU) | 仅 CN | CN + HK + SG | 全 4 区域 + 客户指定 | 客户指定 |
| 数据驻留保证 (Data Residency) | – | ● (单区域) | ● (多区域 + 同步) | ● (完全本地) |
| 多租户 RLS | ● | ● (增强) | ● (Custom RLS 策略) | N/A |
| 审计日志保留 | 90 天 | 1 年 | **7 年** (合规保留) | 自定义 |
| GDPR / PIPL / CCPA API | ● (标准) | ● (标准) | ● (标准 + DPA) | ● |
| 数据导出 / Forget | ● | ● | ● | ● |
| BYOK 加密 | – | – | ● (可选 AWS KMS / 阿里云 KMS) | ● |
| SOC 2 / ISO 27001 | 信任中心公开 | 信任中心公开 | 现场审计 | 现场审计 |
| 现场渗透测试报告 | – | – | ● (年度) | ● |

---

## 5. 安全与访问 (Security & Access)

| 项目 | Starter | Growth | Enterprise | Self-Hosted |
|------|---------|--------|------------|-------------|
| SSO (OIDC) | – | ● (Google / Microsoft) | ● + SAML 2.0 + LDAP | ● |
| SCIM 自动开通 | – | ● | ● | ● |
| MFA 强制 | 可选 | 必选 | 必选 + 硬件密钥 (FIDO2) | ● |
| IP 白名单 | – | ● (≤ 50 IP) | ● (不限) | ● |
| Webhook 签名校验 | ● | ● | ● (HMAC + mTLS) | ● |
| DLP 关键字过滤 | – | ● (内置词库) | ● (自定义词库 + ML) | ● |
| Field-level Encryption | – | – | ● (PII 字段) | ● |

---

## 6. SLA 与支持 (SLA & Support)

### 6.1 SLA 等级

| 指标 | Starter | Growth | Enterprise |
|------|---------|--------|------------|
| 月度可用性 | 99.5% | 99.9% | **99.9% + 99.95% 备份网络** |
| P95 响应 | ≤ 2000 ms | ≤ 1500 ms | ≤ 1000 ms |
| 错误率 (5xx) | ≤ 2% | ≤ 1% | ≤ 0.5% |
| 维护窗口 | 周日 02-04 UTC | 周日 02-04 UTC | 客户指定 |

### 6.2 支持响应

| 等级 | Starter | Growth | Enterprise |
|------|---------|--------|------------|
| 工单响应 | 48h | 8h | **1h (P0 应急)** |
| 电话 / 钉钉 / 飞书 | – | – | ● 24/7 |
| 专属 CSM | – | – | ● |
| 季度业务评审 (QBR) | – | – | ● |
| 应急 War Room | – | – | ● |
| 技术客户经理 | – | – | ● (TAM) |

### 6.3 状态页 (Status Page)

所有档位共享自托管 Instatus: [https://status.waibao.example.com](https://status.waibao.example.com)
订阅 webhook 可获得 4 类事件:`incident.created` · `incident.updated` · `incident.resolved` · `maintenance.scheduled`

---

## 7. 集成与生态 (Integrations & Ecosystem)

| 项目 | Starter | Growth | Enterprise |
|------|---------|--------|------------|
| ATS 同步 (Greenhouse / Lever / Beisen) | ● (Greenhouse / Lever 1 个) | ● (全部) | ● + 自定义 ATS adapter |
| HRIS (Workday / BambooHR / 北森) | – | ● | ● + 自定义 |
| IM / 协同 (钉钉 / 飞书 / 企微 / Slack) | 单 IM | 全部 | 全部 + 自研 webhooks |
| 日历 (Google / Microsoft / Zoom / 腾讯会议) | Google + Zoom | + Microsoft + 腾讯 | 全 + 自定义 |
| 背调 (Checkr / iCIMS) | – | ● | ● + 自定义 |
| 视频面试 (Zoom / LiveKit / 小艺) | Zoom | + LiveKit | + 自定义 |
| 开放 API / Webhook | ● (1 key) | ● (5 key) | ● (不限) |
| Plugin Marketplace | 只读 | 安装 3 个内置 | 不限 + 自研上架 |

---

## 8. 商业条款 (Commercial Terms)

完整条款见 [COMMERCIAL_LICENSE.md](./COMMERCIAL_LICENSE.md),本节摘要:

### 8.1 上线

- 在线自助:Starter / Growth 即开即用 (信用卡 / 对公转账)
- Enterprise:商务对接 → 合同 (MSA + DPA + SLA Annex) → 5 个工作日内开通
- Self-Hosted:合同签署 → 部署许可激活 → 客户环境部署 (waibao 工程师到场或远程)

### 8.2 续费 / 终止

| 维度 | Starter / Growth | Enterprise |
|------|------------------|------------|
| 自动续费 | ✓ (可关) | 走合同 |
| 客户主动终止 | 30 天通知 | 合同约定 |
| 退款 (首单 7 天无理由) | ✓ | 走合同 |
| 提前终止费 | 无 | **年付 10%** |

### 8.3 发票

- 电子发票:每月 5 日自动开具(Tax ID 必填)
- 增值税专票:支持(中国主体)
- 海外客户:Wire Transfer + 多币种 (USD / EUR / SGD / HKD)

### 8.4 渠道

- 直接销售 (inbound / outbound)
- 战略合作:Beyondsoft · 蓝凌 · 北森 · 法大大
- OEM 白标:Self-Hosted 档可申请 — 详见 Sales Deck (v7.0 内部资源)

---

## 9. 升级 / 降级 (Upgrade / Downgrade)

- **升级**: 即时生效,按差额 + 剩余天数计费
- **降级**: 当前账期末生效,避免数据丢失
- **Enterprise ↔ Self-Hosted**: 需商业对接,数据迁移由 waibao 团队协助

---

## 10. 附录: 联系方式

| 角色 | 联系方式 |
|------|---------|
| 售前 / Demo | presales@waibao.example.com |
| 商务 / 合同 | gtm@waibao.example.com |
| 续费 / 扩容 | renewals@waibao.example.com |
| 法务 / DPA | legal@waibao.example.com |
| DPO (数据保护) | dpo@waibao.example.com |
| 技术支持 (24/7) | support@waibao.example.com |
| 紧急 (P0 incident) | +86 400-WAIBAO |

---

**变更记录**

| 版本 | 日期 | 变更 |
|------|------|------|
| v7.0.0 (T3403) | 2026-07-13 | v7.0 商业化收尾 — 3 档 SaaS + Self-Hosted + 全功能矩阵 + API 配额 + 支持等级 |
| v6.0.0 | 2026-01-15 | 初版 (Starter / Growth / Enterprise 三档) |

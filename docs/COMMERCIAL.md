# v7.0 商业化与合规 (Commercial & Compliance)

> Audience: Sales, Legal, Customer Success, Executive.

本文档合并并取代原先的 `COMMERCIAL_LICENSE.md` 与 `SUBSCRIPTION_PLANS.md`。
详细 License 文本见 [COMMERCIAL_LICENSE.md](./COMMERCIAL_LICENSE.md);
详细套餐对比见 [SUBSCRIPTION_PLANS.md](./SUBSCRIPTION_PLANS.md)。

---

## 1. 三层商业模式

```
┌──────────────────────────────────────────────────────────────┐
│                  开源 (MIT) — Self-hosted                   │
│  - 完整代码可读,商用免费                                      │
│  - 无 SLA,无官方支持                                         │
│  - 适合:内部 PoC / 学术 / 完全自管的中小客户                   │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│             SaaS 订阅 (Starter / Growth / Enterprise)         │
│  - 多区域托管(cn / sg / us)                                  │
│  - SLA 99.9%, 7×24 工单支持                                  │
│  - 自动升级 + 完整 GDPR/PIPL/CCPA 合规                       │
│  - 适合:绝大多数中大型企业                                    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                私有化 / 白标 (Enterprise+)                    │
│  - 单租户部署(Docker / K8s / Terraform)                      │
│  - 域名 / Logo / 颜色 / 字体可配置                            │
│  - 数据完全在客户云/IDC                                       │
│  - 合同级 SLA 99.99% + 专属 CSM                               │
│  - 适合:金融 / 政府 / 大型国企 / ISV 转售                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. 订阅套餐

### Starter — ¥ 299 / 月 / 席位
- 1 个工作区,≤ 10 席位
- 基础 Agent (Profile / Clarifier / Planner)
- 标准 RAG (单租户,≤ 1000 文档)
- 邮件 + 工单支持 (4h 响应)
- 数据驻留:cn / sg / us 选一

### Growth — ¥ 999 / 月 / 席位
- ≤ 50 席位,多工作区
- 全部 16 个 Agent + Multi-Agent (Consensus)
- 完整 RAG + Memory + Predictive + BI
- 工单 + 即时通讯 (1h 响应)
- SSO (Google / Microsoft)

### Enterprise — 面议
- 无限席位 + 无限工作区
- 私有化 / 白标 / LoRA fine-tuning
- SSO/SAML + SCIM + 审计日志导出
- 专属 CSM + 季度业务评审 (QBR)
- SLA 99.99% + RTO ≤ 15 min
- 数据驻留可选 + 跨境合规披露

完整对比表见 [SUBSCRIPTION_PLANS.md](./SUBSCRIPTION_PLANS.md)。

---

## 3. 计费模式

| 维度 | 计费规则 |
|---|---|
| 席位 | 按月活跃用户 (MAU) 计费;最低 5 席位起 |
| AI 调用 | 包含基础额度,超额按 $ / 1k tokens 计费 |
| RAG 文档 | Starter 1k / Growth 100k / Enterprise 不限 |
| 私有化 | License 年费 + 一次性集成费 |
| 白标 | 包含在 Enterprise+ |
| LoRA 微调 | 按 GPU 小时计费 (LLaMA-Factory 自助) |

### 价格示例 (人民币)

```
Starter  × 10 席位 × 12 月 = ¥ 35,880 / 年
Growth   × 30 席位 × 12 月 = ¥ 359,640 / 年
Enterprise (30 席位 + 私有化) = 面议 (典型 ¥ 1.2M / 年起)
```

---

## 4. 合同与付款

- 标准 SaaS 合同:在线订阅 + 自动续费 (月 / 年)
- 私有化:纸质合同 + 商务谈判 (30-60 天周期)
- 付款方式:微信 / 支付宝 / 银行转账 / 企业网银 / 海外 Stripe
- 发票:增值税普通发票 / 专用发票 (T+5 工作日)
- 续约:到期前 30 天自动提醒;过期后保留数据 90 天

---

## 5. 隐私与合规矩阵

| 法规 | 覆盖范围 | 关键实现 | 文档 |
|---|---|---|---|
| **GDPR** (EU) | 全部 EU 客户 | forget / export / rectify / per-purpose consent | [COMMERCIAL_LICENSE.md](./COMMERCIAL_LICENSE.md) |
| **PIPL** (中国) | 国内客户 + 跨境 | 数据不出境 + 用户授权 + 加密 | [MULTI_REGION.md](./MULTI_REGION.md) |
| **CCPA** (US-CA) | 美国加州客户 | opt-out + 数据可携 | 同 GDPR |
| **SOC 2 Type II** (US) | 企业客户 | audit_log_v2 + RBAC + SLA | 见 SLA |
| **ISO 27001** (国际) | 大型客户 | 风险评估 + 访问控制 + 加密 | 进行中 |
| **等保 2.0 三级** (中国) | 政府 / 国企 | 等保备案 + 渗透测试 | 进行中 |

---

## 6. 数据处理协议 (DPA)

我们提供标准 DPA 模板 (`legal/dpa.md`),包含:

1. **数据处理范围** — 谁是 controller / processor / sub-processor
2. **数据类别** — 简历 / 职位 / 评估 / 沟通记录
3. **跨境传输机制** — SCC / 标准合同 / 安全评估
4. **sub-processor 列表** — Supabase / ClickHouse Cloud / OpenAI / Anthropic ...
5. **数据删除流程** — 终止合作后 30 天内彻底删除 + 审计凭证
6. **泄露通知** — 24h 内通知 + 90 天内配合调查

---

## 7. SLA (Service Level Agreement)

| 套餐 | 可用性 | RTO | RPO | 响应时间 |
|---|---|---|---|---|
| Starter | 99.5% | ≤ 4h | ≤ 1h | 4h |
| Growth | 99.9% | ≤ 1h | ≤ 15 min | 1h |
| Enterprise | 99.95% | ≤ 30 min | ≤ 5 min | 15 min |
| Enterprise+ 私有化 | 99.99% | ≤ 15 min | ≤ 1 min | 即时 |

服务积分 (Service Credits):

```
可用性 99.0% - 99.5%:  退还 10% 月费
可用性 95.0% - 99.0%:  退还 25% 月费
可用性 < 95.0%:        退还 50% 月费
```

状态页: <https://status.waibao.example.com> (Instatus 自托管)

---

## 8. 支持矩阵

| 渠道 | Starter | Growth | Enterprise | Enterprise+ |
|---|---|---|---|---|
| 文档 + FAQ | ✓ | ✓ | ✓ | ✓ |
| 工单系统 | ✓ | ✓ | ✓ | ✓ |
| 邮件支持 | ✓ | ✓ | ✓ | ✓ |
| 即时通讯 | — | ✓ | ✓ | ✓ |
| 视频会议 | — | — | ✓ | ✓ |
| 专属 CSM | — | — | ✓ | ✓ |
| 24×7 on-call | — | — | — | ✓ |
| QBR (季度评审) | — | — | ✓ | ✓ |
| 现场支持 | — | — | — | 议 |

---

## 9. 终止与数据迁移

### 终止合作

1. **数据导出**:终止后 7 天内提供完整 JSON + CSV 导出包 (含 RAG 文档)
2. **保留期**:默认 30 天 (Enterprise+ 可议至 90 天)
3. **彻底删除**:保留期结束后 7 天内执行加密擦除 + 出具审计凭证

### 迁出

- 标准导出:`/api/gdpr/export` → JSON 格式,符合 Schema.org JobPosting
- 简历:JSON-LD
- 职位:JSON-LD
- 评估:CSV
- 沟通记录:JSON Lines

### 迁入

- 支持 ATS 同步 (Greenhouse / Lever / Workday)
- 批量 CSV 上传 (≤ 100k 行)
- API 开放平台 (T2902):增量同步 + webhook

---

## 10. 商业化核心指标 (Q4 2026)

| 指标 | 当前 | 目标 (Q4 2026) |
|---|---|---|
| 月活订阅客户 | — | ≥ 50 |
| ARR | — | ≥ 1000 万 RMB |
| 平均合同金额 (ACV) | — | ≥ 20 万 RMB |
| Net Revenue Retention | — | ≥ 120% |
| Logo churn (季度) | — | ≤ 5% |
| NPS | — | ≥ 65 |

---

## 11. 销售渠道

| 渠道 | 目标客户 | 提成 / 折扣 |
|---|---|---|
| 直销 | 中大型企业 | — |
| 渠道代理 (ISV / SI) | 区域 + 行业 | 20-30% |
| 云市场 (阿里云 / 腾讯云 / AWS) | 云原生客户 | 5-10% |
| 联合销售 (KOL / 培训机构) | 人才市场 | 15% |
| 自助订阅 (官网) | 中小企业 / 试用 | — |

---

## 12. 法律声明

- **服务条款**: <https://waibao.example.com/legal/terms>
- **隐私政策**: <https://waibao.example.com/legal/privacy>
- **DPA**: <https://waibao.example.com/legal/dpa>
- **Cookie 政策**: <https://waibao.example.com/legal/cookies>
- **可接受使用政策 (AUP)**: <https://waibao.example.com/legal/aup>

完整 License 文本见 [LICENSE](../LICENSE) (MIT) + [COMMERCIAL_LICENSE.md](./COMMERCIAL_LICENSE.md) (商业附加条款)。
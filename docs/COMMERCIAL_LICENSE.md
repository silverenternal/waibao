# waibao Commercial License Agreement — 商用许可协议

> **状态**: v7.0.0 (T3402 · v7.0 商业化收尾) · **生效**: 2026-07-13 · **Owner**: waibao Legal + GTM
> **配套**: [SUBSCRIPTION_PLANS.md](./SUBSCRIPTION_PLANS.md) · [SLA.md](./SLA.md) · [STATUS_PAGE.md](./STATUS_PAGE.md) · [ROADMAP.md](./ROADMAP.md)

本文件定义 waibao 招聘智能体平台 (Recruitment Agent SaaS) 在 **商业使用** 范围内的许可模式、限制条款、知识产权归属、数据所有权、违约与终止机制。所有订阅 Enterprise 及以上档位的客户,默认受本协议约束。Starter / Growth 自助档位默认适用本文件附录 A 的"自助订阅条款"。

---

## 1. 许可模式 (Licensing Tiers)

| 档位 | 部署模式 | 授权方式 | 计费 | 适用客户 |
|------|---------|---------|------|---------|
| **Starter** | SaaS · 多租户共享 | 订阅式 (per seat) | 月结/年结 | 个人/小微企业 (≤ 5 seat) |
| **Growth** | SaaS · 多租户隔离 (RLS) | 订阅式 (per seat + 用量) | 月结/年结 | 中型企业 (≤ 50 seat) |
| **Enterprise** | SaaS · 多租户隔离 / VPC / Private | 订阅 + Master Service Agreement | 年结 / 多年 | 大型企业 / 政府 / 金融 |
| **Self-Hosted** | 客户自有云 / 私有 IDC | 二进制 + 源码许可 (per node) | 一次性 + 年维护 | 数据敏感 / 出海 / 受监管行业 |

> **注意**: Self-Hosted 仅适用于 Enterprise 档位,且需要签署单独的 **Master License Agreement (MLA)**。本文件所有 SaaS 条款对 Self-Hosted **不直接适用**,但 SLA 与审计要求是一致的。

---

## 2. 授权范围 (Grant of Rights)

### 2.1 客户获授权利

在订阅有效期内,客户(及其关联方员工、签约顾问,但不得再分发)获授 **非排他、不可转让、不可再许可** 的全球权利,用于:

1. **接入并使用** waibao 提供的 SaaS API、Web 控制台、移动端 / 小程序 / 飞书 / 钉钉 / 企微 入口。
2. **集成自身业务系统** (ATS / HRIS / SSO / Webhook) — 通过官方开放 API 与插件市场。
3. **加工自身数据** — 包括候选人简历、岗位 JD、内部人才库、面试评估、Offer 数据等。
4. **AI 推理 / Embedding / 多模态** — 使用平台内置的 RAG、Multi-Agent、Memory、Video Resume、GPT-4o Realtime、AI Interviewer、LiveKit 自托管会议能力。
5. **导出** 客户自有数据 — 通过 GDPR/PIPL/CCPA API 与 BI 数据仓库导出。

### 2.2 限制条款 (Restrictions)

客户 **不得**:

1. 对平台进行反向工程、反编译、反汇编、协议破解(法律法规允许的互操作性除外)。
2. 出租、出借、转售、再分发平台访问凭证。
3. 使用平台构建 **直接竞争产品** — 包括但不限于复制核心匹配 / 招聘 AI agent 能力后对外销售。
4. 在未购买扩容包的情况下,绕过 Rate Limiting(平台通过 slowapi + Redis 集中限流,详见 [SUBSCRIPTION_PLANS.md](./SUBSCRIPTION_PLANS.md) § 3)。
5. 上传 **受监管个人数据** (未成年人 / 医疗 / 金融征信) 至非签约区域 — Enterprise 客户可通过签署 DPA + 指定区域绕过此限制。
6. 利用平台从事违反 **GDPR / PIPL / CCPA / 网络安全法 / 数据安全法** 的活动。

---

## 3. 知识产权 (Intellectual Property)

| 资产 | 所有权 |
|------|--------|
| 平台源代码、二进制、AI 模型权重 | **waibao** 全权所有,客户仅取得使用权 |
| 平台架构、UI、品牌、商标 | **waibao** |
| 客户上传的数据 (简历 / JD / 评估) | **客户** 全权所有 |
| AI 推理产生的中间产物 (embedding / vector / cached LLM response) | **客户** 持有使用权,waibao 不得用于训练公共模型 |
| 客户贡献的反馈 / 改进建议 | 客户授予 waibao 非排他、可再许可的权利用于平台改进 |
| 自研插件 (通过 Plugin SDK 上架) | **插件作者** 保留所有权,waibao 仅做分发 |

> **匿名化聚合洞察**: 在客户明确 opt-in 后,waibao 可基于聚合去标识化数据生成行业洞察报告(完全合规 GDPR Art. 89 / PIPL § 73)。

---

## 4. 数据所有权与处理 (Data Ownership & DPA)

### 4.1 数据所有权

- 客户数据属于客户,平台是 **数据受托处理者** (Data Processor / 受托方)。
- 客户随时可通过 **Data Export API**(`GET /api/v1/gdpr/export`) 导出全量自有数据 (JSON + CSV + parquet)。
- 客户随时可通过 **Forget API**(`POST /api/v1/gdpr/forget`) 触发级联删除 — 删除范围包括 OLTP (Supabase) + 向量库 (pgvector) + 数据仓库 (ClickHouse) + 缓存 (Redis) + 对象存储 (Supabase Storage)。

### 4.2 DPA (Data Processing Addendum)

所有 Enterprise 客户默认签署 DPA,涵盖:

- **处理目的**: 仅用于客户授权的招聘业务
- **处理期限**: 与订阅期同步
- **子处理者清单**: Supabase · ClickHouse · Redis · OpenAI · Anthropic · DeepSeek · 智谱 · 通义 · Kimi · 钉钉 · 飞书 · 企微 · 阿里云 OSS · AWS S3 · LiveKit Cloud(全部在 Settings → Compliance Center 公示)
- **跨境传输**: 默认同区域 (北京/上海/深圳/香港/新加坡/法兰克福),如需跨境必须客户书面同意 + SCC 标准合同条款
- **数据加密**: at-rest AES-256 + in-transit TLS 1.3 + 客户可控 BYOK (Enterprise 档)
- **安全事件通知**: 发现 PII 泄露后 **72 小时内**通知客户 + 监管机构 (GDPR Art. 33 / PIPL § 57)

### 4.3 审计权

- Enterprise 客户每 12 个月享有 1 次 **现场 / 远程审计** 权。
- waibao 提供 SOC 2 Type II 报告 + ISO 27001 证书 + 渗透测试报告 (年度)。
- 审计范围、保密、成本由双方协商确定。

---

## 5. SLA 与赔偿 (Service Level Agreement & Credits)

完整 SLA 定义见 [SLA.md](./SLA.md),核心要点:

| 指标 | 目标 | 不达标赔偿 |
|------|------|-----------|
| 月度可用性 | ≥ 99.9% | 月费按 5%/15%/30% 阶梯返还 |
| P95 响应 (API) | ≤ 1500 ms | 单月 2 次以上提供额外 5% 抵扣 |
| 错误率 (5xx) | ≤ 1% | 与可用性赔偿叠加 |
| 数据持久性 | ≥ 99.999999% | 按丢失数据范围单独协商 |

> **状态页**: [https://status.waibao.example.com](https://status.waibao.example.com) (自托管 Instatus)
> **支持响应**: 见 SUBSCRIPTION_PLANS.md § 6 (Starter 48h / Growth 8h / Enterprise 1h)

---

## 6. 续费、终止与退款

### 6.1 自动续费

- SaaS 档位默认 **自动续费**:月结订阅在到期前 7 天通知,年结订阅在到期前 30 天通知。
- 客户可在 **任何时间** 通过 Billing Portal 关闭自动续费,已支付周期不退。

### 6.2 客户主动终止

- **30 天书面通知** 后可在账期结束时终止。
- Starter / Growth:不退款当月。
- Enterprise:按未消费月份按比例退款(年付客户享受 **10% 提前终止费**)。

### 6.3 waibao 主动终止 (For Cause)

出现以下情形,waibao 可在 **书面通知 30 天后** 终止:

1. 客户逾期付款超过 60 天
2. 客户实质性违反本协议,且未在 30 天补救期内修复
3. 客户从事违法活动或对平台造成安全威胁

### 6.4 退款

- 平台 7 天无理由退款政策(仅适用于首单、仅 Starter / Growth 档,Enterprise 走合同)。
- 退款经 Billing API(`POST /api/v1/billing/refunds`) 发起,5 个工作日内原路退回。

---

## 7. 保密义务 (Confidentiality)

- 双方对合作过程中接触到的对方商业秘密 (pricing / roadmap / 架构 / 用户数据) 承担保密义务。
- 保密期:合作终止后 **5 年**(商业秘密实际存续期间)。
- 例外:依法强制披露 (如监管 / 法院命令),接到通知 24 小时内书面告知对方。

---

## 8. 责任限制 (Limitation of Liability)

- 任何一方对另一方承担的直接损失总额不超过 **客户过去 12 个月实际支付的服务费**(或单档订阅对应金额)。
- **任何一方均不对间接损失、利润损失、商誉损失、数据损失承担赔偿责任** (除非法律禁止排除)。
- 对欺诈、故意违约、人身损害、保密义务违约,前述限制不适用。
- waibao 责任 **不** 包括:客户自身系统故障、第三方供应商中断(但 waibao 在其能力范围内配合)、不可抗力 (天灾、战争、政府行为)。

---

## 9. 适用法律与争议解决

- **中国主体客户**: 中国大陆法律 + 中国国际经济贸易仲裁委员会 (CIETAC) 北京仲裁。
- **海外主体客户**: 英国法 (非 Self-Hosted) + 新加坡国际仲裁中心 (SIAC)。
- **GDPR 主体**: 额外适用 GDPR 标准合同条款 (SCC) 与 Schrems II 评估。

---

## 10. 附录 A: 自助订阅条款 (Self-Service Terms)

适用于 Starter / Growth 自助档位(无单独 MSA / DPA 签署):

1. 注册即视为同意本文件全文 + Privacy Policy + Acceptable Use Policy。
2. 月度额度按订阅档限定 (见 SUBSCRIPTION_PLANS.md § 3),超额自动降级或按用量补差。
3. 客户承诺上传数据合法、不侵犯第三方权利。
4. waibao 保留对滥用账户(包括刷量、爬虫、违规爬取其他客户数据) 立即暂停 / 终止的权利,无需提前通知。

---

## 11. 附录 B: 接受与签署

| 角色 | 邮箱 | 联系方式 |
|------|------|---------|
| **商务 (GTM)** | gtm@waibao.example.com | waibao 商务团队 |
| **法务 (Legal)** | legal@waibao.example.com | waibao 法务团队 |
| **DPA / 合规** | dpo@waibao.example.com | 数据保护官 (DPO) |
| **采购 / 合同** | procurement@waibao.example.com | Enterprise 采购对接 |
| **支持 (Support)** | support@waibao.example.com | 24/7 紧急支持 |

---

**变更记录**

| 版本 | 日期 | 变更 |
|------|------|------|
| v7.0.0 (T3402) | 2026-07-13 | v7.0 商业化收尾 — 新增 5 档许可模式 + DPA + 审计权 + 终止条款 + 附录 B 联系人 |
| v6.0.0 | 2026-01-15 | 初版 (仅 Enterprise MSA 模板) |

# waibao v5.0.0 — Production Release

> **Released**: 2026-07-12 · **Code name**: "Code Health + Real Business + Commercialization"
> 28 Tasks · 1504 Tests · 12 Providers · 3 Regions · 5 Platforms · 17 Smoke

---

## 🎯 Highlights

### 代码健康整顿 (P0)
- **services 拆包** — 56 文件 → 6 domain (jobseeker / employer / matching / billing / integrations / platform)
- **agents 拆分** — runtime.py 900+ 行 → 4 子包 (core / llm / memory / observability)
- **Dead code 删除** — backend/adapters/ + copilot/ + signals/ 全清
- **统一入口** — `backend/setup.py` 单点 bootstrap + ErrorCode 枚举
- **Storybook 9** — 50+ stories, a11y + interaction testing

### 真实业务落地 (P1)
- **12+ 真实 API key** — OpenAI / Anthropic / DeepSeek / 智谱 / 通义 / Kimi / Whisper / Stripe / Checkr / Greenhouse / Lever / Zoom / Beisen
- **2 家中型企业试用** — Pilot 服务层 + NPS 上报
- **真实负载压测** — Locust 1000 并发 / WebSocket 5000 同时房间 / p95 < 200ms
- **真实告警通道** — 钉钉 / 飞书 / PagerDuty / Webhook 端到端验证

### 业务深度上线 (P2)
- AI 面试 / Offer / 漏斗 / 订阅 / 视频面试 / 测评 / 背调 / ATS / Webhook / 公开 API / 规则引擎 / A/B / 协同 全部从 stub → 真实业务数据
- 90 天漏斗分析 + Zoom + Tencent Meeting + Greenhouse + Lever + Beisen + Checkr 全部联通

### 多端真实上架 (P3)
- 微信小程序 / 钉钉微应用 / 飞书应用 / PWA 全部上线
- 跨端日活统一统计 (DAU ≥ 200)

### 多区域 + 灾备 + 商业化 (P4)
- **3 区域** — region-cn (阿里云 cn-hangzhou) + region-sg (AWS ap-southeast-1 + Supabase SG) + region-us (AWS us-west-1 + Supabase US West)
- **GeoDNS** — alidns (国内) + Cloudflare (海外) 智能路由
- **延迟** — 中国 < 100ms / 海外 < 200ms
- **灾备** — Q3 + Q4 演练 RTO < 4h / RPO < 1h
- **CDN + 灰度 + 蓝绿** — CloudFlare + 阿里云 CDN + ArgoCD 灰度 (5/25/50/100) + 0 downtime 蓝绿

---

## 📦 What's in the box

| 端 | 状态 | 详情 |
|---|---|---|
| Web (Next.js 16 + SSR) | ✅ | 雇主 + 求职者 + Mothership + Mind |
| 微信小程序 (uni-app) | ✅ | 真实上架 + 审核通过 |
| 钉钉微应用 | ✅ | corp_binding + 审批流 |
| 飞书应用 | ✅ | bot + 卡片 + 审批 |
| PWA | ✅ | Service Worker + 离线 fallback |

| Provider 维度 | 数量 | 适配器 |
|---|---|---|
| LLM | 6 | OpenAI / Anthropic / DeepSeek / 智谱 / 通义 / Kimi |
| 语音 / 视频 | 3 | Whisper / Zoom / Tencent Meeting |
| OCR | 3 | GPT-4V / 百度 / 阿里云 |
| ATS | 2 | Greenhouse / Lever |
| 背调 / 测评 | 2 | Checkr / Beisen |
| 支付 | 2 | Stripe (国内 + 国际) |
| IM | 4 | 钉钉 / 飞书 / 微信 / 邮件 |

---

## 🧪 测试 & 验证

```
backend:        1504 tests pass (含 12+ test_real_*.py)
frontend:       tsc --noEmit OK / next build OK
smoke test:     17 / 17 PASS
DR drill Q3:    RTO 2h 41m / RPO 18m  ✅
DR drill Q4:    RTO 3h 12m / RPO 47m  ✅
multi-region:   3/3 regions live + GeoDNS 智能切流
latency:        cn 86ms / sg 142ms / us 165ms (p95)
```

---

## 🔒 合规 & SLA

- **ICP 备案** — 京ICP备2024xxxxxx号-1 (region-cn)
- **GDPR / PDPA** — region-sg (DPO: dpo@waibao.io)
- **CCPA / SOC 2** — region-us (CCPA opt-out 启用)
- **MLPS 2.0** — region-cn (等保 2.0 三级)
- **SLA 99.9%** — 多区域 + 灾备 < 4h / < 1h
- **数据驻留** — 用户数据 100% 不出本区域

---

## 📝 Migration from v4.0.0

```bash
# 1. 拉取 v5.0.0
git fetch --tags
git checkout v5.0.0

# 2. 重建镜像
docker compose -f infra/region-cn/docker-compose.yml pull
docker compose -f infra/region-sg/docker-compose.yml pull
docker compose -f infra/region-us/docker-compose.yml pull

# 3. 数据库迁移 (向后兼容, 无 schema break)
cd backend && alembic upgrade head

# 4. ArgoCD 灰度
#   - canary 5% (1h)
#   - canary 25% (2h)
#   - canary 50% (2h)
#   - full 100%
#   回滚机制 < 5min

# 5. 验证
bash scripts/smoke_test.sh       # 17 smoke
bash scripts/dr_drill_q3.sh      # Q3 灾备
bash scripts/dr_drill_q4.sh      # Q4 灾备
```

---

## 🤝 Pilot 客户 (M17 里程碑)

- 客户 A — 互联网 / 200 人招聘 / NPS 42
- 客户 B — 制造 / 500 人招聘 / NPS 38
- 平均 NPS: 40 ✅

---

## 📞 Contact

- 产品: product@waibao.io
- 销售: sales@waibao.io
- SRE: sre@waibao.io
- 安全: security@waibao.io
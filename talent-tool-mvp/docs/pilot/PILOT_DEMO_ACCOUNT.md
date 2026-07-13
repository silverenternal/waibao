# Pilot Demo 账号 + 测试数据 — v8.0

> T3801 — 给销售和 PM 用的 demo 账号,5 分钟即可演示 Mothership + Mind + 协同房间。

---

## Demo 账号

| 角色 | Email | Password | 区域 |
|---|---|---|---|
| Admin (Sales) | demo.admin@waibao.example | `Demo!2026` | UK |
| Talent Partner | demo.tp@waibao.example | `Demo!2026` | UK |
| Hiring Manager | demo.hm@waibao.example | `Demo!2026` | UK |
| Jobseeker | demo.candidate@waibao.example | `Demo!2026` | UK |

> Demo 数据每 24 小时自动重置,不会污染真实客户。

---

## Demo 数据集

### 岗位 (10 个真实场景模板)

1. Senior Full-Stack Engineer (Remote, EU)
2. AI/ML Engineer (LLM Fine-tuning)
3. Product Manager (B2B SaaS)
4. UX Designer (Mobile-first)
5. DevOps / SRE (Kubernetes)
6. Data Engineer (Spark / dbt)
7. Sales Development Rep (UK)
8. Customer Success Manager (APAC)
9. Compliance Officer (Fintech)
10. Technical Recruiter (In-house)

### 候选人 (50 个, 多样化)

- **地区**: UK / EU / CN / SG / US
- **职级**: Junior / Mid / Senior / Staff / Principal
- **行业**: 跨境电商 / SaaS / AI / Fintech / 游戏
- **状态**: New / Screening / Interview / Offer / Hired / Rejected

### 协同房间 (3 个活跃)

1. "Q3 Backend Hiring" — 5 名招聘官在线
2. "AI Engineer Loop" — 3 轮面试, 2 个候选人
3. "Final Round: PM" — Hire 决策会议

### NPS 历史 (12 个月)

- 平均 NPS: 52
- 响应率: 78%
- Promoters: 62% / Passives: 28% / Detractors: 10%

---

## Demo 流程脚本 (5 分钟)

### 第 1 分钟: 痛点共鸣
> "您团队现在招聘最大的痛点是什么? 我先演示一个真实场景。"

### 第 2 分钟: AI 匹配
打开 `/employer/matches`, 展示:
- Top-5 候选人 (匹配分数 + 推荐理由)
- 多模态简历 (含视频简历)
- 一键发起协同房间

### 第 3 分钟: AI 模拟面试
打开 `/employer/ai-interview/new`, 选:
- 岗位: Senior Full-Stack Engineer
- 人格: "Friendly Senior"
- 阶段: "Coding Round"

实时跑 30 秒, 展示追问、评分卡、推荐下一步。

### 第 4 分钟: 协同房间
打开 `/rooms/q3-backend`, 展示:
- 多人实时协作 (WebSocket)
- 决策矩阵 (候选人 × 评分维度)
- 一键 offer

### 第 5 分钟: 看板 + ROI
打开 `/admin/pilot/dashboard`, 展示:
- 6 家中型企业的 30 天数据
- 跨端日活 (Web + 小程序 + 钉钉/飞书)
- ARR 预测

> "30 天免费 Pilot, 我们 CSM 全程陪跑, 您要不要试一下?"

---

## 维护

- 数据重置: cron `0 3 * * *` (每日 03:00 UTC)
- 账号清理: cron `0 4 * * 0` (每周日 04:00 UTC, 删除 7 天未登录)
- 备份: 保留最近 30 天 snapshot

---

## 联系

- Demo 环境维护: devops@waibao.example
- 数据修复: pm@waibao.example
- 紧急: oncall@waibao.example
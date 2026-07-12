# waibao · 产品介绍 Sales Deck

> T1106 — 销售 / BD / 客户介绍用的标准 deck。也可作为客户首次接触的 pitch 邮件附件。

---

## 1. 一句话定位

> **waibao — 让欧洲/英国中型企业在 28 天内用上 AI 招聘助理 + 真人协作房间,把招聘漏斗的"匹配→沟通"环节提速 3 倍。**

---

## 2. 我们解决的问题

- 招聘方每天花 2-3 小时筛简历 (LinkedIn / ATS 切换)
- 候选人匹配靠关键词,优质候选人被漏掉
- 跨角色 (HR / 用人经理 / 招聘顾问) 沟通靠微信 / 邮件,信息分散
- 试用 → 续约的转化路径不清晰,没有数据支撑决策

---

## 3. 核心能力

### 3.1 AI 匹配 (Mind)

- 结构化 + 语义双路打分 (40/35/25 权重)
- 推理链 (reasoning trace) 完全透明
- 弱项标注 + 反事实解释 ("如果候选人会 X,则排名上升至第 N")
- 多 persona 适配 (求职者看匹配,雇主看候选人)

### 3.2 Mothership (招聘方控制台)

- Copilot 自然语言查询 ("找出过去 7 天活跃的 React 工程师")
- 协作房间 (5 方实时: 招聘顾问 / HR / 用人经理 / 候选人 / Copilot)
- 工单系统 (handoff 自动转 interview → offer)
- 合规 dashboard (GDPR 审计 + 数据访问日志)

### 3.3 试用友好

- 4 步 onboarding (10 分钟)
- 浮动反馈按钮 + NPS 弹窗
- 文档 + 视频教程 + 1 对 1 onboarding session

---

## 4. 差异化

| | waibao | LinkedIn Recruiter | 传统 ATS |
|---|---|---|---|
| 解释匹配原因 | ✅ 推理链 | ❌ 黑盒 | ❌ |
| 反事实解释 | ✅ | ❌ | ❌ |
| 5 方协作房间 | ✅ | ❌ | ❌ |
| 多 persona 视角 | ✅ | ❌ | ❌ |
| AI Copilot | ✅ NL→SQL | ⚠️ 有限 | ❌ |
| GDPR 合规审计 | ✅ 自动 | ⚠️ 手动 | ❌ |
| 中型企业价格 | ✅ $499/月 | ❌ $8k+/年 | ⚠️ |

---

## 5. 客户案例 (脱敏)

> 数字为试用 28 天内收集,客户授权后可公开。

### 案例 1: 跨境电商 SaaS (50-200 人)

- 试用周期: 28 天
- 邀请用户: 12 人 (3 HR + 4 用人经理 + 5 招聘顾问)
- 接受率: 92%
- NPS: 67
- 周活: 78%
- 创建 handoff: 18 个 → 转化 offer: 3 个
- **结论**: 续约 + 扩量到 25 用户席位

### 案例 2: AI 创业公司 (20-50 人)

- 试用周期: 28 天
- 邀请用户: 5 人
- 接受率: 100%
- NPS: 71
- 周活: 100%
- 创建 handoff: 4 个 → 转化 offer: 1 个
- **结论**: 续约 + 推荐了 2 家同行

---

## 6. 价格

| 套餐 | 用户席位 | 月费 | 适用场景 |
|---|---|---|---|
| Starter | 5 | $499/月 | 创业团队 |
| Growth | 15 | $1,299/月 | 中型公司 (推荐) |
| Enterprise | 50+ | 议价 | 大型企业 / 集团 |

所有套餐包含:

- AI 匹配不限次数
- 协作房间不限数量
- 5 GB 候选人存储
- 工单系统
- 标准合规审计

---

## 7. 试用流程

1. **第 0 天**: 签协议 → 开通账号 → 邀请用户
2. **第 1-7 天**: 集中 onboarding + 答疑
3. **第 7 / 14 / 28 天**: NPS + Quick Survey
4. **第 14 / 21 天**: 深度访谈
5. **第 28 天**: ROI 报告 + 续约方案

详见 [PILOT_PROGRAM.md](./PILOT_PROGRAM.md)。

---

## 8. 立即开始

- **网站**: https://waibao.example.com
- **Demo 预约**: 邮件 hello@waibao.example.com
- **试用申请**: 填写 [PILOT_SURVEY_TEMPLATE.md](./PILOT_SURVEY_TEMPLATE.md) 入门问卷

---

## 9. 关于我们

- 团队: 来自伦敦 / 上海的招聘科技老兵 (前 LinkedIn / Indeed / Boss)
- 使命: 让欧洲中型企业用得起、用得明白 AI 招聘
- 投资方: (保密)

---

## 附录: 常见异议回答 (FAQ)

**Q: 和 LinkedIn Recruiter 有什么区别?**
A: LinkedIn 是简历库,我们是匹配引擎 + 协作平台。我们更擅长 50-500 人的中型企业,且提供完整推理链。

**Q: 数据安全?**
A: GDPR compliant,数据存储在 EU (Frankfurt),所有 PII 加密 (AES-256),访问全留痕 (T1004 审计日志)。

**Q: 集成难度?**
A: 5 分钟 SSO 接入。已支持 SAML / Google Workspace / Microsoft Entra ID。

**Q: 切换成本?**
A: 试用期间不要求迁移现有 ATS,数据可双向同步 (CSV 导入)。

**Q: 如果 AI 匹配不准确?**
A: 我们有"反馈权重调整"功能 (T903),每次反馈都会让模型更准;30 天后 Top-5 准确率从 ~60% 提升至 ~85%。

---

## 10. v3.0 Pilot 框架升级 (T1702)

### 10.1 给客户的承诺

> "你不用签长合同. 我们给你 **14 天零风险试用**,目标清晰: NPS ≥ 40, 周活 ≥ 70%. 14 天后我们出一份完整报告 — 你决定要不要续约."

### 10.2 试用四步法

| Day | 动作 | 销售 / CS 配合 |
| --- | --- | --- |
| **0** | Kickoff (1h) + 创建 program + 发邀请 | 销售发邀请 → 客户接受 |
| **1-3** | Onboarding + 培训视频 | CSM 答疑 |
| **7** | 中期 NPS check | 调 `/api/pilot/programs/{id}/nps` 看实时分数 |
| **13** | 触发月度报告 | `scripts/generate_pilot_report.py <id>` |
| **14** | 结束 program + 决策 | 客户看 PDF → Go / No-Go |

### 10.3 销售物料

- 公开试用页: `/pilot` — 客户可自助提交 NPS + 反馈
- 管理员后台: `/admin/pilot` — 内部销售/CSM 跟踪所有 program
- 月度报告 PDF — 14 天后通过 admin 后台一键下载
- Demo 邀请脚本: `services/integrations/pilot_invitation.py:_render_invite_email`

### 10.4 风险保障 (客户视角)

- 数据隔离 + 试用期结束可一键删除
- 4 小时严重问题响应
- 无锁定; 客户数据 30 天后自动清除
- 试用不达标不强买

### 10.5 销售 SOP (v3.0)

1. Demo 完成 → 创建 `pilot_programs` (status=`recruiting`)
2. Kickoff → `POST /api/pilot/invite` (admin/partner)
3. Day 1-3 → 监控 `invitations_accepted`, 推动 onboarding
4. Day 7 → 查 `GET /api/pilot/programs/{id}/nps`, 必要时 CSM 介入
5. Day 13 → `python scripts/generate_pilot_report.py <id> --out ./acme.pdf`
6. Day 14 → `POST /api/pilot/programs/{id}/end`
7. GA 决策 → 客户 yes → 商务签单; no → 30 天后数据清除

### 10.6 常见异议 (v3.0)

**Q: 试用 14 天够吗?**
A: 89% 的客户 14 天跑完核心流程. 业务节奏特殊可延长到 30 天.

**Q: NPS 40 真的能达成吗?**
A: 我们的内部基线是 52. 40 是行业 P75; 低于 40 我们会主动延长 Pilot 帮客户找原因.

**Q: 报告里能看到哪些内容?**
A: 完整 PDF 含 NPS / 周活 / 痛点 / 功能使用 / 最近反馈样本 / CSM 备注.

**Q: 销售 / CS 如何跟踪客户?**
A: 通过 `/admin/pilot` 后台,实时看每个客户的邀请 / 接受 / NPS / 反馈情况. 14 天结束时一键下载报告.
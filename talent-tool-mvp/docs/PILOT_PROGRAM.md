# Pilot Program 运营手册

> T1106 — 招募试用合作方的标准化流程。
> 本文档面向**产品经理 (PM)** 与**运营 (Ops)**。技术对接 (邀请 API、反馈 API) 见下文链接。

---

## 1. 招募合作方流程

### 1.1 候选名单筛选

理想合作方画像:

| 维度 | 标准 |
|---|---|
| 行业 | 跨境电商、SaaS、AI、金融科技、英国/欧洲本地中型企业 |
| 规模 | 招聘需求 5-30 个 / 月,内部已有 ATS 或 CRM |
| 决策人 | 招聘负责人 / People Ops Lead |
| 时间窗口 | 未来 30-60 天内有实际招聘需求 |

### 1.2 接触路径

1. **冷邮件**: 突出"2 周免费试用 + AI 匹配 + 协作房间",附本文件做 pitch。
2. **LinkedIn Outreach**: 招聘负责人 / Talent Acquisition Manager。
3. **行业活动 / 招聘群**: 邀请共进午餐,当面 demo Mothership 后台。
4. **现有客户转介绍**: 老客户推荐新合作方,给予额外算力。

### 1.3 决策链路

- **第 1 次沟通 (30 min)**: 需求诊断 → demo Mothership + Mind → 分享 SALES_DECK.md。
- **第 2 次沟通 (60 min)**: 试用协议条款 → 明确目标岗位数、用户数、试用周期。
- **签协议**: 用 PILOT 协议模板 (本文档 §3)。
- **开通账号**: PM 在 Mothership 创建 program + 邀请用户 (技术细节见 §6)。

### 1.4 时间线 (建议)

| Day | 动作 | 责任人 |
|---|---|---|
| 0 | 签订试用协议 | PM |
| 0 | 创建 pilot_programs + 邀请第一批用户 | PM |
| 1 | 用户接受邀请,登录试用 | 用户 |
| 7 | 第 1 次 check-in: 体验反馈 + 答疑 | PM |
| 14 | 中期 NPS + Quick Survey | PM |
| 21 | 深度访谈 5-10 位用户 | PM + Researcher |
| 28 | 收尾: 总结报告 + 是否付费决策 | PM + Sales |

---

## 2. 成功标准

试用成功 (Go) 需**同时满足**以下三项:

| 指标 | 阈值 | 计算方式 |
|---|---|---|
| **NPS** | ≥ 50 | `(promoters - detractors) / 响应数 * 100` (见 §4) |
| **周活 (WAU)** | ≥ 70% | 7 天内至少登录 1 次的邀请用户 / 已接受邀请的用户 |
| **Top 痛点** | ≤ 3 个 | 按 category=`bug` + `feature_request` 聚合,频次 >1 即为痛点 |

补充参考:

- **Feedback Volume**: ≥ 20 条 / 28 天 (人均 ≥ 0.7 条)
- **Quick Survey 平均分**: ≥ 4.0 / 5
- **Handoff 数**: ≥ 1 单 (证明"匹配 → 约谈 → 投递"主路径跑通)

如未达阈值,PM 主导复盘并输出改进方案,72 小时内同步给技术团队。

---

## 3. 试用协议模板

> 仅供参考。法律文本以正式合同为准,建议请律师审阅。

```text
PILOT PROGRAM AGREEMENT
[公司名称] (以下简称 "Customer")
与 waibao Ltd. (以下简称 "Provider")

1. 试用范围
   - Customer 在 Provider 的 pilot program 中获得 [N] 个用户席位
   - 试用周期: 开始日期 [START_DATE] 结束日期 [END_DATE] (默认 28 天)
   - 功能范围: AI 匹配 + 协作房间 + 反馈收集;不包含 [受限功能]

2. 数据使用
   - Customer 数据 (候选人、JD) 仅用于本次试用目的
   - Provider 不得将 Customer 数据用于训练第三方模型
   - 试用结束后 30 天内,Provider 将导出 Customer 数据并永久删除

3. 反馈收集
   - Customer 同意 Provider 收集试用期间的匿名 NPS、产品反馈和功能使用数据
   - 反馈数据用于改进 Provider 产品
   - 个人身份信息 (PII) 遵循 GDPR 处理

4. 保密
   - 双方对合作期间知悉的对方商业信息承担保密义务,有效期 3 年

5. 终止
   - 任一方可提前 7 天书面通知终止试用
   - 终止后双方按 §2 处理数据

6. 服务水平
   - API 可用性目标: 99.5%
   - 重大故障响应时间: 4 小时

签字:
______________________       ______________________
Customer 代表                Provider 代表
日期:                        日期:
```

---

## 4. NPS 计算公式

采用经典的 Bain & Company NPS (Net Promoter Score) 模型:

```
                  # Promoters (评分 9-10) - # Detractors (评分 0-6)
NPS = 100 *  ─────────────────────────────────────────────────────────
                          Promoters + Passives + Detractors
```

桶划分 (在 `/api/feedback/nps` 端点实现):

| 评分 | 桶 | 含义 |
|---|---|---|
| 0-6 | Detractor | 贬损者,可能劝阻他人使用 |
| 7-8 | Passive | 中立者,满意但不热情 |
| 9-10 | Promoter | 推广者,会主动推荐 |

注意: **Passives 计入分母,但不计入分子**。

实现位置: `backend/api/feedback.py` 写入 `metadata.bucket`,`backend/api/pilot.py` 的 `_compute_nps` 函数聚合。

---

## 5. 反馈收集方法

### 5.1 主动反馈

- **触发**: 用户点击右下角浮动按钮 (`FeedbackWidget`)。
- **类别**: bug / feature_request / praise / complaint / other。
- **接口**: `POST /api/feedback`。
- **存储**: `pilot_feedback.category != 'nps' && != 'survey'`.

### 5.2 NPS 评分

- **触发**: 试用第 7 天 / 14 天弹窗;用户也可手动触发 (`FeedbackWidget` -> NPS tab)。
- **频控**: 同一用户同一会话只弹 1 次,localStorage `wb_nps_done` 标记。
- **接口**: `POST /api/feedback/nps`。
- **存储**: `pilot_feedback.category='nps'`,score 0-10。

### 5.3 快速问卷

- **触发**: 重要功能首次完成后 (`featureUsed` 参数)。
- **题目**: 3 题 (易用性 / 价值感 / 响应速度),各 1-5 分。
- **频控**: localStorage `wb_quick_survey_done_{trigger}` 标记。
- **接口**: `POST /api/feedback/quick-survey`。
- **存储**: `pilot_feedback.category='survey'`,score 为平均分 ×2 (对齐 NPS 数值范围便于同图展示)。

### 5.4 深度访谈

- PM 预约 5-10 位试用用户,30-45 min 一对一。
- 模板见 [PILOT_SURVEY_TEMPLATE.md](./PILOT_SURVEY_TEMPLATE.md)。
- 访谈记录同步到 Confluence,脱敏后归档。

---

## 6. 技术对接 (开发参考)

### 6.1 创建 Pilot

```bash
curl -X POST https://api.waibao.com/api/pilot/programs \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "organisation_id": "uuid",
    "name": "Acme Corp · 跨境电商招聘",
    "target_nps": 50,
    "max_users": 20
  }'
```

### 6.2 邀请用户

```bash
curl -X POST https://api.waibao.com/api/pilot/invite \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "program_id": "uuid",
    "email": "alice@acme.com",
    "role": "employer"
  }'
# 返回 invite_url (14 天有效)
```

### 6.3 拉取统计

```bash
curl https://api.waibao.com/api/pilot/programs/$ID/stats \
  -H "Authorization: Bearer $ADMIN_JWT"
```

返回字段: invitations / nps / feedback_by_category / top_pain_points 等。

### 6.4 数据库

迁移文件: `supabase/migrations/019_pilot_programs.sql`,含三张表 (`pilot_programs` / `pilot_invitations` / `pilot_feedback`)。

---

## 7. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 邀请邮件进垃圾箱 | 接受率 < 30% | 配置 SPF / DKIM,首次发送后 PM 主动跟进 |
| 用户不填写反馈 | NPS 数据不足 | 弹窗 + 邮件提醒,试用结束奖励 (积分 / 折扣) |
| 内部 AI bug 被发现 | 负面口碑 | 24h 内修复,主动告知客户进度 |
| 试用到期未续约 | 流失 | 提前 7 天输出 ROI 报告 + 续费方案 |
| PII 数据滥用 | 合规风险 | GDPR 审计 + 访问日志 (T1004) + 加密存储 (T108) |

---

## 8. 复盘模板

试用结束后 7 天内 PM 输出报告,字段:

1. **基础数据**: 邀请数 / 接受数 / 活跃用户数
2. **NPS 趋势**: 7 天 / 14 天 / 28 天 折线图
3. **Top 痛点** (按 category 聚合)
4. **亮点** (按 praise 聚合)
5. **ROI 评估**: 时间节省 / 招聘成功率
6. **续约意向**: Go / No-Go + 理由
7. **改进建议**: 产品 / 工程 / 运营

报告归档到 `plans/pilot-reports/YYYY-MM-{org}.md`。

---

## 9. v3.0 升级说明 (T1702)

> 本节为 v3.0 Pilot 框架重构的增量说明. 既有流程保持兼容.

### 9.1 新增服务层

| 模块 | 路径 | 职责 |
| --- | --- | --- |
| `pilot_service` | `backend/services/integrations/pilot_service.py` | `create_program / invite / get_stats / end_program / generate_report` |
| `nps_service` | `backend/services/integrations/nps_service.py` | `calculate_nps / categorize_feedback` (LLM + 启发式回退) |
| `pilot_report` | `backend/services/integrations/pilot_report.py` | 月度 PDF (reportlab → 失败 fallback 纯文本) |

### 9.2 新增 API 端点 (api/pilot.py)

- `PATCH /api/pilot/programs/{id}` — 更新
- `DELETE /api/pilot/programs/{id}` — 删除
- `GET /api/pilot/programs/{id}/nps` — 实时 NPS
- `GET /api/pilot/programs/{id}/report` — JSON 完整报告
- `POST /api/pilot/programs/{id}/report/pdf` — 触发生成 PDF
- `GET /api/pilot/programs/{id}/report/download` — 直接下载
- `POST /api/pilot/feedback/categorize` — LLM 分类 (admin)

### 9.3 新增前端组件

- `components/pilot/NPSWidget.tsx` — 0-10 评分
- `components/pilot/FeedbackDialog.tsx` — 5 类反馈弹窗
- `components/pilot/UsageStats.tsx` — KPI / NPS 分布 / Top 痛点
- `components/pilot/AdminDashboard.tsx` — 程序列表 + 总览

页面: `/pilot`, `/admin/pilot`, `/admin/pilot/[id]`.

### 9.4 新增 CLI

```bash
python scripts/generate_pilot_report.py <program_id> --out ./report.pdf
```

退出码: 0 成功 / 2 参数错 / 3 program 不存在 / 4 生成失败.

### 9.5 目标值 (v3.0)

| 指标 | v3.0 | v2 (旧) |
| --- | --- | --- |
| NPS | ≥ **40** | ≥ 50 |
| 周活 | ≥ **70%** | ≥ 70% |
| Top 痛点 | ≤ **5** | ≤ 3 |

> 阈值调整理由: 让中等规模客户的"Pilot → GA"路径更可达;
> 严格阈值仍记录在 `metadata.targets_met` 用于事后分析.
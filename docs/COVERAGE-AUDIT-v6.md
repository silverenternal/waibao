# 甲方需求 + 架构扩展性 复审报告 (v6.0 规划依据)

**审计日期**: 2026-07-12
**审计维度**: 16 项甲方需求 + 架构扩展性 + 新功能添加成本 + 横向能力

---

## 评分图例

- ✅ **完整 + 可扩展** — 1-2 天可加新供应商/Agent/API
- 🟡 **完整但扩展受限** — 加新功能需要改核心代码
- ❌ **缺失 / 难扩展** — 没机制或需大改

---

## 维度 1: 16 项甲方需求(v5.0)

| 编号 | 评级 | 备注 |
|---|---|---|
| 1.1 | ✅ | Profile/Intake/简历上传/OCR/ProfileCard |
| 1.2 | ✅ | Daily Journal + 趋势图 + 行动项 + 语音 |
| 1.3 | ✅ | WebSocket + SSE + Redis + 协同房间 |
| 1.4 | ✅ | Emotion + 折线图 + 周报 + 高风险告警 |
| 1.5 | ✅ | Clarifier + 画像可视化 + 追问 + 冲突 |
| 1.6 | ✅ | CareerPlanner + 真实市场 + 学习资源 + 计划 |
| 2.1 | ✅ | Persona + 老板偏好 + 升级按钮 |
| 2.2 | ✅ | Compliance + OCR + 工商 + 信用代码 + 过期 |
| 2.3 | ✅ | Vision + 4 层战略地图 + diff |
| 2.4 | ✅ | TalentBrief + 偏见 + 法律 |
| 2.5 | ✅ | JobSpec + 模板 + over-spec + 版本 |
| 2.6 | ✅ | Policy + 浏览 + 搜索 + 法律 |
| 2.7 | ✅ | MultiParty + 协同房间 + @mention |
| 2.8 | ✅ | EmployerClarifier + 画像 + StakeholderMatrix |
| 2.9 | ✅ | HRService + 工单 + SLA + 自动升级 |
| 3 | ✅ | TwoWay + 互评 + 可解释 + 自动权重 |

**结论**: 16/16 ✅ 完整,生产级。

---

## 维度 2: 架构扩展性评审(关键!)

### ✅ 已经做对的部分 — 扩展性优秀

| 模块 | 抽象 | 加新供应商/Agent 成本 |
|---|---|---|
| **LLM/Embedding/Vision/OCR/STT/Notify/Lookup/JobMarket/Payment/VideoInterview/Assessment/ATS/BackgroundCheck** (12 维度) | ABC + base.py + registry + mock + 适配器 | **1-2 天** |
| **Agent 框架** | BaseAgent + AgentInput/Output + MemoryScope | **0.5-1 天** |
| **API 路由** | 65 router 按模块分类 | **0.5 天** |
| **数据库迁移** | 33 编号迁移 | **0.5 天** |
| **前端组件** | shadcn 风格 + Tailwind | **0.5-1 天** |
| **i18n** | next-intl 3 语言 240 keys | **0.5 天** |
| **多端** | uni-app + 钉钉 + 飞书 + PWA | **1-2 周** |
| **可观测性** | OTel + Prometheus + Sentry 自动 | **0** |
| **测试框架** | pytest 1434 passed | **0.5 天** |
| **Webhook 出口** | HMAC 签名 + 重试 + 死信 | **0.5 天** |
| **公开 API** | API Key + scope + rate limit | **0.5 天** |
| **规则引擎** | DSL + 内置触发器 + cooldown | **0.5 天** |

### 🟡 受限的部分 — 加新功能需改核心

| 问题 | 现状 | 痛点 |
|---|---|---|
| **Agent 间缺 Hook 机制** | Agent A 调 Agent B 是硬编码 in 代码 | 想"clarifier 完成后自动触发 emotion" 必须改两个文件 |
| **缺动态配置中心** | Agent prompt / 阈值全在代码里 | admin 想改"偏见阈值"必须发版 |
| **缺 Feature Flag 系统** | 没办法"对 5% 用户打开新功能" | 灰度靠手工改 env |
| **缺插件机制** | 第三方开发者不能加新 Agent / Service | 扩展只能官方做 |
| **Prompt 管理** | Prompt 散落在 agent .py 文件 | 改 prompt 需发版 |
| **记忆系统** | 短期/工作/长期 3 层但耦合 agent | 缺"用户级记忆"统合 |
| **多租户隔离** | org_id 在表里但 RLS 不严 | 大客户单独部署难 |

### ❌ 缺失的扩展性能力

| 能力 | 状态 | 影响 |
|---|---|---|
| **Event Bus** (pub/sub) | ❌ | Agent 间不能事件驱动,只能顺序调用 |
| **插件市场** (Plugin SDK) | ❌ | 第三方开发者无法贡献 Agent / Service |
| **Agent Composition** (可视化编排) | ❌ | 非技术人员不能配置 Agent 流程 |
| **配置中心** (admin UI 改 agent 行为) | ❌ | 所有变更需发版 |
| **Feature Flag** | ❌ | 灰度靠手工 |
| **Tenant 配额** | ❌ | 大客户单独配额需改代码 |
| **数据版本化** (Event Sourcing) | ❌ | 数据审计 / 回放难 |
| **API 网关** (限流/熔断/路由) | 🟡 | 散落在各 service |
| **A/B 测试粒度** (UI/Agent/Prompt 三个层级) | 🟡 stub | v3.0 加了 stub 但只到算法 |

---

## 维度 3: 新功能添加成本评估

### ✅ 加这些东西 1-2 天搞定(优秀)

1. **新 LLM 供应商** (e.g. Cohere): 写 `providers/llm/cohere.py` + 注册到 `registry.py` + 写 `tests/test_cohere.py`
2. **新 Agent** (e.g. 简历评分 Agent): 写 `agents/jobseeker/resume_scorer_agent.py` + 注册 + 写 API
3. **新 OCR 供应商** (e.g. 阿里云): 同上
4. **新 API 端点**: 写 router + 业务 service
5. **新数据库表**: 写 migration
6. **新前端页面**: 用 shadcn 组件拼
7. **新 i18n 语言** (e.g. 日语): 加 JSON + locale switcher
8. **新 Webhook 事件**: 扩展 `WebhookEvent` 枚举
9. **新公开 API 端点**: 在 `api/public.py` 加

### 🟡 加这些东西 1-2 周(中等)

10. **新端** (e.g. 飞书): uni-app 跨端或单独写
11. **新实时通道** (e.g. Slack): 写 `providers/notify/slack.py`
12. **新评估指标** (e.g. 业务指标): 加 metrics + dashboard

### ❌ 加这些东西 1-2 月(困难)

13. **新 Agent 类型 + UI 可视化编排**: 缺 Event Bus + Agent Composition
14. **新"动态行为"** (e.g. admin 改偏见阈值实时生效): 缺配置中心
15. **新"插件"** (第三方开发者贡献): 缺 Plugin SDK
16. **多租户配额管理**: 缺 Tenant Quota 系统
17. **数据回放 / 审计**: 缺 Event Sourcing

---

## 维度 4: 横向能力补强(竞争差异化)

虽然 16 项甲方需求都满足,但**真正区分竞品**的能力还缺:

| 能力 | 现状 | 商业价值 |
|---|---|---|
| **AI 模拟面试官**(语音 + 视频实时对话) | ❌ 缺 | ⭐⭐⭐⭐⭐ 高,差异化 |
| **Realtime API 实时对话** (GPT-4o Realtime) | ❌ 缺 | ⭐⭐⭐⭐⭐ 高,体验质变 |
| **视频简历理解** (GPT-4V 看 30 秒自我介绍) | ❌ 缺 | ⭐⭐⭐⭐ 中高 |
| **雇主品牌建设** (公司介绍页 + 评价集成) | 🟡 部分 | ⭐⭐⭐ 中 |
| **公司评价集成** (看准网 / Glassdoor) | ❌ 缺 | ⭐⭐⭐ 中 |
| **行业薪资报告** (实时市场数据) | 🟡 mock | ⭐⭐⭐ 中 |
| **离职预测模型** (从情绪时间线预测离职风险) | ❌ 缺 | ⭐⭐⭐⭐ 中高 |
| **试用期跟踪** (新员工 3/6 月评估) | ❌ 缺 | ⭐⭐⭐ 中 |
| **内部推荐系统** (在职员工推荐候选人) | ❌ 缺 | ⭐⭐⭐⭐ 中高 |
| **候选人 Rediscovery** (沉睡候选人激活) | ❌ 缺 | ⭐⭐⭐ 中 |
| **多模态语义搜索** (视频/音频/图片 搜索) | 🟡 文本 | ⭐⭐⭐⭐ 中高 |
| **AI 自动生成 JD** (一句话生成完整 JD) | 🟡 template | ⭐⭐⭐ 中 |
| **面试准备助手** (针对 JD 准备 10 道题) | ❌ 缺 | ⭐⭐⭐⭐ 中高 |
| **薪资谈判模拟** (用 AI 模拟 HR 反向施压) | ❌ 缺 | ⭐⭐⭐ 中 |

---

## 维度 5: 真正的痛点(用户用起来才会发现)

虽然 v5.0 大量功能完整,但**用户用起来**会发现的痛点:

1. **缺"为什么"**: 匹配分 0.8 但不知道为什么,虽然 v3.0 加了 explainer 但还浅
2. **缺"下一步"**: AI 给建议但不给"今天该做什么",需要用户自己拆
3. **缺"信任"**: 求职者不信任 AI 给的画像/需求,需要"用户确认"机制
4. **缺"效率"**: HR 用起来发现每个候选人/岗位都要手动操作,需要"批量"
5. **缺"对比"**: 多个候选人/岗位放一起,无对比视图
6. **缺"搜索"**: 知道有这个人但找不到(v4.0 加了全局搜索但效果待验证)
7. **缺"协作"**: HR 团队内部分享/讨论候选人,只有 1v1 没有多人
8. **缺"导出"**: 给老板/上级汇报,要 Word/PPT 导出
9. **缺"通知偏好"**: 用户被通知轰炸,需要按优先级/类型过滤
10. **缺"移动端"**: HR 在路上要看简历,响应式 Web 体验差

---

## v6.0 优先补强方向

1. **P0 架构扩展性 (基础)**:
   - Event Bus (Agent 间解耦)
   - 配置中心 (admin UI 改 agent 行为)
   - Feature Flag 系统
   - Plugin SDK (基础)
   - Agent Composition (可视化编排)

2. **P0 真正差异化能力**:
   - AI 模拟面试官 (语音 + 视频)
   - Realtime API (实时对话)
   - 视频简历理解 (GPT-4V)

3. **P1 用户体验提升**:
   - 候选人/岗位对比视图
   - 批量操作
   - 文档导出 (Word/PPT)
   - 通知偏好

4. **P1 业务深化**:
   - 公司评价集成
   - 行业薪资报告
   - 离职预测模型
   - 试用期跟踪
   - 内部推荐系统

5. **P2 高级特性**:
   - 多模态搜索
   - AI 自动生成 JD
   - 面试准备助手
   - 薪资谈判模拟

**核心思路转变**: v5.0 是"代码健康",v6.0 应该是"可扩展架构 + 真正差异化能力"。
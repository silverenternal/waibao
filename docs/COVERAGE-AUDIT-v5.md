# 甲方需求 + 模块盘点复审报告 (v5.0 规划依据)

**审计日期**: 2026-07-12
**审计范围**: 16 项甲方需求 × v4.0 实现 (16 Agent + 65 API + 56 services + 12 维度 Provider + 4 端 + 1242 tests + 33 migrations)
**审计维度**: 需求覆盖度 + 模块组织 + 生产就绪 + 业务深度

---

## 评分图例

- ✅ **完整 + 健康** — 功能有 + 测试有 + 代码组织清晰 + 集成验证过
- 🟡 **形式完整 + 风险** — 功能在但有债务或未验证
- ❌ **缺失** — 没做

---

## 维度 1: 16 项甲方需求覆盖

| 编号 | 评级 | 备注 |
|---|---|---|
| 1.1 | 🟡 | Profile + Intake Agent + 简历上传 UI + OCR 集成,真实 API 跑通待 key |
| 1.2 | 🟡 | Daily Journal + 趋势图 + 行动项追踪,AI 评价长期效果未验证 |
| 1.3 | ✅ | WebSocket + SSE + 协同房间 5000 并发压测待真实负载 |
| 1.4 | 🟡 | Emotion + 折线图 + 周报 + 相关性,**高风险即时通知 HR 未接通** |
| 1.5 | 🟡 | Clarifier + 画像可视化 + 追问引导 + 冲突标注,**LLM 反思深度需加强** |
| 1.6 | 🟡 | CareerPlanner + 真实市场 + 学习资源 + 计划调整,**真实招聘市场 key 缺** |
| 2.1 | 🟡 | Persona + 老板偏好记忆 + 升级按钮,**决策模式学习未跑数据** |
| 2.2 | ✅ | Compliance + OCR + 工商查询 + 信用代码 + 过期提醒 |
| 2.3 | ✅ | Vision + 4 层战略地图 + diff |
| 2.4 | 🟡 | TalentBrief + 偏见可视化 + 法律提示,**法律依据库需补真实法条** |
| 2.5 | 🟡 | JobSpec + 模板库 + over-spec UI + 版本历史 |
| 2.6 | ✅ | Policy + 浏览页 + 全文搜索 + 法律风险可视化 |
| 2.7 | 🟡 | MultiParty + 协同房间 + WebSocket,**5 方实时通知集成** |
| 2.8 | 🟡 | EmployerClarifier + 人才画像可视化 + StakeholderMatrix |
| 2.9 | ✅ | HRService + 工单 + SLA + 自动升级 |
| 3 | 🟡 | TwoWay + 互评 + 可解释 + 自动权重 + dashboard |

**结论**: 16/16 ✅ 形式覆盖,但**全部 🟡 都有生产债务**:
- 真实 API key 未配置(7 项依赖第三方)
- Pilot 合作方未找到(无人验证 NPS)
- 性能压测通过 mock,真实负载未跑
- AI 评价/推荐/匹配效果无人长期验证

---

## 维度 2: 模块组织问题 (本次盘点发现)

### 痛点分级

#### 🔴 P0 — 立即修(影响日常开发)

1. **services/ 56 个文件过重**
   - 一个目录塞了所有业务,新功能难定位
   - 解决:按 domain 拆子包
     - `services/jobseeker/` (resume_parser, plan_tracker, learning_resources, offer_calculator, negotiation_advisor, ai_interviewer, video_processing, question_bank)
     - `services/employer/` (compliance_service, ticket_service, ats_sync, channel_attribution, recruitment_funnel, corp_sync, dingtalk_sync, feishu_sync, dingtalk_approval, calendar_sync)
     - `services/matching/` (feedback_loop, calibration, global_search)
     - `services/billing/` (billing, payment_providers, invoice_generator)
     - `services/infra/` (telemetry, metrics, sentry, audit, backup, region_router, region_config, llm_cache, llm_budget, cost_tracker, i18n, permissions, notify, handoff, collection, quote)
     - `services/integrations/` (collaboration_room, candidate_recommender, push_engine, job_subscription, api_key, persona_memory, pii_field_encryption, pilot_invitation, funnel_events, profile_extractor, resume_parser, transcribe, file_storage, realtime_router)

2. **agents/runtime.py 过重**
   - BaseAgent + LLMClient + MemoryScope + Toolkit + Registry + Tracing 都混一起
   - 解决:拆 `agents/core/` (BaseAgent + AgentInput/Output) + `agents/llm/` (LLMClient) + `agents/memory/` (MemoryScope + MemoryStore) + `agents/observability/` (Tracing)

3. **adapters/ 是 v1.0 残留**
   - Bullhorn/HubSpot/LinkedIn stub,已被 providers/ats/ 替代
   - 解决:合并到 providers/ats/,删除 adapters/

4. **copilot/ signals/ 使用度低**
   - copilot: NL 查询,v2.0 后被 realtime invoke 替代
   - signals: 事件追踪,v3.0 funnel_events 替代
   - 解决:评估使用,若 30 天内无调用,删除

#### 🟡 P1 — 1 周内修(影响可维护性)

5. **frontend mind/ + mothership/ 残留**
   - v1.0 "招聘方" + "内部" 跟 v2.0 后的 employer/ 重叠
   - 解决:整合 — `mind/` 合并到 `employer/`,`mothership/admin/` 移到独立 `admin/`

6. **frontend components/ 平铺**
   - ~50 个组件同层,新组件难找
   - 解决:按域分类
     - `components/jobseeker/` (ResumeUpload, ProfileCard, JournalAdviceList, ...)
     - `components/employer/` (PolicyList, TalentImageCard, StrategyMap, ...)
     - `components/shared/` (charts, ui, common)

7. **无 backend setup() 统一入口**
   - lifespan 里 init_adapters + init_all_agents + ... 散落
   - 解决:加 `backend/main.py:setup_application()` 函数,集中所有 init

#### 🟢 P2 — 重构期做(影响可扩展性)

8. **无 Storybook**
   - 50+ 组件无独立展示
   - 解决:加 `frontend/.storybook/`

9. **无统一错误代码**
   - 散落的字符串错误
   - 解决:加 `backend/errors.py` ErrorCode 枚举

10. **无 backend observability 中心**
    - telemetry / metrics / sentry / audit 4 个独立
    - 解决:加 `backend/observability/` 包统一门面

---

## 维度 3: 生产就绪差距

| 维度 | 现状 | 差距 |
|---|---|---|
| **真实 API key** | 0/28 | Boss直聘/Whisper/钉钉/微信/支付宝/Zoom 等 12+ 真实 key |
| **Pilot 合作方** | 0/1-2 | 找 1 家中型企业试用 1 个月 |
| **NPS** | 无 | 真实数据 |
| **性能压测** | mock 跑过 | 真实负载 + 1000+ 并发用户 |
| **SLA** | 文档 | 真实 99.5% 可用性 |
| **真实告警** | 配置 | 真实 7×24 告警通道(钉钉/飞书/PagerDuty) |
| **灾备演练** | 文档 | 真实每季度演练 |
| **CDN** | 无 | 静态资源 CDN 加速 |
| **CI/CD** | 基础 | 蓝绿部署 + 灰度 |
| **Sentry 接入** | 代码 | 真实 DSN 接入 |

---

## 维度 4: 业务深度差距

虽然 v3-v4 加了大量"业务深度"功能,但**大部分仍是 stub**:

| 功能 | 现状 | 生产差距 |
|---|---|---|
| **AI 自动面试** | 后端 + 前端 | GPT-4V 真实接入,题库 100 题真品 |
| **Offer 比较** | 后端 + 前端 | 真实 offer 数据积累,谈判话术被采用统计 |
| **招聘漏斗** | 后端 + 前端 | 真实埋点积累 90 天数据 |
| **候选人订阅** | 后端 + 前端 | 真实推送渠道 + 触发率 |
| **视频面试** | 后端 | Zoom/腾讯 真实账号 |
| **测评** | 后端 | 北森真实对接 |
| **背调** | 后端 | Checkr 真实账号 |
| **ATS 同步** | 后端 | Greenhouse/Lever 真实账号 |
| **Webhook** | 后端 | 真实订阅方 |
| **公开 API** | 后端 | 真实第三方开发者 |
| **规则引擎** | 后端 | 真实业务规则 |
| **A/B 实验** | 后端 | 真实流量 |
| **LLM cache** | 后端 | 真实缓存命中 |
| **协同房间** | 后端 + 前端 | 真实日活 100+ 房间 |
| **多端** | 代码 | 真实上架 + 日活 |

**核心问题**: 所有 v3-v4 的"业务深度"都停在"功能完成 + 测试通过"阶段,**没有任何功能在真实业务中被使用并产生数据**。

---

## v5.0 优先补强方向

1. **P0 内务整顿 (代码健康)**: services 拆包 + agents 拆 core/llm/memory + 删 dead code + 整合 mind/mothership
2. **P0 真实业务落地 (生产就绪)**: 找 1-2 家中型企业试用 + 配置真实 API key + 真实压测
3. **P1 业务深度上线**: AI 面试 / Offer / 漏斗 等从 stub → 真业务数据
4. **P1 多端上架**: 微信小程序 / 钉钉 / 飞书 / PWA 真实上架 + 日活
5. **P2 商业化**: 第一个付费客户 + 续费 + case study
6. **P2 规模化**: 多区域部署真实跑 + 灾备演练

**核心思路转变**: v3-v4 是"功能铺开",v5.0 必须是"功能落地 + 代码健康"。不做新功能,只做"把现有功能真正用起来 + 把代码组织梳理清"。
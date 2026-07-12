# API 端点清单

## 📡 总览

本系统提供 **HTTP REST API + WebSocket + SSE** 三种接入方式。

所有 API 都通过 `/api/*` 前缀,WebSocket 走 `/api/realtime/ws/*`,SSE 走 `/api/realtime/sse/*`。

## 🔐 鉴权

所有需要鉴权的端点要求 `Authorization: Bearer <jwt>` 头。

JWT 由 Supabase Auth 签发,后端用 `SUPABASE_JWT_SECRET` 解码。

---

## 🟦 智能体调用 (Realtime)

### HTTP: 召唤智能体
```
POST /api/realtime/invoke
Content-Type: application/json
Authorization: Bearer <jwt>

{
  "agent_name": "emotion_agent",   // 可选,空则自动路由
  "text": "我今天心情很差",
  "context": {},                  // 业务上下文
  "stream": false                 // true 时返回 SSE 端点
}

Response:
{
  "agent": "emotion_agent",
  "text": "听起来你不太好受...",
  "artifacts": {"primary_emotion": "sadness", ...},
  "cost_cents": 5,
  "request_id": "abc123",
  "success": true
}
```

### WebSocket: 流式对话
```
WebSocket: ws://host:8000/api/realtime/ws/invoke?token=<jwt>

# 客户端发送:
{"text": "...", "agent_name": "可选", "context": {...}}

# 服务端推送:
{"type": "ready", "user_id": "...", "persona": "jobseeker"}
{"type": "start", "agent": "emotion_agent", "request_id": "..."}
{"type": "chunk", "text": "..."}          // 流式分块
{"type": "done", "artifacts": {...}, "cost_cents": 0}
{"type": "error", "message": "..."}
```

### SSE (浏览器 EventSource)
```
GET /api/realtime/sse/invoke?text=...&agent_name=...&token=<jwt>

Response (text/event-stream):
event: start
data: {"agent": "emotion_agent"}

event: chunk
data: {"text": "听起来..."}

event: done
data: {"artifacts": {...}, "success": true}
```

---

## 🟦 求职者侧 API

### 日记 (1.2)
```
POST /api/journal
Body: {"content": "今天学了很多", "mood_score": 0.5}
→ 触发 DailyJournal Agent,返回 AI 评价

GET /api/journal/timeline?days=30
→ 获取最近 30 天日记

GET /api/journal/today
→ 获取今天的日记(若已提交)
```

### 情绪 (1.4)
```
POST /api/emotion/detect?text=我今天崩溃了
→ 调用 Emotion Agent

GET /api/emotion/timeline?days=30
→ 情绪时间线(可视化)

GET /api/emotion/alerts   (仅 HR/admin/talent_partner)
→ 需要关注的情绪告警列表
```

### 澄清 / 画像 (1.5)
```
POST /api/clarification/synthesize
→ 综合求职者画像 + 真实需求
Body: {}  (从 user_id 自动拉取所有数据)

GET /api/clarification/my-profile
→ 获取我的画像 + 需求

POST /api/clarification/synthesize-employer
Body: {
  "role_id": "...",
  "brief": {...},
  "spec": {...},
  "compliance": {...},
  "policy": {...}
}
→ 综合用人方画像

GET /api/clarification/role/{role_id}
→ 获取岗位的用人方画像
```

### 职业规划 (1.6)
```
POST /api/career-plan/generate
→ 基于最新画像生成职业规划

GET /api/career-plan/current
→ 获取当前规划
```

---

## 🟧 用人单位侧 API

### 愿景战略 (2.3)
```
POST /api/vision/submit
Body: {"text": "我们公司要在 3 年内成为 AI 平台..."}
→ Vision Agent 解构 4 层

GET /api/vision/strategy-map?organisation_id=...
→ 战略地图(分组 by level)
```

### 资质 (2.2)
```
POST /api/compliance/upload
Body: {
  "file_url": "https://...",
  "credential_type": "business_license",
  "hint_company_name": "...",
  "hint_credit_code": "..."
}
→ OCR + 工商查询 + trust_score

GET /api/compliance/status?organisation_id=...
→ 资质审核状态汇总
```

### 人才需求 (2.4)
```
POST /api/talent-brief/submit
Body: {"text": "我们需要一个有 5 年 AI 经验..."}
→ TalentBrief Agent(含偏见检测)
```

### JD 细化 (2.5)
```
POST /api/job-spec/submit
Body: {"text": "招一个 AI 工程师...", "role_id": "可选"}
→ JobSpec Agent
```

### 规章制度 (2.6)
```
POST /api/policy/upload
Body: {"text": "...", "category": "attendance", "organisation_id": "..."}
→ Policy Agent 入库

GET /api/policy/query?question=请假流程&organisation_id=...
→ 智能体回答(求职者/HR 都可)

GET /api/policy/list?organisation_id=...&category=...
→ 制度列表
```

### 多方对话 (2.7)
```
POST /api/multiparty/submit
Body: {
  "inputs": [
    {"role": "boss", "message": "...", "user_id": "u1"},
    {"role": "hr", "message": "...", "user_id": "u2"}
  ]
}
→ MultiParty Agent 汇总
```

### HR 全生命周期 (2.9)
```
POST /api/realtime/invoke
Body: {"text": "我的假期还有几天?", "agent_name": "hr_service_agent"}
→ HRService Agent
```

---

## 🟩 双向匹配 API (3)

### 计算匹配
```
POST /api/two-way-match/compute?candidate_id=...&role_id=...
→ 计算并存储双向匹配

Response:
{
  "candidate_to_role": 0.85,
  "role_to_candidate": 0.72,
  "harmonic_score": 0.78,
  "candidate_perspective": {...},
  "employer_perspective": {...},
  "record_id": "..."
}
```

### 推荐 Top N
```
GET /api/two-way-match/for-candidate/{candidate_id}?limit=10
→ 给求职者推荐 Top N 岗位

GET /api/two-way-match/for-role/{role_id}?limit=20
→ 给 HR 推荐 Top N 候选人

POST /api/two-way-match/batch?candidate_id=...&top_n_roles=20
→ 批量计算候选人对所有活跃岗位
```

### 互评
```
POST /api/evaluation/mutual
Body: {
  "candidate_id": "...",
  "role_id": "...",
  "candidate_eval": {
    "skill": 4, "communication": 5, "culture": 4, "potential": 5,
    "comment": "技术扎实"
  },
  "employer_eval": {
    "skill": 4, "communication": 4, "culture": 5, "potential": 4,
    "comment": "文化契合"
  }
}
→ MutualEvaluator Agent
```

---

## 🛡️ GDPR 合规

```
GET  /api/gdpr/export        → 导出我的所有数据
DELETE /api/gdpr/all-data    → 忘记我(删除所有个人数据)
GET  /api/gdpr/privacy       → 隐私政策摘要
```

---

## 📚 OpenAPI 文档

启动后端后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 🆕 v2.0 新增 API

### 资质审核增强 (T103) — `/api/compliance`
```
POST /api/compliance/upload
Body: {
  "file_url": "https://...",
  "credential_type": "business_license",
  "hint_company_name": "...",
  "hint_credit_code": "..."
}
→ OCR + 工商查询 + trust_score (走 providers.registry)

GET  /api/compliance/status?organisation_id=...
→ 资质状态汇总

GET  /api/compliance/expiry-alerts?organisation_id=...&days_ahead=30
→ 即将过期的资质告警
```

### HR 工单 (T207) — `/api/tickets`
```
POST   /api/tickets
Body: {
  "title": "...",
  "description": "...",
  "priority": "normal|high|urgent",
  "category": "hr|onboarding|policy|...",
  "assignee_id": "可选",
  "tags": [],
  "metadata": {}
}
→ 创建工单

GET    /api/tickets                       → HR 看所有
GET    /api/tickets/me                    → 员工看自己的
GET    /api/tickets/overdue               → HR 看逾期
GET    /api/tickets/{ticket_id}           → 单条详情
GET    /api/tickets/{ticket_id}/timeline  → 时间线

PATCH  /api/tickets/{ticket_id}/status
Body:  {"status": "in_progress|resolved|...", "reason": "...", "assignee_id": "可选"}

PATCH  /api/tickets/{ticket_id}
Body:  {"title": "...", "priority": "...", "tags": [...]}

POST   /api/tickets/{ticket_id}/comments
Body:  {"body": "...", "is_internal": false, "attachments": []}
```

### Admin 通知通道管理 (T104) — `/api/admin/notify`
```
GET   /api/admin/notify/channels
→ 列出 5 个通道 (smtp/dingtalk/feishu/wecom/webhook) 及其启用状态 + ENV 配置键

POST  /api/admin/notify/channels
Body: {"channel": "dingtalk", "enabled": true, "config": {...}}
→ 启用 / 禁用 / 改某个通道 (admin only)

GET   /api/admin/notify/channels/prefs?user_id=可选
→ 查询用户通知偏好

POST  /api/admin/notify/channels/prefs
Body: {"user_id": "...", "channel": "dingtalk", "enabled": true, "quiet_hours": {...}}
→ 写用户偏好

GET   /api/admin/notify/templates
→ 列出可用通知模板 (key / subject / body schema)
```

### 文件上传 (T201) — `/api/uploads`
```
POST   /api/uploads   (multipart/form-data)
       file=<binary>
       bucket=可选,默认 env STORAGE_DEFAULT_BUCKET
       folder=默认 "files"
→ 返回 {file_url, path, bucket, mime, size, filename}

GET    /api/uploads/signed-url?path=...&ttl=3600
→ 生成 signed URL

DELETE /api/uploads?path=...
→ 删除文件
```

### Provider 抽象层 (内部/Admin)

```bash
# 直接查 OpenAPI 的 /docs 即可看 provider 状态/统计
# 也可以在业务侧通过 services/file_storage 等接口隐式触发
```

---

## 🧪 调用示例 (cURL)

```bash
# 1. 召唤 emotion agent
curl -X POST http://localhost:8000/api/realtime/invoke \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"text": "我今天崩溃了", "agent_name": "emotion_agent"}'

# 2. 提交日记
curl -X POST http://localhost:8000/api/journal \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"content": "今天学了 LangChain", "mood_score": 0.6}'

# 3. 计算双向匹配
curl -X POST "http://localhost:8000/api/two-way-match/compute?candidate_id=xxx&role_id=yyy" \
  -H "Authorization: Bearer $JWT"

# 4. WebSocket(用 wscat)
wscat -c "ws://localhost:8000/api/realtime/ws/invoke?token=$JWT"
> {"text": "我有点迷茫", "agent_name": ""}
```

---

## 🔗 完整端点表

| 路径 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/api/realtime/invoke` | POST | ✅ | 召唤智能体 |
| `/api/realtime/ws/invoke` | WS | ✅(query token) | WebSocket 流式 |
| `/api/realtime/sse/invoke` | GET | ✅(query token) | SSE 流式 |
| `/api/journal` | POST | ✅ | 提交日记 |
| `/api/journal/timeline` | GET | ✅ | 日记时间线 |
| `/api/journal/today` | GET | ✅ | 今日日记 |
| `/api/emotion/detect` | POST | ✅ | 情绪检测 |
| `/api/emotion/timeline` | GET | ✅ | 情绪时间线 |
| `/api/emotion/alerts` | GET | ✅(HR/admin) | 情绪告警 |
| `/api/clarification/synthesize` | POST | ✅ | 综合求职者画像 |
| `/api/clarification/my-profile` | GET | ✅ | 我的画像 |
| `/api/clarification/synthesize-employer` | POST | ✅(用人单位) | 综合用人方 |
| `/api/clarification/role/{role_id}` | GET | ✅ | 岗位画像 |
| `/api/career-plan/generate` | POST | ✅ | 生成职业规划 |
| `/api/career-plan/current` | GET | ✅ | 当前规划 |
| `/api/vision/submit` | POST | ✅(boss/hr) | 提交愿景 |
| `/api/vision/strategy-map` | GET | ✅ | 战略地图 |
| `/api/compliance/upload` | POST | ✅(hr) | 上传资质 |
| `/api/compliance/status` | GET | ✅ | 资质状态 |
| `/api/talent-brief/submit` | POST | ✅(boss/hr) | 人才框架 |
| `/api/job-spec/submit` | POST | ✅(dept_head/hr) | JD 细化 |
| `/api/policy/upload` | POST | ✅(hr) | 上传制度 |
| `/api/policy/query` | GET | ✅ | 查询制度 |
| `/api/policy/list` | GET | ✅ | 制度列表 |
| `/api/multiparty/submit` | POST | ✅(多角色) | 多方汇总 |
| `/api/compliance/upload` | POST | ✅(hr) | 上传资质 (v2.0) |
| `/api/compliance/status` | GET | ✅ | 资质状态 (v2.0) |
| `/api/compliance/expiry-alerts` | GET | ✅(hr/admin) | 即将过期告警 (v2.0) |
| `/api/tickets` | POST | ✅ | 创建工单 (v2.0) |
| `/api/tickets` | GET | ✅(hr/admin) | 所有工单 (v2.0) |
| `/api/tickets/me` | GET | ✅ | 我的工单 (v2.0) |
| `/api/tickets/overdue` | GET | ✅(hr/admin) | 逾期工单 (v2.0) |
| `/api/tickets/{id}` | GET | ✅ | 工单详情 (v2.0) |
| `/api/tickets/{id}/status` | PATCH | ✅ | 推进状态 (v2.0) |
| `/api/tickets/{id}` | PATCH | ✅ | 编辑元信息 (v2.0) |
| `/api/tickets/{id}/comments` | POST | ✅ | 添加评论 (v2.0) |
| `/api/tickets/{id}/timeline` | GET | ✅ | 时间线 (v2.0) |
| `/api/admin/notify/channels` | GET | ✅(admin) | 通道列表 (v2.0) |
| `/api/admin/notify/channels` | POST | ✅(admin) | 通道开关 (v2.0) |
| `/api/admin/notify/channels/prefs` | GET | ✅(admin) | 用户偏好 (v2.0) |
| `/api/admin/notify/channels/prefs` | POST | ✅(admin) | 写用户偏好 (v2.0) |
| `/api/admin/notify/templates` | GET | ✅(admin) | 通知模板 (v2.0) |
| `/api/uploads` | POST | ✅ | 文件上传 (v2.0) |
| `/api/uploads/signed-url` | GET | ✅ | signed URL (v2.0) |
| `/api/uploads` | DELETE | ✅ | 删除文件 (v2.0) |
| `/api/two-way-match/compute` | POST | ✅ | 单次匹配 |
| `/api/two-way-match/for-candidate/{id}` | GET | ✅ | 候选人 Top |
| `/api/two-way-match/for-role/{id}` | GET | ✅ | 岗位 Top |
| `/api/two-way-match/batch` | POST | ✅ | 批量匹配 |
| `/api/evaluation/mutual` | POST | ✅ | 双方互评 |
| `/api/gdpr/export` | GET | ✅ | 数据导出 |
| `/api/gdpr/all-data` | DELETE | ✅ | 删除数据 |
| `/api/gdpr/privacy` | GET | ❌ | 隐私政策 |

(原有 endpoints: candidates/roles/matches/collections/handoffs/quotes/copilot/signals/admin 保留)

---

## 🆕 v3.0 新增 API (30+ 端点)

### 政策 / 用人方画像 (P0)
| Endpoint | Method | Auth | 用途 |
|---|---|---|---|
| `/api/policy/list` | GET | ✅ | 政策列表 (按类别) |
| `/api/policy/{id}` | GET | ✅ | 政策详情 |
| `/api/policy/search` | POST | ✅ | RAG 全文检索 |
| `/api/policy/{id}/legal-risk` | GET | ✅ | 法律风险评估 |
| `/api/role/{id}/talent-image` | GET | ✅ | 岗位人才画像 |
| `/api/role/{id}/stakeholders` | GET | ✅ | StakeholderMatrix |
| `/api/role/{id}/consensus` | GET | ✅ | 多方共识度 |

### 偏见 / JD 模板 (P0)
| `/api/talent-brief/{id}/bias` | GET | ✅ | 偏见检测结果 |
| `/api/talent-brief/{id}/alternative-wording` | GET | ✅ | 替代话术 |
| `/api/jd-templates` | GET | ✅ | JD 模板列表 (10+ 行业) |
| `/api/jd-templates/{id}` | GET | ✅ | 模板详情 |
| `/api/role/{id}/jd-versions` | GET | ✅ | JD 版本历史 |
| `/api/role/{id}/jd-diff` | GET | ✅ | 版本 diff |
| `/api/role/{id}/over-spec-check` | POST | ✅ | Over-spec 检测 |

### 协同房间 / 语音 (P0)
| `/api/rooms` | GET | ✅ | 我的房间列表 |
| `/api/rooms` | POST | ✅ | 创建房间 |
| `/api/rooms/{id}` | GET | ✅ | 房间详情 + 成员 |
| `/api/rooms/{id}/messages` | GET | ✅ | 消息列表 |
| `/api/rooms/{id}/messages` | POST | ✅ | 发消息(@mention 自动触发通知) |
| `/api/rooms/{id}/ws` | WS | ✅ | 实时 WebSocket |
| `/api/rooms/{id}/reactions` | POST | ✅ | Emoji 反应 |
| `/api/voice/transcribe` | POST | ✅ | 语音转写 (Whisper) |
| `/api/voice/journal` | POST | ✅ | 转写后自动建 journal |

### 双向匹配 2.0 (P3)
| `/api/matches/{id}/explain` | GET | ✅ | 匹配解释器 (维度拆解) |
| `/api/matches/{id}/counterfactual` | POST | ✅ | 反事实分析 (如"差 1 项技能 = ?") |
| `/api/matches/{id}/mutual-view` | GET | ✅ | 双方对照视图 |
| `/api/evaluation/{id}/compare` | GET | ✅ | 双方评分对比 |
| `/api/admin/matching-quality` | GET | ✅(admin) | 匹配质量 dashboard |
| `/api/admin/matching-quality/weights` | POST | ✅(admin) | 手动调权重 |
| `/api/admin/weights` | GET/POST | ✅(admin) | 权重配置 + 自动校准 |
| `/api/admin/calibration/dry-run` | POST | ✅(admin) | 校准试运行 |

### Webhook / 公开 API (P2)
| `/api/webhooks/subscriptions` | GET/POST | ✅(admin) | 订阅管理 |
| `/api/webhooks/subscriptions/{id}` | DELETE | ✅(admin) | 取消订阅 |
| `/api/webhooks/deliveries` | GET | ✅(admin) | 投递历史 |
| `/api/webhooks/test/{id}` | POST | ✅(admin) | 测试投递 |
| `/api/public/roles` | GET | API Key | 公开岗位列表 |
| `/api/public/roles/{id}` | GET | API Key | 公开岗位详情 |
| `/api/public/matches` | GET | API Key | 公开匹配结果 |
| `/api/admin/api-keys` | GET/POST | ✅(admin) | API Key 管理 |
| `/api/admin/api-keys/{id}/revoke` | POST | ✅(admin) | 吊销 Key |

### 规则引擎 / A/B 实验 (P2)
| `/api/rules` | GET/POST | ✅(admin) | 规则 CRUD |
| `/api/rules/{id}/test` | POST | ✅(admin) | 试运行 |
| `/api/rules/{id}/enable` | POST | ✅(admin) | 启用 |
| `/api/admin/ab/experiments` | GET/POST | ✅(admin) | 实验 CRUD |
| `/api/admin/ab/{key}/results` | GET | ✅(admin) | 显著性分析 |
| `/api/admin/ab/{key}/stop` | POST | ✅(admin) | 停掉实验 |

### 审计 / 成本 (P4)
| `/api/admin/audit` | GET | ✅(admin) | 审计日志查询 |
| `/api/admin/audit/export` | GET | ✅(admin) | 审计导出 |
| `/api/admin/cost/summary` | GET | ✅(admin) | 成本汇总 |
| `/api/admin/cost/by-agent` | GET | ✅(admin) | 按 Agent 拆分 |
| `/api/admin/cost/by-tenant` | GET | ✅(admin) | 按租户拆分 |

### Action Items / Escalation
| `/api/action-items` | GET/POST | ✅ | 行动项 |
| `/api/action-items/{id}` | PATCH | ✅ | 标记完成/关闭 |
| `/api/escalation` | POST | ✅ | 升级到人工 |
---

## v4.0 新增 API (50+)

### AI 自动面试 (T1301)
| `/api/ai-interview/start` | POST | ✅ | 启动 AI 面试会话 |
| `/api/ai-interview/{id}/questions` | GET | ✅ | 获取题目 |
| `/api/ai-interview/{id}/answer` | POST | ✅ | 提交答案 |
| `/api/ai-interview/{id}/report` | GET | ✅ | 获取评估报告 |

### Offer 比较 + 谈判 (T1302)
| `/api/offers/compare` | POST | ✅ | 多 Offer 比较 |
| `/api/offers/{id}/negotiation` | POST | ✅ | 生成谈判脚本 |
| `/api/offers/{id}/breakdown` | GET | ✅ | 总包拆分 |
| `/api/offers/market-band` | GET | ✅ | 行业百分位 |

### 招聘漏斗 + 渠道 ROI (T1303)
| `/api/funnel` | GET | ✅ | 漏斗视图 |
| `/api/funnel/conversion` | GET | ✅ | 阶段转化率 |
| `/api/analytics/channels` | GET | ✅ | 渠道 ROI |
| `/api/analytics/channels/{channel}/attribution` | GET | ✅ | 渠道归因 |
| `/api/funnel/events` | POST | ✅ | 记录事件 |

### 订阅 + 推荐 (T1304)
| `/api/subscriptions` | GET/POST/DELETE | ✅ | 订阅管理 |
| `/api/subscriptions/match` | POST | ✅ | 匹配运行 |
| `/api/recommendations/candidates` | GET | ✅ | 推荐候选人 |
| `/api/recommendations/jobs` | GET | ✅ | 推荐岗位 |
| `/api/push/subscribe` | POST | ✅ | 推送订阅 |
| `/api/push/unsubscribe` | POST | ✅ | 取消推送 |

### 视频面试 (T1305)
| `/api/video-interview/schedule` | POST | ✅ | 排程 (Zoom / 腾讯) |
| `/api/video-interview/{id}/cancel` | POST | ✅ | 取消 |
| `/api/video-interview/{id}/recording` | GET | ✅ | 录制链接 |
| `/api/video-interview/webhook` | POST | — | Zoom webhook |

### 测评 (T1306)
| `/api/assessments/invite` | POST | ✅ | 发送测评邀请 |
| `/api/assessments/{invitation_id}` | GET | ✅ | 获取结果 |
| `/api/assessments/{invitation_id}/apply` | POST | ✅ | 加权到匹配 |

### 背景调查 (T1307)
| `/api/background-check/trigger` | POST | ✅ | 触发背调 (Checkr) |
| `/api/background-check/{id}/status` | GET | ✅ | 查询状态 |
| `/api/background-check/pre-offer` | POST | ✅ | 自动 offer 前触发 |
| `/api/background-check/webhook` | POST | — | Checkr webhook |

### ATS 双向同步 (T1501)
| `/api/ats/integrations` | GET/POST | ✅ | 集成管理 |
| `/api/ats/integrations/{id}/sync` | POST | ✅ | 立即同步 |
| `/api/ats/integrations/{id}/history` | GET | ✅ | 同步历史 |
| `/api/ats/conflicts` | GET | ✅ | 冲突列表 |
| `/api/ats/conflicts/{id}/resolve` | POST | ✅ | 解决冲突 |

### 计费 (T1405)
| `/api/billing/plans` | GET | — | 价格套餐 |
| `/api/billing/subscribe` | POST | ✅ | 创建订阅 |
| `/api/billing/subscriptions` | GET | ✅ | 我的订阅 |
| `/api/billing/cancel` | POST | ✅ | 取消订阅 |
| `/api/billing/checkout/stripe` | POST | ✅ | Stripe checkout (海外) |
| `/api/billing/checkout/wechat` | POST | ✅ | 微信支付 (国内) |
| `/api/billing/checkout/alipay` | POST | ✅ | 支付宝 (国内) |
| `/api/billing/webhook/stripe` | POST | — | Stripe webhook |
| `/api/billing/webhook/wechat` | POST | — | 微信回调 |

### 多端 / 集成 (T1203/T1204)
| `/api/miniprogram/auth/login` | POST | — | 微信小程序 code2session |
| `/api/miniprogram/auth/phone` | POST | ✅ | 手机号登录 |
| `/api/miniprogram/auth/me` | GET | ✅ | 当前用户 |
| `/api/corp/dingtalk/bind` | POST | ✅ | 钉钉绑定 |
| `/api/corp/dingtalk/signature` | POST | — | 微应用签名校验 |
| `/api/corp/feishu/bind` | POST | ✅ | 飞书绑定 |
| `/api/corp/feishu/signature` | POST | — | 应用签名校验 |

### 合规 / GDPR (T1201/T1202)
| `/api/gdpr/consent` | POST | ✅ | 记录同意 |
| `/api/gdpr/consent` | GET | ✅ | 查询同意 |
| `/api/gdpr/consent/withdraw` | POST | ✅ | 撤回同意 |
| `/api/gdpr/me/export` | POST | ✅ | 数据导出 (可携权) |
| `/api/gdpr/me/forget` | POST | ✅ | 被遗忘权 |

### 全局搜索 (T1404)
| `/api/search` | GET | ✅ | 跨实体全文搜索 |
| `/api/search/suggestions` | GET | ✅ | 搜索建议 (⌘K) |
| `/api/search/recent` | GET | ✅ | 最近搜索 |

### Pilot (T1106)
| `/api/pilot/invite` | POST | ✅(admin) | 邀请试用 |
| `/api/pilot/programs` | GET | ✅ | 试用项目列表 |
| `/api/pilot/{id}/feedback` | POST | ✅ | 反馈提交 |
| `/api/pilot/{id}/survey` | GET | ✅ | 调研问卷 |

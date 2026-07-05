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
| `/api/two-way-match/compute` | POST | ✅ | 单次匹配 |
| `/api/two-way-match/for-candidate/{id}` | GET | ✅ | 候选人 Top |
| `/api/two-way-match/for-role/{id}` | GET | ✅ | 岗位 Top |
| `/api/two-way-match/batch` | POST | ✅ | 批量匹配 |
| `/api/evaluation/mutual` | POST | ✅ | 双方互评 |
| `/api/gdpr/export` | GET | ✅ | 数据导出 |
| `/api/gdpr/all-data` | DELETE | ✅ | 删除数据 |
| `/api/gdpr/privacy` | GET | ❌ | 隐私政策 |

(原有 endpoints: candidates/roles/matches/collections/handoffs/quotes/copilot/signals/admin 保留)
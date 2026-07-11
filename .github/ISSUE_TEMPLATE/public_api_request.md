---
name: 公开 API Key / 端点需求
about: 新增公开 API endpoint / 新 scope / rate limit 调整
title: "[Public API] "
labels: ["public-api", "api"]
assignees: []
---

## 任务类型

- [ ] 新增公开 endpoint
- [ ] 新增 scope
- [ ] 调整 rate limit
- [ ] API Key 申请(给客户)

## Endpoint 详情

- **路径**: `/api/public/xxx`
- **方法**: GET / POST / PATCH / DELETE
- **Auth**: API Key(必须) / OAuth(可选)
- **Scope**: `read:roles` / `read:matches` / 等

## 请求 / 响应

```json
// Request
{
  "field1": "string"
}

// Response
{
  "data": [...],
  "next_cursor": "..."
}
```

## Rate Limit

- [ ] 默认 60 req/min
- [ ] 自定义: __ req/min

## 安全

- [ ] 脱敏(候选人姓名 / 联系方式)
- [ ] 字段过滤(避免泄露内部 ID)
- [ ] 审计 log(记录调用方)

## 文档

- [ ] 更新 `docs/API.md`
- [ ] 写 OpenAPI 注释
- [ ] 客户 onboarding 指南

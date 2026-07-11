---
name: Webhook 集成需求
about: 集成新事件类型 / 新外部系统 / Webhook 投递问题
title: "[Webhook] "
labels: ["webhook", "integration"]
assignees: []
---

## 任务类型

- [ ] 新增事件类型(在 `api/webhooks.py`)
- [ ] 集成新外部系统(钉钉/飞书/企业微信之外)
- [ ] 投递失败排查
- [ ] 订阅管理 UI 改进

## 事件详情

- **事件名**: `xxx.yyy`(如 `match.created`)
- **触发位置**: 哪个 Agent / API
- **Payload 字段**:

```json
{
  "field1": "string",
  "field2": 123
}
```

## 接收方信息

- **系统名**:
- **URL Pattern**:
- **认证方式**: HMAC / Bearer / OAuth / 其他
- **幂等性**: receiver 是否能处理重复投递

## 期望行为

- [ ] 重试策略(指数退避 / 固定间隔)
- [ ] 失败告警(钉钉 / 邮件)
- [ ] dead letter 处理

## 测试

- [ ] 本地用 `webhook.site` 验证签名
- [ ] 模拟 5xx 触发重试
- [ ] 模拟超时触发熔断

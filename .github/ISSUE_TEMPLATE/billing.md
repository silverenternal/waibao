---
name: 计费 / Billing
about: 计费系统 (Stripe / 微信支付 / 支付宝) 相关
title: "[billing] "
labels: ["billing", "area:payment"]
---

## 类型 / Type

- [ ] 订阅开通 / 续费异常
- [ ] Webhook 推送失败
- [ ] 价格变更 / 套餐调整
- [ ] 对账 / 财务报表问题
- [ ] 退款 / 取消订阅
- [ ] 货币 / 汇率问题

## 涉及供应商 / Provider

- [ ] Stripe (国际信用卡)
- [ ] 微信支付 (国内)
- [ ] 支付宝 (国内)
- [ ] 其他: __________

## 区域 / Region

- [ ] region-cn
- [ ] region-sg
- [ ] region-us

## 描述 / Description

清楚描述问题.

## 复现步骤

1. 用户 / 订阅 ID: `xxx`
2. 操作: 创建订阅 / 升级 / 取消
3. 期望: ...
4. 实际: ...

## 关联数据

- subscription_id: `xxx`
- customer_id: `xxx`
- invoice_id: `xxx`
- payment_intent_id: `xxx`

## 日志 / Logs

```
(粘贴相关日志, 隐藏敏感信息)
```

## 影响范围

- [ ] 单个用户
- [ ] 整个区域 (估算影响人数)

## 财务影响

- 涉及金额: ¥XXX / $XXX
- 是否需要退款: 是 / 否
- 已通知 Finance: 是 / 否

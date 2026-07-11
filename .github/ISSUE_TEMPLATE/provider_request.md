---
name: 🔌 Provider Request
about: 请求新增 / 替换 Provider 抽象层中的外部供应商
title: '[PROVIDER] '
labels: provider, enhancement
assignees: ''
---

## Provider 类型

请选择要接入的 capability 维度:

- [ ] LLM (大语言模型)
- [ ] Embedding (向量化)
- [ ] Vision (多模态视觉)
- [ ] OCR (图片文字识别)
- [ ] STT (语音转文字)
- [ ] Notify (通知通道)
- [ ] CompanyLookup (工商信息查询)
- [ ] 其他: ___

## 供应商名称

例如: OpenAI / Anthropic / DeepSeek / Zhipu / Tongyi / Moonshot / 腾讯云 OCR / 百度 OCR / 阿里云 OCR / Whisper / 钉钉 / 飞书 / 企业微信 / SendGrid SMTP / 天眼查 / 启信宝 / 自定义 Webhook

## 接口风格

- [ ] OpenAI 兼容 (chat/completions, embeddings)
- [ ] Anthropic Messages API
- [ ] 原生 SDK (Python 客户端)
- [ ] REST + Bearer Token
- [ ] REST + HMAC 签名
- [ ] Webhook 推送
- [ ] 其他: ___

## 鉴权方式

- API Key (Header)
- API Key (Query Param)
- OAuth 2.0
- HMAC-SHA256 签名
- AK/SK 签名 (阿里云风格)
- 其他: ___

## 必要的环境变量

列出该 provider 需要的全部 ENV 变量,例如:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxx
ANTHROPIC_BASE_URL=https://api.anthropic.com
```

## 文档链接

- 官方文档 URL: ___
- 控制台申请 API Key: ___
- 价格表 / 计费说明: ___

## 模型 / 能力差异

列出默认模型、context window、最大输出 token、特殊能力 (function calling / vision / streaming)。

## 替代现状

是否要替换已有 provider?如果是,说明迁移路径(配置切换 / 双写期 / 灰度策略)。

## 测试场景

至少 3 个测试用例:

1. happy path (正常调用)
2. retry (网络抖动 / 5xx 重试)
3. circuit breaker (连续失败熔断)

## 验收标准

- [ ] 实现 `providers/<capability>/<name>_provider.py`,继承对应基类
- [ ] 在 `providers/registry.py` 注册新 provider
- [ ] 加入 `providers/config.example.env` 注释示例
- [ ] 在 `providers/tests/` 添加至少 3 个单元测试
- [ ] README 与 docs 同步更新
- [ ] CI pytest 全绿
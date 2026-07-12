# 钉钉 / 飞书 Webhook 集成文档 (T1103)

waibao 通知链路支持 6 个 channel,本文档覆盖两个最常用群机器人: **钉钉** 和 **飞书**。

---

## 1. 钉钉群机器人

### 1.1 创建机器人步骤

1. 打开目标钉钉群 → 「群设置」 → 「智能群助手」 → 「添加机器人」 → 「自定义」
2. 填写机器人名字 (例如 `waibao-bot`)
3. **关键**: 勾选「加签」 — 生成 `SEC...` 形式的 secret (用于签名)
4. 勾选消息类型: `文本` / `Markdown` / `ActionCard` (按需)
5. 安全设置 → 至少勾选一个:
   - **自定义关键词**: 消息必须包含至少一个关键词才推送 (推荐)
   - **加签**: HMAC-SHA256 签名校验 (已实现)
   - **IP 白名单**: 限制出口 IP (生产强烈推荐)
6. 复制 webhook URL (包含 `access_token=...`)

### 1.2 配额

| 项 | 限制 |
| --- | --- |
| 单群消息频率 | 20 条/分钟 (超出 429) |
| 单条消息长度 | markdown 5000 字 / link 200 字 |
| 群数 | 不限 |

### 1.3 签名算法

```
timestamp = str(round(time.time() * 1000))   # 毫秒
string_to_sign = f"{timestamp}\n{secret}"
hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
sign = base64.b64encode(hmac_code).decode("ascii")

# 注入 URL
url = f"{webhook}&timestamp={timestamp}&sign={sign}"
```

### 1.4 配置

```bash
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=..."
export DINGTALK_SECRET="SEC..."   # 加签模式下必填
```

### 1.5 消息类型支持

| NotifyMessage 字段 | 钉钉 msgtype |
| --- | --- |
| `html` 非空 | `markdown` |
| `html` 为 None,`body` 非空 | `text` |
| `metadata.atMobiles` | `at.atMobiles` |

### 1.6 测试运行

```bash
cd backend
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=..."
export DINGTALK_SECRET="SEC..."   # 可选
pytest -m real_api providers/notify/tests/test_dingtalk_real.py -v
```

---

## 2. 飞书群机器人

### 2.1 创建机器人步骤

1. 打开目标飞书群 → 「群设置」 → 「群机器人」 → 「添加机器人」 → 「自定义机器人」
2. 填写机器人名字 + 描述
3. **关键**: 勾选「签名校验」 — 系统生成 `secret` 字符串
4. 安全设置:
   - **自定义关键词**: 消息必须包含关键词
   - **签名校验**: HMAC-SHA256 (key 直接是 secret)
   - **IP 白名单**: 出口 IP
5. 复制 webhook URL (类似 `https://open.feishu.cn/open-apis/bot/v2/hook/<uuid>`)

### 2.2 配额

| 项 | 限制 |
| --- | --- |
| 单群消息频率 | 100 条/分钟 |
| 单条消息长度 | interactive card 30 KB |
| 群数 | 不限 |

### 2.3 签名算法

**注意: 飞书签名与钉钉不同, key 直接是 secret 字符串本身,不是 `secret.encode()`**

```
timestamp = str(int(time.time()))   # 秒
string_to_sign = f"{timestamp}\n{secret}"
hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
sign = base64.b64encode(hmac_code).decode("ascii")

# 注入 payload (不是 URL!)
payload = {
    "timestamp": timestamp,
    "sign": sign,
    "msg_type": "interactive",
    "card": {...},
}
```

### 2.4 配置

```bash
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/..."
export FEISHU_SECRET="..."   # 签名校验模式下必填
```

### 2.5 消息类型支持

| NotifyMessage 字段 | 飞书 msg_type |
| --- | --- |
| (任意) | `interactive` (消息卡片) |

### 2.6 测试运行

```bash
cd backend
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/..."
export FEISHU_SECRET="..."   # 可选
pytest -m real_api providers/notify/tests/test_feishu_real.py -v
```

---

## 3. 重试与降级

两个 provider 都装饰了 `@with_resilience(retry=RetryPolicy(max_retries=2, base_delay=0.8))`:
- 5xx → 自动重试 2 次 (指数退避 0.8s / 1.6s)
- 4xx (除 429) → 不重试, 直接抛 ProviderError
- 429 → 退避后重试

如需添加降级 (主通道失败 → 备用 webhook):
```python
primary = DingTalkProvider(secret="...")
backup = FeishuProvider(secret="...")

try:
    await primary.send(msg)
except ProviderError:
    await backup.send(msg)
```

---

## 4. 申请 Checklist

- [ ] 钉钉群已创建 + 机器人已添加 + webhook URL 已复制
- [ ] 钉钉 secret 已生成 (如启用签名)
- [ ] `DINGTALK_WEBHOOK` + `DINGTALK_SECRET` 已 export
- [ ] 飞书群已创建 + 机器人已添加 + webhook URL 已复制
- [ ] 飞书 secret 已生成
- [ ] `FEISHU_WEBHOOK` + `FEISHU_SECRET` 已 export
- [ ] `pytest -m real_api providers/notify/tests/ -v` 全绿
- [ ] 生产环境已配置 IP 白名单

---

## 5. 安全建议

1. **必须启用签名校验** — 防止 webhook 被恶意调用
2. **必须配置 IP 白名单** — 钉钉 / 飞书后台添加生产出口 IP
3. **webhook URL 等同于密码** — 不要分享到 wiki / IM / git
4. **敏感消息用 @指定人 + 加密字段** — 避免明文出现在卡片上
5. **定期轮转 secret** — 季度审计, 异常时立即重置

---

## 6. 故障排查

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| `errcode=310000` 钉钉 | 签名错误 | 检查 secret 拼写, timestamp 单位(毫秒) |
| `errcode=40001` 飞书 | timestamp 过期 | 服务端时钟偏差, NTP 同步 |
| `errcode=43004` 飞书 | 消息含禁词 | 移除关键词列表里的词 |
| `HTTP 429` | 限流 | 降速, 启用 retry |
| `errcode=300003` 钉钉 | IP 不在白名单 | 后台添加出口 IP |
| 消息能推到测试群,但生产群收不到 | 自定义关键词不匹配 | 消息体包含已配置的关键词 |

---

## 7. 监控指标

建议在生产中埋点:
- `dingtalk.send.duration_ms` (histogram)
- `dingtalk.send.errcode` (counter, label=errcode)
- `feishu.send.code` (counter, label=code)
- `webhook.retry.count` (counter)

如 errcode 非 0 / code 非 0 比例 > 5%,触发告警。
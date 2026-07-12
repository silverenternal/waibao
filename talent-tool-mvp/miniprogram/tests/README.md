# T1203 — Real Device / 真机测试清单

uni-app 跨端编译后,平台相关代码 (uni.login / uni.getUserProfile / 录音 / 摄像头)
必须在真实微信开发者工具 + 真机预览上验证。本文件列出最小验收用例。

## 1. 微信开发者工具 (IDE) 自测

| 用例 | 步骤 | 期望 |
| --- | --- | --- |
| 编译产物 | `npm run dev:mp-weixin` → 微信开发者工具打开 `dist/build/mp-weixin` | 编译成功,无 ESLint / TypeScript 报错 |
| 登录页 | 不勾协议点登录 | 提示需勾协议 (T1203 后端 `wechat-login` 仍能返回 token,前端做引导) |
| 微信一键登录 | IDE 中点登录 (模拟 wx.login) | 跳转到求职者首页,顶部显示昵称 |
| 智能对话 | 输入文字 → 发送 | 出现 AI 回复气泡,可滚动到底部 |
| 语音日记 | 点击"语音录入" → 说完 → "保存并分析" | 日记列表新增条目,显示情绪标签 |
| 工单推进 | HR 工作台 → 工单概览 → 点击推进 | 状态从 open → in_progress → closed 流转 |

## 2. 真机预览 (iOS / Android)

- 通过 IDE 右上角"预览"扫码,在真机上跑通以下核心流程:
  - [ ] 微信一键登录 (走真实 wx.login, 真实 code2session)
  - [ ] 手机号快捷登录 (open-type="getPhoneNumber" 必须企业主体小程序)
  - [ ] 网络断开重连: `request` 自动重试最多 2 次
  - [ ] 后端 401 时自动跳登录页

## 3. H5 兼容

- `npm run dev:h5` 后在 Chrome / Safari 验证以下页面:
  - 智能对话页滚动到底部
  - TabBar 切换不丢 state
  - Pinia 持久化在 `wx_session_v1` 字段下,关闭浏览器后失效 (Web 无持久)

## 4. App 兼容 (可选)

- `npm run dev:app` → HBuilderX 真机运行基座
- 录音组件调用原生 RecorderManager (微信里是 wx.startRecord)

## 5. 自动化测试

```bash
cd miniprogram
npm install
npm run test         # vitest 单元测试 (Node 环境)
npm run typecheck    # vue-tsc
npm run lint         # eslint
```

CI 流水线必须保证以上三个命令全部通过。
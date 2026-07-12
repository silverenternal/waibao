# T1203 — 微信小程序发布 / 部署文档

> waibao v4.0 招聘智能体 — 微信小程序 (uni-app 跨端)
> 适用版本: miniprogram v1.0.0 / backend FastAPI v3.0.0+

---

## 目录

1. [前置准备](#1-前置准备)
2. [AppID 申请流程](#2-appid-申请流程)
3. [开发者工具下载](#3-开发者工具下载)
4. [本地开发](#4-本地开发)
5. [后端兼容配置](#5-后端兼容配置)
6. [小程序后台配置 (审核必看)](#6-小程序后台配置-审核必看)
7. [类目选择](#7-类目选择)
8. [用户隐私协议 (必填,否则审核不通过)](#8-用户隐私协议-必填否则审核不通过)
9. [提交审核与发布](#9-提交审核与发布)
10. [常见审核驳回原因](#10-常见审核驳回原因)
11. [运维与监控](#11-运维与监控)

---

## 1. 前置准备

| 资源 | 说明 |
| --- | --- |
| 营业执照 | 仅企业主体可申请"工具 / 商务"类目并获得完整功能 |
| 微信小程序账号 | mp.weixin.qq.com 注册 |
| AppID | 见下文申请流程 |
| 服务器域名 | 后端 API 必须为 HTTPS,且备案 |
| 备案号 | 工信部 ICP 备案 + 公安备案 |

---

## 2. AppID 申请流程

1. 访问 https://mp.weixin.qq.com/wxopen/waregister?action=step1
2. 选择主体类型:
   - **企业** (推荐,支持手机号快速验证组件、客服消息、支付)
   - 个人主体仅支持"工具 - 效率"类目,且**无法使用 getPhoneNumber**
3. 填写主体信息:
   - 企业名称、统一社会信用代码
   - 法人微信扫码验证
   - 对公账户打款验证 (1 分钱)
4. 获得 AppID + AppSecret 后,**立即** 在 mp.weixin.qq.com 配置:
   - **开发管理 → 开发设置**:
     - `AppID(小程序ID)` 复制到 `miniprogram/project.config.json` 的 `appid` 字段
     - `AppSecret(小程序密钥)` + IP 白名单同步到后端 `WECHAT_SECRET`
   - **开发管理 → 服务器域名**:
     - `request 合法域名`: 后端 API 域名,例如 `https://api.waibao.example.com`
     - `uploadFile 合法域名`: 同上 (用于语音日记上传)
     - `downloadFile 合法域名`: 用于音频播放
5. 在项目根 `miniprogram/.env.production` 中配置:
   ```
   VITE_API_BASE_URL=https://api.waibao.example.com
   VITE_APP_ENV=prod
   ```

---

## 3. 开发者工具下载

- **微信开发者工具**: https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html
  - 选择稳定版 Stable Build (macOS / Windows)
  - 安装后用**微信扫码登录** (需要是该 AppID 的开发者或体验成员)
- **HBuilderX (可选)**: https://www.dcloud.io/hbuilderx.html
  - 用于真机运行 / App 打包,内置 uni-app 编译
- **VS Code**: 编辑源码,推荐安装 `uni-app-snippets` 插件

---

## 4. 本地开发

```bash
cd talent-tool-mvp/miniprogram
npm install

# 编译并热更新到微信开发者工具
npm run dev:mp-weixin
# 输出: dist/build/mp-weixin/  ← 用微信开发者工具"导入项目"指向该目录

# H5 (浏览器调试)
npm run dev:h5

# App (HBuilderX 真机运行)
npm run dev:app
```

### 单元测试

```bash
npm run test         # vitest,跑 Node 环境的工具/API/store 单测
npm run typecheck    # vue-tsc
npm run lint         # eslint
```

CI 必须保证以上三个命令全部通过再合并 PR。

---

## 5. 后端兼容配置

### 5.1 后端环境变量

在 `talent-tool-mvp/backend/.env` 中追加:

```ini
# 微信小程序登录
WECHAT_APPID=wx0123456789abcdef
WECHAT_SECRET=your_app_secret_here
MOBILE_JWT_ENABLED=true
# 可选: 独立签名密钥。空 = 复用 SUPABASE_JWT_SECRET
MOBILE_JWT_SECRET=
```

修改后重启后端:

```bash
cd talent-tool-mvp/backend
uvicorn main:app --reload --port 8000
```

### 5.2 验证登录链路

```bash
# 1. 拉取小程序公开配置
curl https://api.waibao.example.com/api/auth/miniprogram-config

# 2. 用 IDE 模拟的 wx.login code 调用登录
curl -X POST https://api.waibao.example.com/api/auth/wechat-login \
  -H "Content-Type: application/json" \
  -d '{"code":"mock_code_for_test_001","nickname":"测试"}'
# 返回: { token, openid, user: {id, email, role}, is_new_user, expires_in }

# 3. 用返回的 token 调用受保护接口
curl https://api.waibao.example.com/api/users/me \
  -H "Authorization: Bearer <token>"
```

后端 `/api/auth/wechat-login` 已实现:

- 真实 `code2session` (配置 WECHAT_APPID + WECHAT_SECRET 时)
- 缺失凭证时**确定性 mock** (CI / 开发用)
- 失败时**兜底 fallback**,避免阻塞登录
- 7 天有效期的 JWT,签名与移动端秘钥隔离

### 5.3 与现有 API 的兼容

`backend/api/auth.py` 中 `get_current_user` 已改造为同时接受:

- 旧 Supabase Web JWT (`iss` 未设置, 带 `aud`)
- 新移动端 JWT (`iss=waibao-miniprogram`, 带 `openid`)

无需修改任何业务路由即可在小程序中调用。

---

## 6. 小程序后台配置 (审核必看)

### 6.1 基础设置

`mp.weixin.qq.com → 设置 → 基本设置`:

| 字段 | 值 |
| --- | --- |
| 小程序名称 | `waibao` (或 `招聘智能体`) |
| 小程序简介 | 让 AI 成为你的求职合伙人,简历优化 / 岗位匹配 / 面试准备 |
| 小程序头像 | 200×200 PNG/JPG, ≤ 100KB |
| 服务类目 | `工具 - 效率` (求职端) + `商务 - 人力资源` (HR 端,推荐双类目) |
| 标签 | AI、招聘、求职、HR |

### 6.2 开发管理

`开发管理 → 开发设置`:

- **AppID**: 复制到 `project.config.json`
- **AppSecret(小程序密钥)**: 点击"生成",复制到后端 `.env`
- **IP 白名单**: 添加后端出口 IP (避免 AppSecret 被盗用)
- **服务器域名**:
  - `request 合法域名`: `https://api.waibao.example.com`
  - `uploadFile 合法域名`: `https://api.waibao.example.com`
  - `downloadFile 合法域名`: `https://cdn.waibao.example.com` (语音日记 CDN)

### 6.3 第三方设置

- **业务域名**: 不需要 (本小程序不嵌 H5)
- **微信支付**: 仅企业认证且需收款时开通 (本 v1.0 不强制)

---

## 7. 类目选择

### 7.1 推荐: 双类目

| 类目 | 适用页面 | 所需资质 |
| --- | --- | --- |
| **工具 - 效率** | login / chat / profile / journal / plan / tickets | 无 (个人可申请) |
| **商务 - 人力资源** | employer/* (HR 工作台) | 营业执照 + 人力资源服务许可证 (部分地区) |

### 7.2 提交资质

- 营业执照 (彩色扫描件)
- 人力资源服务许可证 (如选"商务 - 人力资源")
- ICP 备案号
- 小程序图标 + 类目图标 (128×128 PNG)
- 类目说明 (≤ 200 字): 详细描述 AI 招聘功能如何服务求职者与 HR

---

## 8. 用户隐私协议 (必填,否则审核不通过)

微信 2023 年起强制要求**先弹窗**用户同意隐私协议才能调用任何用户信息接口。
本项目 `miniprogram/src/pages/login/index.vue` 已实现同意入口。

### 8.1 后台填写

`设置 → 服务内容声明 → 用户隐私保护指引`:

逐项勾选小程序实际使用的接口:

| 接口 | 用途 |
| --- | --- |
| **获取用户的微信昵称、头像** | `getUserProfile` 用于完善用户画像 |
| **获取用户手机号** | `getPhoneNumber` 用于快捷登录 |
| **获取用户地理位置** | 附近岗位推荐 (v1.1 启用,先勾选占位) |
| **使用麦克风** | 语音日记录制 (`startRecord`) |
| **使用摄像头** | 简历拍照上传 (v1.1) |
| **读取存储** | 缓存登录态 / 离线日记 |
| **写入存储** | 缓存登录态 / 离线日记 |

- 处理方: 北京某某科技有限公司 (主体名称)
- 存储期限: 用户注销账号后立即删除
- 联系方式: privacy@waibao.example.com

### 8.2 协议内容托管

微信要求协议详情必须**托管在第三方可访问页面**:

1. 创建 `https://waibao.example.com/privacy` 与 `https://waibao.example.com/terms`
2. 在 `pages/login/index.vue` 中 `openAgreement()` 改为跳转这两条 URL (替换占位实现)
3. 在后台"用户隐私保护指引"中粘贴这两条 URL

### 8.3 自定义弹窗

首次进入小程序时,若用户未同意隐私协议,**必须阻断所有 wx.* 接口**。
参考实现:

```ts
// src/utils/privacy.ts
export function ensurePrivacyAgreed(): Promise<boolean> {
  return new Promise((resolve) => {
    const agreed = uni.getStorageSync('wb_privacy_agreed');
    if (agreed) return resolve(true);
    uni.showModal({
      title: '用户协议与隐私政策',
      content: '请阅读并同意《用户协议》和《隐私政策》后继续使用',
      confirmText: '同意',
      cancelText: '不同意',
      success: ({ confirm }) => {
        if (confirm) {
          uni.setStorageSync('wb_privacy_agreed', true);
          resolve(true);
        } else {
          uni.exitMiniProgram();
          resolve(false);
        }
      },
    });
  });
}
```

---

## 9. 提交审核与发布

### 9.1 上传代码

1. `npm run build:mp-weixin` 生成 `dist/build/mp-weixin`
2. 微信开发者工具 → 上传 → 填写版本号 (1.0.0) 与项目备注
3. 在 mp.weixin.qq.com "版本管理" 看到刚上传的体验版

### 9.2 提交审核

1. **版本管理 → 提交审核**:
   - 功能页面截图 (5 张以上,涵盖求职者首页、聊天、画像、日记、HR 工作台)
   - 测试账号 (审核员需要登录验证) — 在 `pages/login/index.vue` 的 mock 路径下放一个 demo 账号
   - 类目资质 (已在第 7 节准备)
2. **审核时间**: 通常 1-3 个工作日,加急 2 小时 (企业认证)

### 9.3 发布

审核通过后:

1. 点击"发布" → 全网生效 (微信用户搜索/扫码即可用)
2. 或"灰度发布" → 先放 5% 用户验证稳定性
3. 配置客服 (微信客服 / 企微) 让用户能反馈

### 9.4 版本回滚

若线上事故:

`版本管理 → 线上版本 → 回退`,立即生效,但限制每月 ≤ 5 次。

---

## 10. 常见审核驳回原因

| 原因 | 解决方案 |
| --- | --- |
| **未填写隐私协议** | 第 8 节 |
| **类目不符** | 选"工具-效率"或"商务-人力资源",不要选"社交/社区" |
| **测试账号无法登录** | 给审核员一个真实可用的 wx.login mock + 后端 mock |
| **未提供体验码 / 二维码** | 提交审核前在"成员管理"添加审核员的微信 |
| **HTTPS 域名未配置** | 第 5.1 节 + 第 6.2 节 |
| **登录按钮无协议勾选** | 已在 `pages/login/index.vue` 实现 |
| **小程序名称含敏感词** | "招聘"、"AI" 可用;避开"贷款"、"医疗" |
| **代码包超过 2MB (主包)** | `vite.config.ts` 已配置 `manualChunks: undefined`,持续监控 |
| **未声明 wx.getLocation 使用** | 在 `manifest.json` 提前 `requiredPrivateInfos: ['getLocation']` 占位 |

---

## 11. 运维与监控

### 11.1 监控指标

通过 `uni.report()` 上报到微信小程序后台:

```ts
// src/utils/monitor.ts
export function reportEvent(name: string, payload: Record<string, unknown>) {
  if (typeof wx !== 'undefined' && (wx as any).reportEvent) {
    (wx as any).reportEvent(name, payload);
  }
}
```

### 11.2 关键事件

| 事件 | 触发 | 关注指标 |
| --- | --- | --- |
| `login_success` | `/api/auth/wechat-login` 成功 | DAU / 留存 |
| `chat_turn` | 每轮对话 | 活跃度 |
| `journal_created` | 日记保存 | 7 日留存 |
| `ticket_advanced` | 工单状态推进 | HR 端活跃 |

### 11.3 错误日志

后端 `sentry_sdk` 已经覆盖 Web 端;**移动端**单独接入:

```ts
import * as Sentry from '@sentry/miniprogram';
Sentry.init({ dsn: 'https://xxx@sentry.io/miniprogram' });
```

### 11.4 灰度与回滚

- 灰度: `mp.weixin.qq.com → 版本管理 → 灰度发布` (1% / 5% / 10% / 50% / 100%)
- 回滚: `版本管理 → 线上版本 → 回退`,秒级生效
- 服务端紧急开关: 后端 `flags.json` 加 `miniprogram_maintenance`,前端在 `request.ts` 检测到时弹出"系统升级中" toast

---

## 附录 A: 工程结构

```
talent-tool-mvp/miniprogram/
├── package.json              # uni-app + Vue 3 + Pinia
├── vite.config.ts
├── tsconfig.json
├── vitest.config.ts
├── project.config.json       # 微信专用
├── project.private.config.json
├── src/
│   ├── App.vue
│   ├── main.ts
│   ├── manifest.json         # uni-app 配置
│   ├── pages.json            # 11 个页面路由 + tabBar
│   ├── pages/
│   │   ├── login/index.vue
│   │   ├── jobseeker/
│   │   │   ├── index/index.vue   (首页 / 智能对话入口)
│   │   │   ├── chat/index.vue    (对话)
│   │   │   ├── profile/index.vue (画像)
│   │   │   ├── journal/index.vue (日记+语音)
│   │   │   ├── plan/index.vue    (职业规划)
│   │   │   └── tickets/index.vue (我的工单)
│   │   └── employer/
│   │       ├── index/index.vue   (HR 工作台)
│   │       ├── tickets/index.vue (工单看板)
│   │       ├── strategy/index.vue(战略地图)
│   │       └── rooms/index.vue   (协同房间列表)
│   ├── api/
│   │   ├── config.ts             (BASE_URL/超时)
│   │   ├── request.ts            (uni.request 封装)
│   │   ├── auth.ts               (微信登录/手机号)
│   │   └── index.ts              (copilot/profile/journal/tickets/...)
│   ├── store/user.ts             (Pinia)
│   ├── components/
│   │   ├── wb-empty/
│   │   ├── wb-loading/
│   │   └── wb-card/
│   └── utils/
│       ├── format.ts
│       ├── logger.ts
│       └── wx.ts
└── tests/
    ├── setup.ts
    ├── auth.spec.ts              (vitest 单测)
    └── README.md                 (真机测试清单)
```

## 附录 B: 与后端的对应关系

| 小程序页面 | 后端接口 |
| --- | --- |
| 登录 | `POST /api/auth/wechat-login` / `phone-login` / `GET /api/auth/miniprogram-config` |
| 智能对话 | `GET/POST /api/copilot/sessions` / `POST /api/copilot/sessions/:id/messages` |
| 画像 | `GET/PATCH /api/profile/me` |
| 日记 | `GET/POST /api/journal` / `POST /api/journal/audio` (multipart) |
| 规划 | `GET /api/career-plan/me` |
| 工单 (求职者) | `GET /api/tickets/me` |
| 工单 (HR) | `GET /api/tickets` / `PATCH /api/tickets/:id/status` |
| 战略地图 | `GET /api/strategy/me` |
| 协同房间 | `GET /api/multiparty/rooms` |
| 首页推荐 | `GET /api/matches/recommend` |

后端 `/api/users/me` 可作为统一的登录态验证探针。

---

## 附录 C: 微信小程序开放接口声明清单

为方便审核员理解,提交审核时附:

1. **登录**: 微信登录 (`wx.login`) + 用户信息 (`wx.getUserProfile`) + 手机号 (`getPhoneNumber`)
2. **数据**: 录音 (`wx.startRecord`/`stopRecord`)、相册/相机 (`wx.chooseMedia`)、地理位置 (`wx.getLocation`, v1.1 启用)
3. **存储**: 微信本地缓存 (`wx.setStorageSync`)
4. **转发**: 右上角菜单"转发给朋友" - 默认开启,内容仅显示当前页标题

所有接口的实际调用位置可在源码中通过 grep `uni\.(login|getUserProfile|getPhoneNumber|startRecord|chooseMedia|getLocation|setStorageSync)` 检索。

---

> **最后更新**: 2026-07 (v4.0 实施交付)
> **维护人**: waibao 实施工程师
> **反馈渠道**: GitHub Issues / 企微群 / privacy@waibao.example.com
# Cookie 政策 (Cookie Policy)

**版本**: v1.0  
**生效日期**: 2026-07-12

---

本 Cookie 政策补充我们的《隐私政策》,说明 waibao 平台如何使用 Cookie 与同类技术。

## 一、什么是 Cookie

Cookie 是您访问网站时,浏览器存储在您设备上的小型文本文件。它们广泛用于让网站正常工作、提升性能并向运营方提供使用信息。  
同类技术包括 Web Beacon、LocalStorage、IndexedDB、SDK 等。

## 二、我们使用的 Cookie 类别

### 2.1 必要 Cookie(Strictly Necessary)
- **作用**:维持登录会话、表单防伪、负载均衡路由
- **是否需要同意**:**否**(依据 ePrivacy 指令豁免 + 《个人信息保护法》第 13 条第 2 款)
- **典型 Cookie**:`sb_token`(Supabase JWT)、`csrf`、`session`
- **保留期限**:会话级或最多 30 天

### 2.2 功能 Cookie(Functional)
- **作用**:记住您的语言、地区、深色 / 浅色主题等偏好
- **是否需要同意**:**是**
- **典型 Cookie**:`waibao_locale`、`waibao_theme`
- **保留期限**:最长 12 个月

### 2.3 分析 Cookie(Analytics)
- **作用**:匿名统计页面访问、功能使用频次,以改进产品
- **是否需要同意**:**是**
- **典型 Cookie**:`_waibao_visit`、`_waibano_session_id`(匿名化)
- **第三方**:Plausible(自托管,无跨境);Plausible Analytics 不收集 PII
- **保留期限**:最长 12 个月

### 2.4 营销 Cookie(Marketing)
- **作用**:个性化推荐广告投放(目前本平台**不使用**营销 Cookie,如启用会提前告知)
- **是否需要同意**:**是**(未来启用时)
- **保留期限**:最长 12 个月

### 2.5 跨境传输同意(Cross-border transfer)
- **作用**:标记您是否同意将去标识化数据用于跨区域功能(海外职位匹配)
- **是否需要同意**:**是**(单独同意)
- **典型 Cookie**:`waibao_xborder_consent`
- **保留期限**:12 个月

## 三、Cookie 横幅行为

我们采用 **GDPR 双层模式** + **中国"知情同意"模式**:

### 3.1 首次访问(EU / UK / 全球)
1. 显示 Cookie 横幅(底部)
2. "全部接受" / "全部拒绝" / "自定义"
3. 自定义模式下可逐类勾选
4. 必要 Cookie 默认开启,不可关闭
5. 选择会写入 `waibao_consent` cookie,有效期 12 个月
6. 用户可在任意时刻通过页脚"Cookie 设置"按钮重新调整

### 3.2 首次访问(中国大陆)
1. 显示中文横幅(顶部居中)
2. 默认:**必要** 开启;**其他全部关闭**
3. 提供"同意全部" / "仅必要" / "自定义"
4. **强调**:跨境传输同意是**单独**勾选项,不会被默认选中
5. 用户操作会记录到 audit_log(`action=consent`, `resource=consent_record`)

## 四、如何管理 Cookie

- **浏览器设置**:大多数浏览器允许您查看、删除或拦截 Cookie(Chrome / Firefox / Safari / Edge)
- **我们的横幅**:页脚的"Cookie 设置"链接
- **隐私偏好**:账户 → 隐私设置 → 同意偏好

请注意,关闭某些 Cookie 可能导致平台部分功能不可用。

## 五、第三方 Cookie

我们在使用第三方服务时,可能由其设置 Cookie,包括:

| 第三方 | 用途 | 隐私政策 |
|---|---|---|
| Supabase | 身份认证 | supabase.com/privacy |
| Plausible(自托管) | 匿名分析 | plausible.io/data-policy |
| 钉钉 / 企业微信 / 飞书 | OAuth / 通知 | 各家隐私政策 |

我们对第三方的 Cookie 不承担最终责任,请参阅其官方隐私政策。

## 六、Do Not Track / Global Privacy Control

我们尊重浏览器的 **DNT** 和 **GPC**(Global Privacy Control)信号。当检测到 GPC=1 时,我们将自动关闭分析与营销 Cookie。

## 七、本政策的变更

我们可能根据业务或法律变更调整本政策。变更会通过站内通知或邮件告知。

## 八、联系方式

- **数据保护负责人**:dpo@waibao.example  
- **邮件**:privacy@waibao.example

---

*本 Cookie 政策自 2026 年 7 月 12 日起生效。*
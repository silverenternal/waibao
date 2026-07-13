# I18N Guide (v9.1)

国际化 (i18n) 框架指南 — 面向新增语言、新增 namespace、新增翻译 key 的工程师。

## 架构总览

- 框架: `next-intl` 3.x
- 配置入口: `frontend/i18n.ts`
- Message 文件: `frontend/messages/{locale}.json`
- 支持语言: `zh-CN` (默认) / `en-US` / `ja-JP`
- 命名空间 (namespaces): `common` / `jobseeker` / `employer` / `admin` / `mothership` / `errors`

```
frontend/
├── i18n.ts                          # 路由 + locale 检测
├── messages/
│   ├── zh-CN.json
│   ├── en-US.json
│   └── ja-JP.json
└── middleware.ts                    # locale cookie 同步
```

## Locale 切换

1. 用户登录时,后端返回 `default_locale` 写入 `waibao_locale` cookie。
2. Middleware 检测 cookie,重写到对应前缀 (保留 ?lang= 优雅回退)。
3. UI 用 `LocaleSwitcher` (`components/i18n/LocaleSwitcher.tsx`) 一键切换。

```tsx
import { useLocale, useTranslations } from "next-intl";

export function Greeting() {
  const t = useTranslations("common");
  const locale = useLocale();
  return <h1>{t("hello", { name: "Waibao" })}</h1>;
}
```

## 新增翻译 key (三步)

### Step 1 — 写入 `zh-CN.json` (主语言)

```json
{
  "jobseeker": {
    "dashboard": {
      "title": "今日关怀",
      "no_card": "今天没有主动提醒"
    }
  }
}
```

### Step 2 — 同步 `en-US.json` / `ja-JP.json`

```json
// en-US.json
{ "jobseeker": { "dashboard": { "title": "Today's Care", "no_card": "No proactive reminders today" } } }

// ja-JP.json
{ "jobseeker": { "dashboard": { "title": "本日のケア", "no_card": "本日の能動的リマインダーはありません" } }
```

### Step 3 — 组件中读取

```tsx
const t = useTranslations("jobseeker.dashboard");
return <h1>{t("title")}</h1>;
```

缺失 key 时,构建期 `next-intl` 不会报错,但运行时会回退到 `en-US`,再回退到 key 字符串。
CI 会用 `scripts/check-i18n-keys.ts` 比对三个 locale 的 keys,缺一即 fail。

## 新增 Locale

1. `frontend/i18n.ts` 中 `locales` 数组加新 locale。
2. `messages/{new-locale}.json` 复制 `en-US.json` 骨架,翻译 keys。
3. `messageKeys` glob 加入 `scripts/check-i18n-keys.ts`。
4. CI 跑 `npm run check:i18n`。

## 数字 / 日期 / 货币

`next-intl` 默认使用 `Intl.*`,无需额外配置:

```tsx
new Intl.NumberFormat(locale, { style: "currency", currency: "CNY" }).format(12000);
// zh-CN → ¥12,000.00
// en-US → ¥12,000.00
// ja-JP → ¥12,000.00
```

## Plural & 插值

```json
{ "items": "{count, plural, =0 {无} one {1 项} other {# 项}}" }
```

```tsx
t("items", { count: 3 });  // "3 项"
```

## 服务端 / 客户端组件混用

- 服务端组件: `const t = await getTranslations("namespace")` 
- 客户端组件: `const t = useTranslations("namespace")`
- API 错误消息: 从 `errors.*` namespace 取,前端不直译后端字符串。

## RTL / 新语种扩展

未来新增 `ar-SA` / `he-IL` 时:

1. `<html dir>` 根据 locale 设置。
2. Tailwind 启用 `rtl:` 变体:`tailwind.config.ts` plugin。
3. Icon 镜像:`lucide-react` 的 `ArrowLeft/Right` 替换为 `ArrowStart/End`。

## 测试

- Unit: `tests/i18n.test.ts` 验证 key 一致性、缺失回退。
- E2E: `tests/i18n.spec.ts` 切换语言,断言 `lang` 属性 + 文案。

## 工具脚本

| 命令 | 作用 |
|---|---|
| `npm run check:i18n` | 比对三 locale keys,缺一即 fail |
| `npm run fix:i18n` | 自动补缺失 key (值为 key 字符串) |
| `npm run stats:i18n` | 统计每个 namespace 的 key 覆盖率 |

## 注意

- **永不** 直接在 JSX 写硬编码中文/英文字符串 (除了 type 字面量)。
- 后端错误消息永远是 key (例: `errors.auth.invalid` ),前端翻译。
- 测试 fixture 中 zh-CN 允许硬编码,其它 locale 必须从 `messages/` 取。

## 参考

- 框架: https://next-intl-docs.vercel.app
- 文件: `frontend/i18n.ts`, `frontend/middleware.ts`, `frontend/messages/*.json`
- CI: `.github/workflows/i18n.yml`

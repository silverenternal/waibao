# i18n 规范 (T801)

> 目标: 统一前/后端多语言 key,减少重复翻译,避免命名冲突,支持未来加语言低成本.

## 1. 命名规范 (强制)

### 1.1 总体格式

```
{namespace}.{area}.{component}.{field}[.{subField}]
```

- **camelCase**,全部小写,数字允许.
- **最多 4 段** (e.g. `jobseeker.journal.editor.placeholder`).
- **不要带空格 / 标点**,用 `.` 分隔.
- **不要带动词变位** (不用 `isLoading` / `wasSaved`, 用 `loading` / `saved`).

### 1.2 常用 namespace

| namespace | 用途 |
|-----------|------|
| `common`  | 全局通用 (`save` / `cancel` / `loading`) |
| `nav`     | 顶部 / 侧边导航 |
| `jobseeker` | 求职者侧 (`/jobseeker/*`) |
| `employer`  | 用人方侧 (`/employer/*`, 包括 mind + mothership) |
| `match`   | 双向匹配 |
| `policy`  | 政策浏览 |
| `jd`      | JD 编辑 / 模板 |
| `plan`    | 职业规划 |
| `admin`   | admin 后台 (webhooks / api keys / rules / ab) |
| `error`   | 错误码 / 错误提示 |
| `agent`   | AI 智能体输出 (情感 / 偏见 / 解释) |

### 1.3 命名示例

```text
common.save                          # 通用 "保存"
nav.jobseekerHome                   # 导航 "我的空间"
jobseeker.journal.editor.placeholder # 日记编辑器 placeholder
jobseeker.emotion.trend.title       # 情绪趋势页标题
employer.role.talentImage.title     # 用人方角色画像页标题
match.weakPoints.heading            # 匹配弱项
admin.webhooks.form.urlLabel        # webhooks 配置页 URL label
error.network.timeout               # 网络超时
agent.biasAlert.severity.high       # 偏见高危
```

### 1.4 禁止项

- 缩写不一致 (`btn` vs `button`)
- 中英混杂 (`common.保存`)
- 单 key 复用 (`common.submit` 给所有按钮)
- 数值硬编码 (`pageSize: 20`) 应抽到 `common.pageSize` 但实际以 prop 传入
- ICU 占位符歧义: `Hello {name}` 必须明确是 `{name}` 不是 `{user_name}`

## 2. 文件结构

```
frontend/
├── messages/
│   ├── zh-CN.json   # 默认
│   ├── en-US.json
│   └── ja-JP.json   # 机器翻译兜底
├── i18n.ts          # next-intl 配置
└── components/
    └── LocaleSwitcher.tsx
```

- 默认 `zh-CN`.
- 翻译缺失时 fallback 到 `en-US`.
- key 缺失 CI 检查: `pnpm i18n:check` (T801 实现).

## 3. 使用规范

```tsx
// 1. server component
import { getTranslations } from "next-intl/server";
const t = await getTranslations("jobseeker.journal");
return <h1>{t("editor.title")}</h1>;

// 2. client component
import { useTranslations } from "next-intl";
const t = useTranslations("common");
return <button>{t("save")}</button>;

// 3. 带变量
t("rating.value", { score: 4.5 });
// zh-CN: "评分 {score}"
// en-US: "Rating {score}"
```

## 4. PR / CI 检查

1. 新 key 必须 3 个文件都加 (CI lint 报缺失).
2. 同一 namespace 内 key 数量差异 > 20% 时 lint 警告 (翻译可能漏).
3. 已删除的 key 必须在 PR 描述里写 `i18n: removed <key>` 由 CI 检查代码引用.
4. 命名不合规 → lint 红.

## 5. 翻译 PR 模板

```md
## i18n change
- added:  jobseeker.emotion.trend.title / monthLabel / weekLabel
- changed: common.confirm (旧 "OK" → 新 "确认" / "Confirm")
- removed: legacy.common.ok (引用清理见 PR #123)

## 翻译
- zh-CN: by @xxx
- en-US: by @yyy
- ja-JP: by machine (待人工 review)
```

## 6. 已知 namespace 边界

- `nav.*` 仅出现在顶部 / 侧边导航;侧边栏二级菜单不抽 key,沿用 `nav.*` + 子后缀.
- `error.*` 仅放客户端可见提示,服务端日志不在此列.
- `agent.*` 是智能体输出自然语言,可被 prompt 直接引用.
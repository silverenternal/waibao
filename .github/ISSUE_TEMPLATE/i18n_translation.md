---
name: i18n 翻译需求
about: 新增 / 修改 i18n key,或请求某种语言的翻译
title: "[i18n] "
labels: ["i18n", "frontend"]
assignees: []
---

## 任务类型

- [ ] 新增 key(在 `frontend/messages/zh-CN.json`)
- [ ] 翻译补全(zh-CN 已有,en-US / ja-JP 缺失)
- [ ] 修改现有 key
- [ ] 翻译 review(质量)

## Key 路径

`common.xxx` / `jobseeker.xxx` / `employer.xxx` / `error.xxx`

示例:`jobseeker.home.greeting`

## 内容

**中文 (zh-CN):**

```

```

**English (en-US):**

```

```

**日本語 (ja-JP):**

```

```

## 上下文

- **使用位置**: 哪个文件 / 哪个组件
- **场景**: 按钮 / 提示 / 错误信息 / 占位符
- **变量插值**: 有 / 无 (如有,说明变量名)

## Checklist

- [ ] 三语都已写
- [ ] 跑过 `npm run i18n:check`
- [ ] 检查占位符 `{{var}}` 一致
- [ ] 复数 / 单数处理正确

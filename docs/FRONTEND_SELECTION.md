# waibao v9.0 前端开源选型

> 状态：Architecture Decision Record（ADR）候选稿  
> 适用版本：v9.0  
> 基线：v8.1 已完成 16 项需求、服务开关、数据驱动与反馈闭环  
> 目标：在保留 Next.js 16、React 19、TypeScript、Tailwind CSS、shadcn 现有投资的前提下，把前端升级为可持续演进的企业级产品。

---

## 0. 执行摘要

### 0.1 最终结论

v9.0 不应把任一外部模板整仓搬入，也不应重新实现成熟基础设施。

采用“一个主架构、五类模式库”的组合：

1. **Refine**：借鉴企业后台的资源、权限、数据提供器和路由组织；采用渐进集成，不替换 Next.js。
2. **shadcn-admin**：复制并适配后台壳层、侧栏、命令面板、表格和设置页模式。
3. **Open WebUI**：重做求职者端对话、流式响应、Markdown、附件、语音状态和主动消息。
4. **OpenResume**：重做画像确认、简历/Profile 编辑、实时预览和模板选择。
5. **Cal.com**：借鉴协同房间、日程、参与者、通知、空状态和实时状态模式。
6. **Tremor**：采用 dashboard 设计语言和图表组合，不要求整包替换现有 Recharts。

### 0.2 不采用的“大爆炸方案”

- 不用 Ant Design Pro 整体替换 shadcn：会引入第二套设计系统和 Umi 约束。
- 不直接 fork Open WebUI：其前端不是 React/Next.js，且许可证与品牌条款必须单独复核。
- 不直接 fork Cal.com、Plane、Docmost：大型 monorepo 与业务耦合过重。
- 不把 Vercel Platforms 当 admin 模板：它解决的是多租户域名与站点路由，而非后台 UX。
- 不继续扩张“页面各自写一套”的方式：v9.0 必须先建设 shell、token、数据层与状态规范。

### 0.3 当前仓库适配依据

当前前端位于 `talent-tool-mvp/frontend`，已使用：

- Next.js 16.2.1；
- React 19.2.4；
- TypeScript 5；
- Tailwind CSS 4；
- shadcn 4；
- Recharts 3；
- next-intl；
- next-auth；
- Supabase；
- Storybook 9 与 a11y addon。

因此选型原则是“保留技术栈，移植模式”，而不是“为了模板降级或改框架”。

---

## 1. 目标与约束

### 1.1 企业级前端定义

v9.0 的“企业级”至少意味着：

- 信息架构统一，不再有多套 admin 路径与视觉语言；
- 权限、服务开关、租户与菜单来自同一策略源；
- 页面具备 loading、empty、error、offline、permission denied 状态；
- 列表具备筛选、排序、分页、批量操作、保存视图和导出；
- 表单具备校验、草稿、离开确认、失败恢复和审计反馈；
- 实时页面具备连接状态、重连、冲突提示和降级路径；
- 关键操作具备可访问名称、键盘路径、焦点管理和对比度保障；
- 移动端不是缩小桌面端，而是有明确的响应式信息优先级；
- 组件通过 Storybook、视觉回归和交互测试进入产品；
- 依赖的许可证、维护状态、升级成本可被治理。

### 1.2 硬约束

- 保持 Next.js App Router。
- 保持 React 与 TypeScript strict。
- 保持 Tailwind + shadcn 作为主视觉系统。
- 保持 next-intl 国际化能力。
- 保持现有 FeatureGate / ServiceToggle 语义。
- 不复制受限制许可证代码到商业闭源目录。
- 不把动态 GitHub stars 当质量门槛。

### 1.3 星标口径

GitHub stars 是动态数据，本文使用约数和区间，不把用户提示中的数字当作固定事实。

实施前应使用 GitHub API 冻结一次快照，并记录：

- `stargazers_count`；
- `license.spdx_id`；
- 默认分支最近提交时间；
- 最近 release；
- open issue 与 contributor 情况。

推荐格式：`截至 YYYY-MM-DD：约 N stars`。

---

## 2. 评估方法

### 2.1 权重

| 维度 | 权重 | 判定方式 |
|---|---:|---|
| 与现有栈兼容 | 25% | Next.js/React/Tailwind/shadcn 可否低成本复用 |
| 企业能力 | 20% | auth、RBAC、数据层、审计、i18n、实时、可访问性 |
| UX 借鉴价值 | 20% | 信息密度、状态设计、交互一致性、移动端 |
| 维护活跃度 | 15% | release、提交、issue、社区规模 |
| 许可证安全 | 10% | 是否允许商业使用、复制与修改，是否有附加条款 |
| 引入成本 | 10% | 依赖数量、框架耦合、升级和测试成本 |

### 2.2 集成级别

- **L1：设计借鉴**：只借鉴信息架构与交互，不复制代码。
- **L2：组件适配**：复制许可允许的单个组件，重写 token、类型与测试。
- **L3：npm 集成**：安装稳定 package，通过 adapter 封装。
- **L4：子系统集成**：在限定路由中采用框架能力。
- **L5：整仓 fork**：原则上禁止，必须另开 ADR 和法务审查。

### 2.3 通过门槛

每个进入生产的外部依赖必须满足：

1. 锁定精确版本或可控 semver 范围；
2. 有许可证清单与 NOTICE 处理；
3. 有 adapter，业务代码不直接散布第三方 API；
4. 有 Storybook story；
5. 有键盘和屏幕阅读器检查；
6. 有暗色、中文长文本和窄屏测试；
7. 有失败状态和可观测性；
8. 有退出方案。

---

## 3. 候选项目全景（16 项）

| 项目 | 类型 | 技术/定位 | 推荐级别 | 采用方式 |
|---|---|---|---|---|
| shadcn-admin | Admin UI | React、Vite、shadcn | 强推荐 | L2 复制适配 |
| NextAdmin | Next.js admin 模板 | Next.js、Tailwind | 观察 | L1/L2 |
| Taxonomy | shadcn 历史 demo | Next.js 示例 | 参考 | L1 |
| Platforms | 多租户 SaaS starter | Next.js App Router | 条件推荐 | L1/L2 |
| Tremor | Dashboard 组件/blocks | React、Tailwind、图表 | 强推荐 | L2/L3 |
| Refine | Headless React 框架 | 数据、auth、access control | 强推荐 | L3/L4 |
| Ant Design Pro | 中后台解决方案 | React、Ant Design、Umi | 不作主框架 | L1 |
| OpenResume | 简历生成器 | Next.js、React、Tailwind | 强推荐 | L1/L2 |
| Cal.com | 预约系统 | Next.js 企业 monorepo | 强推荐借鉴 | L1/L2 |
| Plane | 项目管理 | 大型 web monorepo | 参考 | L1 |
| Docmost | 协作文档 | monorepo、实时编辑 | 参考 | L1 |
| Chatwoot | 客服平台 | Rails + Vue 前端 | 参考 | L1 |
| AppFlowy | Notion 替代 | Flutter + Rust | 参考 | L1 |
| Open WebUI | AI 对话产品 | Svelte + Python | 强推荐借鉴 | L1，谨慎 L2 |
| LibreChat | AI 对话产品 | React/Node 生态 | 次选 | L1/L2 |
| Chatbot UI | ChatGPT 风格模板 | React/Next.js 生态 | 次选 | L1/L2 |

---

## 4. 推荐项目

## 选 1：[Refine](https://github.com/refinedev/refine) - 约 30k+ stars（动态）

- **原因**：它是面向 internal tools、admin panels、dashboards 和 B2B apps 的 headless React 框架，核心抽象与 waibao 的企业后台高度吻合。
- **原因**：数据提供器、认证提供器、访问控制、通知、路由、资源定义可以把散落页面规范收束为统一契约。
- **原因**：不强迫使用单一 UI 库，可保留 shadcn，并把框架限制在 admin/mothership 管理面。
- **借鉴什么**：Resource 驱动导航；List/Create/Edit/Show 页面语义；DataProvider；AuthProvider；AccessControlProvider；NotificationProvider；live provider。
- **借鉴什么**：列表查询参数标准化；筛选排序 URL 化；mutation 成功/失败反馈；失效与刷新策略。
- **借鉴什么**：租户、角色、服务开关共同决定资源可见性，而不是只隐藏按钮。
- **集成方式**：优先 npm 安装 headless core 与 Next.js/router 相关适配包；先做一条垂直切片，不一次迁移所有页面。
- **集成方式**：创建 waibao adapter：`dataProvider` 映射 FastAPI，`authProvider` 映射 next-auth，`accessControlProvider` 映射 RBAC + ServiceToggle。
- **集成方式**：shadcn 组件继续由本仓库维护，Refine 只负责状态与资源编排。
- **风险**：不能把“审计日志”理解为免费核心自动生成的完整企业审计产品；审计仍应由现有后端 audit API 负责。
- **风险**：Refine 的企业功能、云服务或高级能力可能有商业边界，实施前核对当前文档与许可。
- **风险**：直接让每个页面调用 hooks 会造成框架渗透；必须通过 `features/admin-platform` adapter 隔离。
- **退出方案**：adapter 对外只暴露 waibao 的 `useResourceList/useResourceMutation`，未来可换 TanStack Query 而不重写业务组件。

### Refine 借鉴清单

- 资源注册表与菜单生成；
- 权限驱动的路由守卫；
- 列表、详情、创建、编辑统一页面骨架；
- 乐观更新与撤销；
- 数据失效和实时订阅；
- API 错误归一化；
- 面包屑和页面标题约定；
- 多租户资源上下文；
- 操作成功通知；
- 删除确认与危险操作策略。

## 选 2：[shadcn-admin](https://github.com/satnaing/shadcn-admin) - 约 10k+ stars（动态）

- **原因**：视觉栈与现有 shadcn、Tailwind、TypeScript 最接近，适合补齐“后台壳层太草率”的直接问题。
- **原因**：项目明确采用 Vite，而不是 Next.js；这反而提醒我们只复制 UI 模式，不复制构建与路由结构。
- **借鉴什么**：响应式 sidebar、header、global search、command menu、主题切换、用户菜单、表格工具栏和设置布局。
- **借鉴什么**：桌面收起侧栏、移动端 sheet 导航、页面最大宽度、sticky toolbar、密集表格排版。
- **集成方式**：从许可证允许范围内逐个复制组件，改写 import、路由和 token；禁止整仓覆盖。
- **集成方式**：优先抽取 `AppShell`、`NavGroup`、`CommandPalette`、`DataTableToolbar`、`PageHeader` 五类模式。
- **集成方式**：所有复制代码保留来源注释与许可证归档，并加入 Storybook。
- **风险**：它是 dashboard UI，不是完整企业框架；没有替 waibao 解决 RBAC、审计、i18n、服务开关和后端契约。
- **风险**：Vite/TanStack Router 示例不能直接照搬到 App Router。
- **风险**：模板审美容易造成“看起来完整，业务状态仍缺失”；必须用状态矩阵验收。
- **退出方案**：复制后的组件归 waibao design system 管理，不形成运行时依赖。

### shadcn-admin 借鉴清单

- 主侧栏与二级导航；
- Command Palette；
- 表格筛选与列显隐；
- 用户头像菜单；
- 暗色模式；
- 页面 header 和 action slot；
- Settings 横向/纵向布局；
- 404/500/权限错误页；
- responsive drawer；
- skip link 与键盘导航。

## 选 3：[Open WebUI](https://github.com/open-webui/open-webui) - 约 100k+ stars（动态）

- **原因**：成熟的 AI 对话产品覆盖会话历史、流式输出、Markdown/LaTeX、附件、语音和反馈，适合求职者“知心朋友”主入口。
- **原因**：它展示了对话产品真正需要的状态密度，而不是只有左右气泡。
- **借鉴什么**：ChatBubble 层次；流式光标；停止生成；重新生成；复制；赞踩；引用；附件预览；会话搜索。
- **借鉴什么**：语音输入、免手持会话、模型/能力状态、网络断线和生成错误恢复。
- **借鉴什么**：主动 push 不应伪装成用户消息，应使用 system/event card，并明确来源、原因和操作。
- **集成方式**：以 L1 设计借鉴为主，在 React 中使用现有 shadcn、Markdown renderer 和 SSE/WebSocket API 重建。
- **集成方式**：若复制任何源码，必须逐文件核对当前 Open WebUI 许可证、品牌条款与提交时间；不能假设旧版 MIT 永久适用。
- **集成方式**：不引入 Svelte runtime，不 fork 整仓，不接管 waibao 后端会话模型。
- **风险**：Open WebUI 主前端是 Svelte，不可直接复用 React 组件。
- **风险**：许可证历史与当前条款可能变化，商业产品尤其要法务复核。
- **风险**：功能非常多，照抄会让求职主流程变成“模型控制台”；waibao 应隐藏模型复杂度。
- **退出方案**：仅保存交互规格和本地 React 组件，不产生项目运行时耦合。

### Open WebUI 借鉴清单

- 消息组与角色语义；
- Markdown、代码块、表格和引用；
- 流式状态机；
- 语音录制电平与权限状态；
- 文件上传队列；
- 消息级反馈；
- 会话侧栏与搜索；
- 快捷提示；
- 重试/继续/停止；
- 主动关怀卡与安全边界提示。

## 选 4：[OpenResume](https://github.com/xitanggg/open-resume) - 约 8k+ stars（动态）

- **原因**：与 waibao 的 Profile、简历、画像确认和 JD 模板场景直接匹配。
- **原因**：其核心价值是结构化编辑与实时预览，而不是简单上传 PDF。
- **借鉴什么**：分段表单；实时预览；ATS 友好版式；模板切换；字段顺序；技能标签；打印/PDF 体验。
- **借鉴什么**：画像确认页应允许“接受、编辑、解释来源”，而非只展示 AI 结论。
- **借鉴什么**：JD 营销页可复用模板选择、段落重排、预览和版本对比模式。
- **集成方式**：L1/L2；重建 ProfileCard、SectionEditor、TemplatePicker、PreviewPane、CompletenessMeter。
- **集成方式**：优先使用本仓库数据模型，不直接导入其 resume schema。
- **集成方式**：如采用 PDF 相关代码，逐项核对字体、浏览器兼容和第三方依赖许可证。
- **风险**：用户给出的“30k+ stars”不应作为事实写死，星标需通过 API 快照核对。
- **风险**：项目面向单份简历，waibao 还需要多版本、审计、权限和企业共享。
- **风险**：模板视觉可能不适合中文长文本，需要中文字体和分页专项测试。
- **退出方案**：所有表单和模板映射进入 waibao profile domain，不依赖外部运行时。

### OpenResume 借鉴清单

- 双栏编辑/预览；
- section 折叠与排序；
- 完整度提示；
- ATS 安全样式；
- 模板选择器；
- PDF 导出前检查；
- 本地草稿；
- 字段示例和 inline help；
- 中文长度适配；
- AI 建议的逐项采纳。

## 选 5：[Cal.com](https://github.com/calcom/cal.com) - 约 40k+ stars（动态）

- **原因**：成熟的 Next.js 企业产品，对参与者、时区、日历、通知、工作流和状态反馈处理完善。
- **原因**：waibao 的多方协同房间、规划 check-in 和面试日程与其交互模型相近。
- **借鉴什么**：参与者头像栈；可用性；时区选择；日程视图；邀请状态；提醒；改期；取消；空状态。
- **借鉴什么**：多步骤创建流程；右侧 summary；可复制邀请链接；连接状态；组织/团队上下文。
- **借鉴什么**：通知应区分待处理、成功、失败、需要人工介入。
- **集成方式**：L1 为主，少量通用 UI 在许可证许可下 L2 适配；不 fork monorepo。
- **集成方式**：日历能力优先采用现有 date-fns 与产品 API，不复制 Cal.com 的领域后端。
- **集成方式**：设计稿中标注借鉴来源，组件实现遵循 waibao token。
- **风险**：大型 monorepo 业务耦合深，复制组件可能带出内部 package 链。
- **风险**：开源与商业/企业目录边界需要逐文件核对。
- **风险**：日历交互涉及时区、DST、locale，不能只做视觉复刻。
- **退出方案**：只保留 interaction spec，本地实现基于标准日期模型。

### Cal.com 借鉴清单

- 多参与者协同；
- 日历与 agenda 双视图；
- 时区显式展示；
- RSVP 状态；
- 改期/取消流程；
- 通知偏好；
- wizard 与 summary；
- 空状态和 onboarding；
- 实时连接状态；
- 移动端底部 action bar。

## 选 6：[Tremor](https://github.com/tremorlabs/tremor) - 约 16k+ stars（动态）

- **原因**：专注 dashboard 与图表组合，能快速提升 KPI、趋势、漏斗、共识度与命中率页面的信息表达。
- **原因**：与 Tailwind 和 React 兼容，但 waibao 已有 Recharts，应优先借鉴 blocks 与视觉语法，避免重复图表栈。
- **借鉴什么**：KPI card；delta badge；时间序列；bar list；category bar；donut；legend；日期范围筛选；dashboard grid。
- **借鉴什么**：图表上方写结论，图表下方写口径与更新时间，避免“只有彩色线”。
- **借鉴什么**：命中率、偏见影响、情绪趋势需要同时提供数值、趋势、分组和可访问表格。
- **集成方式**：优先 L2 复制 blocks 的布局思想，底层继续 Recharts；仅在明确收益时安装 Tremor 包。
- **集成方式**：建立 `MetricCard`、`TrendChart`、`FunnelChart`、`ConsensusGauge`、`ChartDataTable`。
- **集成方式**：颜色全部映射语义 token，不直接使用项目默认调色板。
- **风险**：组件库版本、仓库形态和发布策略可能变化，安装前核对当前 package 文档。
- **风险**：图表组件不能代替分析口径；数据定义由后端与产品共同维护。
- **风险**：SVG 图表可访问性常被忽略，必须提供文本摘要和数据表。
- **退出方案**：图表 adapter 基于 waibao 类型，底层可在 Recharts、Tremor 或 ECharts 间切换。

### Tremor 借鉴清单

- KPI 卡；
- 趋势与同比；
- 漏斗；
- 时间范围；
- 分组 legend；
- drill-down；
- 阈值线；
- loading skeleton；
- 无数据解释；
- 图表对应数据表。

---

## 5. 其他候选项目调研

## 候选 7：[NextAdmin](https://github.com/surajondev/nextadmin)

- **定位**：Next.js admin dashboard/template。
- **可借鉴**：Next.js 路由组织、dashboard 卡片、表格与认证页布局。
- **优点**：比 Vite 模板更接近现有 App Router 工程。
- **不足**：模板能力不等于企业数据层；与 shadcn-admin、Refine 的覆盖高度重叠。
- **集成建议**：只挑选 Next.js 特有实现细节进行 L1/L2 比较，不作为主框架。
- **风险**：仓库名称相近项目较多，必须固定准确 URL、commit 与许可证。
- **结论**：观察名单。

## 候选 8：[Taxonomy](https://github.com/shadcn-ui/taxonomy)

- **定位**：shadcn 生态的历史示例应用，而非长期承诺的企业 admin 产品。
- **可借鉴**：组合式组件、内容布局、命令菜单、主题和 Next.js 示例。
- **优点**：对理解 shadcn 设计哲学有价值。
- **不足**：历史 demo 的依赖和 Next.js 模式可能过时。
- **集成建议**：L1；优先看当前 shadcn 官方文档与 registry，而不是复制旧代码。
- **风险**：把 demo 当正式框架会形成维护债务。
- **结论**：设计参考，不列入六个核心来源。

## 候选 9：[Platforms](https://github.com/vercel/platforms)

- **定位**：多租户、子域名/自定义域名的 Next.js starter。
- **可借鉴**：tenant resolution、middleware、域名路由、站点切换、缓存策略。
- **优点**：与 waibao 已有多租户和白标能力相关。
- **不足**：不是 admin UI；与现有 FastAPI/Supabase 租户模型并不完全一致。
- **集成建议**：L1/L2，针对 middleware 和 tenant switcher 单独写 ADR。
- **风险**：Vercel 平台 API、数据库和部署假设可能造成供应商绑定。
- **结论**：基础设施专题参考，不是整体 admin 选型。

## 候选 10：[Ant Design Pro](https://github.com/ant-design/ant-design-pro)

- **定位**：成熟中后台前端/设计解决方案，基于 Ant Design 与 Umi 生态。
- **可借鉴**：高密度企业表单、ProTable、查询区、批量操作、权限菜单、异常页。
- **优点**：中文企业后台经验深，复杂 CRUD 模式成熟。
- **不足**：引入后会与 shadcn 形成双设计系统，并增加 Umi/antd 依赖和 CSS/token 冲突。
- **集成建议**：只做 L1，借鉴交互与信息架构；不安装全套、不复制视觉。
- **风险**：如果某个页面单独使用 antd，会破坏 bundle、主题和可访问性一致性。
- **结论**：重要参考，不作为 v9 主框架。

## 候选 11：[Plane](https://github.com/makeplane/plane)

- **定位**：项目与产品管理平台。
- **可借鉴**：issue list、kanban、过滤器、成员协同、活动流、快捷编辑。
- **优点**：复杂工作流的信息密度和快捷操作优秀。
- **不足**：大型 monorepo，领域与 waibao 不同，部分代码许可证具有 copyleft 约束。
- **集成建议**：L1；不复制 AGPL 代码进入闭源商业前端，除非法务明确批准。
- **风险**：列表/看板功能容易无限扩张，需限制在招聘 pipeline 场景。
- **结论**：协同与 pipeline UX 参考。

## 候选 12：[Docmost](https://github.com/docmost/docmost)

- **定位**：协作文档与知识库。
- **可借鉴**：编辑器、评论、presence、分享权限、侧栏树、版本历史。
- **优点**：对 policy explainer 的引用、协作知识和审计交互有启发。
- **不足**：实时编辑器是独立复杂子系统，不应为 v9 首期引入。
- **集成建议**：L1；富文本优先采用成熟编辑器库，而非复制应用源码。
- **风险**：许可证为 AGPL 类时，网络服务修改与分发义务需要法务审查。
- **结论**：知识协作参考。

## 候选 13：[Chatwoot](https://github.com/chatwoot/chatwoot)

- **定位**：客户支持与多渠道会话平台，后端 Rails，前端主要为 Vue 生态。
- **可借鉴**：conversation inbox、assignee、标签、未读、SLA、活动时间线、内部备注。
- **优点**：HR 与候选人多方沟通的工作台模式成熟。
- **不足**：技术栈不兼容，不应复制运行时代码。
- **集成建议**：L1；借鉴 inbox 和 conversation metadata。
- **风险**：企业目录、附加许可和集成代码需逐项检查。
- **结论**：沟通运营台 UX 参考。

## 候选 14：[AppFlowy](https://github.com/AppFlowy-IO/AppFlowy)

- **定位**：Notion 替代，Flutter + Rust 跨平台应用。
- **可借鉴**：block editor、数据库视图、评论、离线优先、侧栏和快捷命令。
- **优点**：跨端、离线、结构化内容和协作状态设计成熟。
- **不足**：非 Web React 栈，组件不可直接移植。
- **集成建议**：L1；只研究交互，不复制 Flutter 代码。
- **风险**：AGPL 类许可证与跨语言迁移成本。
- **结论**：长期知识工作台参考，不进入 v9 首期依赖。

## 候选 15：[LibreChat](https://github.com/danny-avila/LibreChat)

- **定位**：多模型 AI 对话应用。
- **可借鉴**：会话、附件、工具调用、预设、消息操作和多端布局。
- **优点**：React 生态可读性通常比 Svelte 项目更接近现有栈。
- **不足**：产品重心是模型编排，而 waibao 重心是招聘任务。
- **集成建议**：作为 Open WebUI 的对照组，若某交互需 React 实现参考，再做 L1/L2。
- **风险**：依赖链和许可证需按具体文件检查。
- **结论**：Chat UI 次选。

## 候选 16：[Chatbot UI](https://github.com/mckaywatsen/chatbot-ui)

- **定位**：ChatGPT 风格前端/模板。
- **可借鉴**：轻量消息列表、输入框、会话切换和 prompt 体验。
- **优点**：结构较轻，便于理解最小可用 Chat UI。
- **不足**：企业状态、审计、多方协作、无障碍和长期维护能力需自行补齐。
- **集成建议**：L1/L2；只用于小型原型或比较输入区实现。
- **风险**：仓库所有者拼写和分支状态必须核验，不能依赖非官方镜像。
- **结论**：原型参考，不作为主来源。

---

## 6. 关键纠偏

### 6.1 Refine 不等于“自动拥有完整审计日志”

Refine 能统一资源操作和数据流，但法律合规级审计应继续由 waibao 后端完成。

前端职责是：

- 展示审计事件；
- 在敏感 mutation 上携带 correlation id；
- 显示操作影响；
- 不把前端日志当不可抵赖证据。

### 6.2 shadcn-admin 不是 Next.js 模板

它当前定位是 Shadcn + Vite 的 admin dashboard UI。

因此：

- 复制布局模式；
- 重写路由；
- 使用 Next.js server/client component 边界；
- 不搬入 Vite 配置；
- 不引入第二套路由器。

### 6.3 Open WebUI 不应被描述成 React 组件库

其主要前端为 Svelte。

因此：

- 只借鉴交互；
- React 实现由 waibao 自己的 design system 承载；
- 任何源码复制先过许可证；
- 语音/视频底层优先复用现有 LiveKit 和 realtime 能力。

### 6.4 Tremor 不必替换 Recharts

当前仓库已安装 Recharts 3.8.0。

正确做法：

- 先借鉴 Tremor blocks；
- 建立 waibao chart adapter；
- 继续用 Recharts 实现；
- 只有缺失关键能力时才增加依赖。

### 6.5 Cal.com 不等于实时协同框架

它提供优秀协作与日程产品模式，但实时同步仍需要：

- 现有 WebSocket/SSE；
- presence 模型；
- 幂等 mutation；
- 冲突处理；
- reconnect 策略。

---

## 7. 16 项甲方需求与前端映射表

| 甲方需求 | 前端页面 | 借鉴项目 | 关键组件 |
|---|---|---|---|
| 1.1 知心朋友 | `app/(jobseeker)/page.tsx`（建议新增统一入口；兼容 `app/jobseeker/dashboard/page.tsx`） | Open WebUI | ChatBubble、Composer、主动 Push 卡、会话侧栏、消息反馈 |
| 1.2 工作状态 | `app/jobseeker/journal/page.tsx` + `journal/analytics/page.tsx` | shadcn-admin + Plane | Timeline、ActionItem、筛选器、状态摘要、周复盘 |
| 1.3 频繁互动 | `app/realtime/page.tsx` + 求职者对话入口 | Open WebUI + Cal.com | Realtime 状态条、VoiceOrb、VideoPanel、重连提示、快捷回复 |
| 1.4 喜怒哀乐 | `app/jobseeker/emotion/page.tsx` + `(jobseeker)/emotion/care/page.tsx` | Tremor | EmotionTrend、情绪分布、关怀卡、数据表、危机提示 |
| 1.5 画像 | `app/jobseeker/profile/page.tsx` | OpenResume | ProfileCard、SectionEditor、来源解释、确认/纠正、完整度 |
| 1.6 规划 | `app/jobseeker/plan/page.tsx` + `plan/progress/page.tsx` | Cal.com + Plane | Milestone、Calendar、CheckIn、ProgressRing、阻塞项 |
| 2.1 真诚 HR | `app/(employer)/hr-tone/page.tsx` | Refine + shadcn-admin | ToneSettings、示例预览、版本历史、保存/回滚、权限守卫 |
| 2.2 资质 | `app/mothership/compliance-review/page.tsx` | shadcn-admin + Refine | VerificationCard、证据 Drawer、风险 Badge、审核操作、审计轨迹 |
| 2.3 战略 | `app/(employer)/strategy/feed/page.tsx` | Tremor + Chatwoot | StrategyTimeline、ImpactCard、受众筛选、已读/反馈、趋势摘要 |
| 2.4 偏见 | `app/mothership/analytics/bias-impact/page.tsx` | Tremor + shadcn | BiasWarningModal、ImpactChart、分组对比、整改动作、口径说明 |
| 2.5 JD | `app/(employer)/roles/[id]/marketing/page.tsx` | OpenResume | TemplatePicker、分段编辑、实时预览、版本 Diff、发布检查 |
| 2.6 制度 | `app/(jobseeker)/policy-explainer/page.tsx` | Open WebUI + Docmost | PolicyChat、引用卡、原文定位、追问、免责声明 |
| 2.7 多方 | `app/employer/rooms/page.tsx` + `rooms/[id]/page.tsx` | Cal.com + Chatwoot | ParticipantStack、RoomTimeline、Agenda、通知、沉默激活 |
| 2.8 共识 | `app/employer/rooms/[id]/page.tsx`（共识 tab） | Tremor | ConsensusGauge、观点分布、分歧列表、阈值、决议记录 |
| 2.9 主动 HR | `app/(employer)/hr/suggestions/page.tsx` | Refine + Plane | DailySuggestions、优先级队列、接受/忽略、批量操作、原因解释 |
| 3 双向匹配 | `app/mothership/matching/quality/page.tsx` + `app/match/page.tsx` | Tremor + shadcn-admin | HitRateDashboard、Funnel、TopMismatch、反馈闭环、时间筛选 |

### 7.1 映射执行要求

每一行都必须交付：

- 正常状态；
- 首次空状态；
- 筛选后空状态；
- loading skeleton；
- 局部失败；
- 整页失败；
- 无权限；
- 服务关闭；
- 离线/断线；
- 移动端布局；
- 键盘路径；
- 埋点与反馈入口。

### 7.2 组件复用矩阵

| 组件族 | 覆盖需求 | 首要来源 |
|---|---|---|
| AppShell / Nav / Command | 全部后台页面 | shadcn-admin、Refine |
| Chat / Composer / Message | 1.1、1.3、2.6 | Open WebUI |
| Timeline / Activity | 1.2、2.3、2.7 | Plane、Chatwoot |
| Profile / Template / Preview | 1.5、2.5 | OpenResume |
| Calendar / Participant / RSVP | 1.6、2.7 | Cal.com |
| Metric / Trend / Funnel | 1.4、2.3、2.4、2.8、3 | Tremor |
| Resource CRUD / Access | 2.1、2.2、2.9、admin | Refine |
| Verification / Audit | 2.2、2.4 | shadcn-admin + waibao backend |

---

## 8. 目标前端架构

### 8.1 分层

```text
app/                         路由与 server component 组合
features/                    业务域：jobseeker/employer/matching/admin
components/patterns/         Chat、Timeline、ResourceTable、Dashboard 等模式
components/ui/               shadcn primitives，只含视觉基础件
platform/                    auth、tenant、RBAC、service-toggle、telemetry
data/                        API client、query key、schema、error normalization
design-system/               token、theme、icons、motion、a11y
```

### 8.2 外部项目落点

| 外部项目 | waibao 落点 | 禁止事项 |
|---|---|---|
| Refine | `platform/resources`、`data/providers` | 业务组件直接依赖全套 API |
| shadcn-admin | `components/layout`、`components/patterns/table` | 搬入 Vite/router 配置 |
| Open WebUI | `features/conversation` | 引入 Svelte 或复制整仓 |
| OpenResume | `features/profile`、`features/jd-marketing` | 绑定外部 schema |
| Cal.com | `features/rooms`、`features/plan` | 复制领域后端和 monorepo packages |
| Tremor | `components/patterns/analytics` | 与 Recharts 双轨散用 |

### 8.3 数据契约

统一 API error：

- `code`：机器可读；
- `message`：用户可读；
- `fieldErrors`：表单字段；
- `requestId`：排障；
- `retryable`：是否可重试；
- `serviceState`：服务关闭/灰度/配额；
- `requiredPermission`：权限提示。

统一 query 状态：

- idle；
- pending；
- refreshing；
- success；
- empty；
- error；
- offline；
- forbidden；
- service-disabled。

### 8.4 设计 token

必须先定义语义 token：

- surface/background/elevated；
- text/default/muted/inverse；
- border/default/strong/focus；
- status/info/success/warning/danger；
- chart/categorical/1..N；
- emotion/positive/neutral/negative；
- matching/high/medium/low；
- spacing、radius、shadow、motion；
- compact/comfortable density。

不得在业务页面直接散布品牌色和图表色。

---

## 9. 实施顺序

## Phase 0：冻结基线与治理（第 1 周）

1. 用 GitHub API 记录候选项目 stars、license、latest commit、release 快照。
2. 建立 `THIRD_PARTY_NOTICES` 与组件来源登记表。
3. 对 Open WebUI、Cal.com、Plane、Docmost 做许可证专项复核。
4. 盘点现有页面、重复组件、路由、权限与服务开关。
5. 定义 v9 前端成功指标：任务完成率、错误率、LCP、可访问性、NPS。

**退出条件**：每个拟复制组件都有来源、commit、license 和 owner。

## Phase 1：设计系统与企业壳层（第 2-3 周）

1. 建 token、typography、density、motion。
2. 从 shadcn-admin 适配 AppShell、Sidebar、Header、Command Palette。
3. 统一 PageHeader、Breadcrumb、ActionBar、EmptyState、ErrorState。
4. 打通 next-intl、主题、白标、租户切换和 ServiceToggle。
5. 在 Storybook 覆盖暗色、中文、窄屏和键盘。

**退出条件**：admin、employer、jobseeker 三类 shell 一致，Lighthouse accessibility 达标。

## Phase 2：企业数据与权限骨架（第 3-5 周）

1. 以 Refine 思想实现 Resource Registry 和 data adapter。
2. 接入 auth、RBAC、tenant、service access。
3. 建 ResourceTable、FilterBar、SavedView、BulkAction。
4. 先迁移 `hr/suggestions`、`compliance-review`、`matching/quality` 三页。
5. 验证 URL 状态、缓存、mutation、错误和审计 correlation id。

**退出条件**：三条垂直切片生产可用，adapter 边界稳定。

## Phase 3：求职者 Chat 主体验（第 5-7 周）

1. 按 Open WebUI 模式建立 conversation 状态机。
2. 完成 ChatBubble、Composer、Markdown、附件、反馈、主动卡片。
3. 接入现有 realtime、LiveKit、语音和服务开关。
4. 完成断线、重连、停止、重试、消息失败恢复。
5. 交付 1.1、1.3、2.6。

**退出条件**：流式对话、语音降级和主动消息可用，移动端完成测试。

## Phase 4：Profile、JD 与规划（第 7-9 周）

1. 按 OpenResume 建结构化编辑与实时预览。
2. Profile 支持来源解释、逐项确认、纠正和版本历史。
3. JD 支持模板、版本 diff、发布前检查。
4. 按 Cal.com 建计划日历、check-in、参与者和提醒。
5. 交付 1.5、1.6、2.5。

**退出条件**：中文简历分页、草稿恢复、模板切换与日历时区测试通过。

## Phase 5：协同房间与活动流（第 9-11 周）

1. 借鉴 Cal.com、Chatwoot、Plane 重做 rooms。
2. 建 ParticipantStack、Agenda、RoomTimeline、Unread、Mention。
3. 加入沉默激活、邀请状态、通知和共识 tab。
4. 交付 1.2、2.3、2.7、2.8、2.9 的协同部分。

**退出条件**：100 房间规模下交互性能、重连和通知去重达标。

## Phase 6：数据仪表盘（第 10-12 周，可与 Phase 5 并行）

1. 以 Tremor blocks 统一 MetricCard 和 dashboard grid。
2. 底层保留 Recharts，通过 adapter 实现。
3. 为每张图补口径、更新时间、文本摘要和数据表。
4. 交付 1.4、2.3、2.4、2.8、3。
5. 完成 drill-down、筛选 URL 化和导出。

**退出条件**：所有 dashboard 有无障碍替代、空数据解释和指标口径。

## Phase 7：收口与迁移（第 12-14 周）

1. 删除重复壳层和废弃组件。
2. 统一 `/admin`、`/mothership` 等信息架构，提供 redirect。
3. 完成视觉回归、E2E、性能预算、a11y 和 i18n 检查。
4. 灰度发布，收集真实任务完成率和反馈。
5. 更新 ADR、组件文档和第三方 NOTICE。

**退出条件**：16 项映射全部通过状态矩阵，旧入口可安全下线。

---

## 10. 首批实施 Backlog

### P0

- AppShell；
- Resource Registry；
- API Error Boundary；
- ServiceDisabledState；
- PermissionDeniedState；
- Command Palette；
- ResourceTable；
- Chat state machine；
- Message renderer；
- MetricCard；
- Storybook visual matrix。

### P1

- Profile editor；
- Template picker；
- Room timeline；
- Participant stack；
- Calendar/check-in；
- Consensus gauge；
- Bias impact chart；
- Saved views；
- Bulk actions；
- Audit event drawer。

### P2

- 可配置 dashboard；
- 离线草稿；
- 跨端同步；
- 高级快捷键；
- 用户自定义密度；
- dashboard 导出；
- 富文本协同编辑。

---

## 11. 验收指标

### 11.1 体验

- 核心任务完成率提升；
- 首次任务成功时间降低；
- 空状态可导向下一动作；
- mutation 失败可恢复；
- Chat 首 token 与停止响应可度量；
- 移动端关键任务不依赖 hover。

### 11.2 性能

- route-level bundle budget；
- LCP、INP、CLS 纳入 CI/监控；
- 图表和编辑器按路由动态加载；
- 大列表虚拟化或服务端分页；
- streaming 不触发整页高频重渲染；
- sidebar 与 shell 不重复加载业务数据。

### 11.3 可访问性

- 所有操作可键盘完成；
- Dialog/Drawer 正确管理焦点；
- 图表有文本摘要与数据表；
- 状态不只依赖颜色；
- streaming 更新使用合适 live region；
- prefers-reduced-motion 生效；
- 中文屏幕阅读器标签清晰。

### 11.4 工程质量

- TypeScript strict 无错误；
- ESLint 无阻断问题；
- Storybook build 成功；
- 核心 pattern 有 interaction test；
- 16 项页面有 E2E happy path 和 failure path；
- 第三方来源与许可证检查通过。

---

## 12. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 模板整仓迁移导致架构倒退 | 中 | 高 | 禁止 L5，逐组件 ADR |
| Refine 渗透业务层 | 中 | 高 | adapter + 垂直切片 |
| 双设计系统 | 高 | 高 | Ant Design 只 L1，shadcn 单一主系统 |
| Open WebUI 许可证误判 | 中 | 高 | 按文件和 commit 法务复核 |
| AGPL 代码复制 | 中 | 高 | Plane/Docmost/AppFlowy 仅 L1 |
| 图表依赖重复 | 中 | 中 | Recharts 优先，统一 adapter |
| stars 数据过时 | 高 | 低 | API 快照，不作质量门槛 |
| Next.js 版本差异 | 高 | 中 | 只迁移模式，针对 Next 16 重写 |
| 页面重做但状态缺失 | 中 | 高 | 状态矩阵作为 DoD |
| 中文/移动端后补 | 高 | 中 | Storybook 首日纳入 |
| 实时重连数据重复 | 中 | 高 | event id、幂等与去重 |
| 服务开关只隐藏 UI | 中 | 高 | 前后端共同校验 |

---

## 13. 许可证与供应链政策

### 13.1 允许路径

- MIT、Apache-2.0 等宽松许可证：可在保留声明和满足条款后 L2/L3。
- AGPL/GPL 类：默认只 L1；复制、修改、网络部署前必须法务审查。
- 自定义许可证或品牌条款：默认只 L1，审批后再升级。
- 无明确许可证：不得复制代码。

### 13.2 每个复制组件的记录

- 上游项目 URL；
- commit SHA；
- 原文件路径；
- SPDX license；
- 修改摘要；
- waibao owner；
- 升级/安全跟踪方式；
- 删除和替换方案。

### 13.3 供应链检查

- lockfile 必须提交；
- npm audit/OSV 扫描；
- Renovate/Dependabot 分组升级；
- 新依赖 bundle 影响报告；
- 安装脚本与 postinstall 审查；
- 禁止从不明 fork 安装 package。

---

## 14. 来源与核验入口

以下以一手仓库为最终依据；stars、许可证和技术栈在真正集成前应再次核验：

1. [Refine GitHub](https://github.com/refinedev/refine)
2. [Refine Documentation](https://refine.dev/docs/)
3. [shadcn-admin GitHub](https://github.com/satnaing/shadcn-admin)
4. [NextAdmin GitHub](https://github.com/surajondev/nextadmin)
5. [Taxonomy GitHub](https://github.com/shadcn-ui/taxonomy)
6. [Vercel Platforms GitHub](https://github.com/vercel/platforms)
7. [Tremor GitHub](https://github.com/tremorlabs/tremor)
8. [Ant Design Pro GitHub](https://github.com/ant-design/ant-design-pro)
9. [OpenResume GitHub](https://github.com/xitanggg/open-resume)
10. [Cal.com GitHub](https://github.com/calcom/cal.com)
11. [Plane GitHub](https://github.com/makeplane/plane)
12. [Docmost GitHub](https://github.com/docmost/docmost)
13. [Chatwoot GitHub](https://github.com/chatwoot/chatwoot)
14. [AppFlowy GitHub](https://github.com/AppFlowy-IO/AppFlowy)
15. [Open WebUI GitHub](https://github.com/open-webui/open-webui)
16. [LibreChat GitHub](https://github.com/danny-avila/LibreChat)
17. [Chatbot UI GitHub](https://github.com/mckaywatsen/chatbot-ui)
18. [shadcn/ui Documentation](https://ui.shadcn.com/)
19. [Next.js Documentation](https://nextjs.org/docs)
20. [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)

---

## 15. 最终决策记录

### 决策

- 主技术栈不变：Next.js 16 + React 19 + TypeScript + Tailwind + shadcn。
- 企业资源层：渐进采用 Refine 的 headless 模式。
- Admin 壳层：以 shadcn-admin 为首要视觉来源。
- Chat：以 Open WebUI 为交互标杆，在 React 中重建。
- Profile/JD：以 OpenResume 为交互标杆。
- Rooms/Plan：以 Cal.com 为交互标杆。
- Analytics：以 Tremor 为 dashboard 标杆，底层优先复用 Recharts。
- Ant Design Pro、Plane、Docmost、Chatwoot、AppFlowy 仅作为专项模式库。

### 理由

该组合最大化复用成熟开源经验，同时最小化框架迁移、双设计系统、许可证和供应商绑定风险。

### 不可妥协项

- 不整仓 fork；
- 不无来源复制；
- 不只做 happy path；
- 不把权限等同于隐藏按钮；
- 不把 dashboard 等同于堆图表；
- 不把 Chat 等同于左右气泡；
- 不把 stars 等同于架构质量；
- 不牺牲中文、移动端和可访问性。

### 复审时间

- Phase 2 垂直切片完成后复审 Refine 集成深度；
- Phase 3 完成后复审 Chat 组件边界；
- v9.0 GA 前重新冻结上游版本与许可证快照。

---

## v9.1 — Jobseeker 端选型补完

| 参考项目 | URL | 借鉴 |
|---|---|---|
| Refine | https://refine.dev | admin / Resource hooks / refine.tsx |
| shadcn-admin | https://github.com/satnaing/shadcn-admin | mothership layout |
| Tremor | https://tremor.so | KPI/AreaChart 图表 |
| **Open WebUI** | https://github.com/open-webui/open-webui | **jobseeker chat shell (会话 / 侧栏 / Streaming)** |
| **OpenResume** | https://github.com/xitanggg/open-resume | **jobseeker résumé blocks / 可拖拽 / 打印** |
| **Cal.com** | https://github.com/calcom/cal.com | **面试 booking / 时间槽 / 时区** |

### Jobseeker 关键页面映射

| 我们的页面 | Open Source 参考 | 借用的设计模式 |
|---|---|---|
| `/jobseeker` (Dashboard) | Open WebUI + shadcn | 侧栏+主区+ProactiveBanner |
| `/jobseeker/chat` | Open WebUI | 会话流 + Streaming + Input 工具栏 |
| `/jobseeker/profile` | OpenResume | 块化简历 + 打印样式 |
| `/jobseeker/interview` | Cal.com | 时间槽选择 + tz-aware |
| `/jobseeker/offers/compare` | shadcn admin | 表格 + 评分卡 |
| `/jobseeker/journal` | Open WebUI + Tremor | 时间轴 + 评分趋势 |

### 为什么不用某个库作为黑盒

我们刻意 **吸收设计模式** 而 **不直接 npm install**:

- Refine 太重——我们只需 Resource hooks,自己写了 1/10。
- shadcn/ui 是 CLI copy-paste,符合"我们持有代码"原则。
- Tremor 图表改造为 `components/charts/*`(避开其定制 Tailwind preset 冲突)。
- Open WebUI 的 chat 流是 Svelte,直接翻译到 React (`<ChatBubble/>` + SSE)。
- OpenResume 的 PDF 输出改为 `@react-pdf/renderer`(纯 Node)。
- Cal.com 完整部署太重,只取 `<TimeSlotPicker/>` 思想。

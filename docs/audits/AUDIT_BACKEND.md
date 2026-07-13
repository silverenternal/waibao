# waibao v10.0 后端企业化代码审查

> 审查基线：`/home/hugo/codes/waibao/talent-tool-mvp/backend`。静态审查覆盖 804 个 Python 文件，其中生产代码 594 个、约 121,559 LOC，测试代码 210 个、约 50,436 LOC。仓库宣称 3,660+ tests；本次未重新执行全量测试，因此“测试覆盖”是基于代码/测试规模、模块测试分布和已发布测试结果的工程估值，不等同于 coverage.py 行覆盖率。

## 总体评分
- 后端整体: **6.1/10**
- 测试覆盖: **约 76%（估值；缺少本次 coverage.py 报告）**
- 错误处理: **6.0/10**
- 性能: **6.4/10**
- 安全: **5.8/10**

总体判断：功能面已经远超 MVP，具备 Provider 抽象、熔断重试、EventBus、ConfigCenter、FeatureFlag、ServiceToggle、Workflow、Sentry/OTel/Prometheus 等企业化“组件”；但大量组件仍以进程内状态、宽泛异常吞噬、静默降级和弱契约方式拼装。企业化短板不在“有没有功能”，而在**强制治理、故障语义、持久化一致性、租户边界、可审计性及真实生产验证**。

关键量化证据：
- API：113 个带路由文件、约 640 个路由；仅 96 处 `response_model=`，88 个路由文件完全没有响应模型。
- 多租户：API 源码仅 178 次 `tenant_id` 显式引用，很多路由依赖全局 middleware 隐式绑定；路由级隔离不可见且难审计。
- 服务开关：`main.py` 通过 `install_auto_gates(app)` 自动挂载，优于逐路由手工依赖；但静态 API 文件仅 1 处直接 `check_service_access`，治理正确性高度依赖 monkey-patch/注册顺序。
- 生产代码含约 874 个 `except Exception`、130 个缩进级 `pass`，故障被静默降级的密度过高。
- 约 121.6K 生产 LOC 对 50.4K 测试 LOC；测试基础较好，但 provider 的真实集成测试常依赖密钥，且 sourcing/vision 等维度无目录内单测。

## 高优先级问题 (P0 - 立即修)

1. **问题：Anthropic Provider 使用过时模型与不兼容请求参数**
   - 位置: `backend/providers/llm/anthropic_provider.py:34-45,107-126,165-183,215-237`
   - 影响: 默认 `claude-3-5-sonnet-latest` 已不符合当前官方模型实践；对新 Opus 4.7/4.8 继续发送 `temperature` 会直接 400。异常映射依赖类名和错误字符串，可能把 403/404/413/529 误映射成上游不可用并错误重试。定价表也会导致成本核算失真。
   - 修复成本: 中（3-5 人日，含兼容测试）
   - 建议: 使用官方 SDK typed exceptions；模型目录由 ConfigCenter/Models API 管理；对 Claude 4.8 使用 `thinking={"type":"adaptive"}`，移除 sampling 参数；结构化输出改用 `output_config.format`/SDK parse；大输出使用 streaming；增加 400/401/403/404/413/429/500/529、refusal、max_tokens、context overflow 契约测试。

2. **问题：PluginSDK 的“沙箱”仍是同进程 monkey-patch，默认网络 guard 可失效**
   - 位置: `backend/plugins/sdk/sandbox.py:24-26,129-181,188-243,250-298`
   - 影响: 文档明确沙箱 opt-in；RestrictedPython 缺失时退化为 AST 审计后普通 `compile`，无法形成可信安全边界。`NetworkGuard` 在 allow-list 为空时直接返回，相当于默认放行；全局替换 `socket.socket`/进程级 rlimit 还会影响宿主并产生并发竞态。恶意插件可造成数据泄露、宿主 DoS 或跨租户访问。
   - 修复成本: 高（2-4 周）
   - 建议: 生产强制独立进程/容器或微 VM，默认拒绝 egress、只读根文件系统、非 root、seccomp/AppArmor、CPU/内存/时间/文件系统配额；manifest 权限由宿主 RPC capability 执行，不允许插件直接访问进程对象；安装前签名/SBOM/依赖扫描。

3. **问题：FeatureFlag/Config/ServiceToggle 在基础设施故障时静默回退进程内状态**
   - 位置: `backend/services/platform/feature_flag.py:102-179,186-221`，`service_toggle.py:54-119`，`config_service.py:131-155`
   - 影响: 多 worker/多区域会出现决策漂移；重启丢状态；安全开关、付费权限、灰度发布可能在 Redis/Supabase 故障时表现不同。`feature_flag.invalidate()` 无 prefix 时使用 Redis `flushdb`，可能误删共享库数据。
   - 修复成本: 中高（1-2 周）
   - 建议: 将“配置不可用”区分 fail-open/fail-closed；安全、计费、租户隔离开关必须 fail-closed；Redis keyspace 独占且禁止 `flushdb`；引入版本号/CAS、变更确认、跨节点收敛指标和故障演练。

4. **问题：WorkflowEngine 宣称并行/可恢复，但核心实现并不满足**
   - 位置: `backend/services/platform/workflow_engine.py:1-10,119-145,184-197,251-287`
   - 影响: 注释声称并行，实际 fan-out 顺序执行；默认 InMemory store；resume 依赖 `_last_workflow`，重启后无法恢复，且 `execute()` 会重建结果，存在覆盖历史状态的风险；无节点 timeout、重试策略、幂等键、补偿事务、循环/重复节点防护。
   - 修复成本: 高（3-5 周）
   - 建议: 统一保留一个生产引擎；持久化 definition/version/current frontier；节点级幂等、lease、heartbeat、timeout/retry/dead-letter、补偿；真正 `asyncio.TaskGroup` 并行并限制并发；增加 crash/restart/duplicate delivery 测试。

5. **问题：输入、输出与 Prompt Injection 防护没有成为 AgentRuntime 强制契约**
   - 位置: `backend/agents/runtime.py:114-143,165-173`；16 个业务 Agent；例如 `profile_agent.py:21-42,280-304`
   - 影响: `AgentInput` 是 dataclass，无长度、字符集、PII、URL、context schema 限制；绝大多数 Agent 直接拼 prompt、`json.loads` 后使用 dict，没有 Pydantic/JSON Schema 校验。用户文本、OCR、视频转录和 RAG 内容可注入指令；超大输入可放大成本/延迟；错误 JSON 可能进入业务状态。
   - 修复成本: 中高（2-3 周）
   - 建议: Runtime 强制 `AgentInputModel`/`AgentOutputModel`；输入字节/token 限制、PII 分类与用途同意、外部内容隔离标记、不可覆盖系统政策；输出采用 provider 原生 structured output + Pydantic 二次验证，失败仅做有限 repair/retry，之后走确定性 fallback。

6. **问题：多租户与权限治理依赖全局隐式 middleware，路由级证据不足**
   - 位置: `backend/setup.py:104-155`，`backend/services/platform/middleware.py:72-132`，`backend/main.py:29-33`，大量 `backend/api/*.py`
   - 影响: 自动 gate 必须在 include_router 前安装；新注册方式、mount、WebSocket、后台任务或直接 service 调用可能绕过。640 路由中租户 ID 只在部分模块显式出现；admin_config/admin_feature_flags/admin_plugins 等路由静态扫描显示 Depends 很少或为零，需依赖外围魔法保证授权。
   - 修复成本: 中（1-2 周）
   - 建议: 把 auth/tenant/service entitlement 变成 APIRouter 级显式 dependencies；CI AST 规则检查每个非公开路由；repository 方法强制 tenant 参数/RLS；WebSocket、SSE、任务队列单独建立租户传播和测试矩阵。

## 中优先级问题 (P1 - 1 个月内)

1. **问题：Prompt 仍大面积硬编码，ConfigCenter 热更新未实际覆盖 Agent**
   - 位置: `backend/agents/**` 中 `PROFILE_INTAKE_PROMPT`、`COMPLIANCE_PROMPT`、`HR_SERVICE_PROMPT` 等；仅个别 Agent 尝试读取配置。
   - 影响: 无法版本化回滚、灰度、按租户/地区/语言调整；prompt 改动必须发版；审计无法关联 prompt 版本。
   - 修复成本: 中。
   - 建议: 统一 PromptRegistry，key=`agent.<name>.<locale>`，强制记录 version/hash；本地常量只作受控 fallback；ConfigWatcher 加收敛 SLA 和失败告警。

2. **问题：Agent fallback 多为“捕获所有异常后返回默认 dict”，可用性与正确性混淆**
   - 位置: 全部 16 Agent，典型为 `profile_agent.py:71-95,135-137` 和多处 `except Exception`。
   - 影响: 网络错误、鉴权、内容违规、JSON 格式错、业务校验错被同等处理；上游以 success 继续持久化，难以区分“真实推理结果”和“兜底”。
   - 修复成本: 中。
   - 建议: 建立错误分类、`degraded/retryable/source/confidence` 输出字段；确定性 fallback 不应写入长期记忆；鉴权/配置错误立即告警，不重试。

3. **问题：API 响应契约和 OpenAPI 完整度低**
   - 位置: `backend/api/`；约 640 路由仅 96 个 response_model，88 个路由文件完全缺响应模型。
   - 影响: 客户端生成、兼容性检测、数据脱敏与字段治理薄弱；任意 dict 可能泄露内部字段。
   - 修复成本: 中高。
   - 建议: 每路由 request/response Pydantic v2 模型、统一错误 envelope、examples、operation_id、分页模型；CI OpenAPI diff 阻止破坏性变更。

4. **问题：限流虽有 tenant quota/slowapi，但覆盖与策略分散**
   - 位置: `backend/setup.py:124-155`、各 API 文件中的局部 limiter。
   - 影响: 路由级成本差异未映射到配额；WebSocket/SSE/批处理/LLM token 消耗不能仅按 request 计；有些文件未见 limiter。
   - 修复成本: 中。
   - 建议: 统一按 tenant+actor+route+token/计算量计费；Redis 原子限流；响应标准 RateLimit headers；后台任务和实时连接单独限额。

5. **问题：Service 层规模和职责失控**
   - 位置: 见下表；特别是 `integrations/collaboration_room.py` 1115 行、`platform/predictive.py` 846 行、`platform/service_toggle.py` 792 行、`billing/billing.py` 681 行。
   - 影响: 测试隔离、并发推理和故障定位困难；重复的根目录兼容模块与领域子包增加双实现漂移。
   - 修复成本: 高。
   - 建议: 按 application/domain/infrastructure 拆分；400 LOC 设软门槛；删除兼容转发层前建立 import graph；统一 UnitOfWork 和 repository。

6. **问题：Provider 弹性能力不均衡，mock fallback 可能掩盖生产故障**
   - 位置: `backend/providers/*`；embedding/llm/lookup/ocr/sourcing/stt/vision 缺明确 retry，payment 未见统一 timeout；大量 broad except。
   - 影响: 不同维度在 429、超时、凭据失效时行为不同；自动切 mock 可能向用户返回伪造结果。
   - 修复成本: 中。
   - 建议: Provider contract 强制 timeout/retry-after/idempotency/error taxonomy；mock 只在 test/dev 显式启用，生产不得静默 fallback；真实测试以 nightly/sandbox 运行。

7. **问题：EventBus 缺少企业级交付语义**
   - 位置: `backend/eventbus/base.py:22-58,116-176,183-247`
   - 影响: Event payload 无 schema/version/tenant_id；Redis pub/sub 无持久化、ack、重放、consumer group、DLQ；handler 错误仅存在进程内 list；`publish_async` 的 Redis 实现只调用本地 handler，没有向 Redis publish。
   - 修复成本: 高。
   - 建议: 事件契约注册表（名称+版本+Pydantic schema）、tenant/correlation/causation；采用 Redis Streams/Kafka/NATS JetStream；outbox/inbox、幂等消费、DLQ、重放与 lag 指标。

8. **问题：可观测性是 best-effort，生产缺失会静默继续**
   - 位置: `backend/setup.py:63-96`、`services/observability/telemetry.py:33-56,82-92,95-145`
   - 影响: OTel/Sentry/Prometheus 初始化或 instrumentation 失败只 warning/debug；部署可能在“无追踪、无告警”状态运行。OTLP exporter 固定 `insecure=True`，生产传输配置不足。
   - 修复成本: 低中。
   - 建议: production profile 下关键 observability 初始化失败阻止启动；TLS/headers/resource attributes；tenant 哈希、route、provider、model、prompt_version、degraded 状态打点，严格禁止 PII 进 span/log。

9. **问题：日志仍是标准 logging + 自由文本，结构化不统一**
   - 位置: 全 backend；`main.py:8-10` 使用 basicConfig，Agent 使用 f-string 日志。
   - 影响: request/trace/tenant/user/provider 字段不可稳定检索；异常字符串可能泄露简历、API 响应或 PII。
   - 修复成本: 中。
   - 建议: structlog/json formatter；contextvars 自动绑定 trace/request/tenant；统一 redaction processor；禁止记录 prompt/raw response/secrets。

10. **问题：成本/熔断/令牌桶多为进程内单例且并发安全不足**
    - 位置: `backend/providers/base.py:97-128,133-157,163-245,284-300`
    - 影响: 多 worker 各自预算、限流、熔断；`TokenBucket`、`CostTracker`、半开熔断无锁，协程并发下可超发；记录成本后才发现越限，已产生费用。
    - 修复成本: 中。
    - 建议: Redis/Lua 原子预算预留与结算；分布式 circuit breaker 或实例级明确语义；half-open 单探针锁；按估算 token 预授权，完成后 reconcile。

## 低优先级问题 (P2 - 重构期)

1. `backend/main.py` 504 行且手工 include 100+ router，版本仍写 `0.1.0`，建议模块化 router registry 与构建时版本注入。
2. `AgentOutput.reasoning_chain` 暗示向用户暴露推理链；应改为审计友好的决策摘要/证据，避免存储或展示隐藏推理。
3. Agent Runtime 构造函数静默吞下任意 kwargs（`runtime.py:165-173`），会掩盖拼写错误；改显式依赖和 fail-fast。
4. 多处同步 Redis/Supabase SDK 被 async API 调用，需基准测试并迁移 async client/线程池。
5. FeatureFlag 目前能做百分比 rollout 和 user/org override，但缺实验互斥、曝光日志、样本比失衡检测、统计口径和胜出自动化，不应等同完整 A/B 平台。
6. ConfigCenter 的 watcher 基于本地 callback/Redis 线程，需要配置 schema 校验、双人审批、secret 类型与敏感值脱敏。
7. Provider API key 主要来自 env，企业部署应增加 Secret Manager/Vault/KMS、轮换、key ID、泄漏检测；对象不应长期保留明文 key 属性。
8. 兼容模块与领域模块并存（如根 services 与 `services/jobseeker|employer|platform`），增加导入歧义和测试重复。
9. 大量 dataclass/dict 作为跨层协议，建议 contracts 包成为单一 Pydantic source of truth。
10. 真实 API 测试应隔离为 integration/nightly marker，并增加 VCR/contract sandbox，避免“有测试文件但 CI 永远 skip”。

## Agent 成熟度表

评分说明：1=原型，2=MVP，3=可用但治理不足，4=企业可运营，5=强契约/可审计/多区域成熟。当前 16 个业务 Agent（15 个 `*_agent.py` 加 1 个 evaluator）均有 BaseAgent、日志、一定 fallback 和 EventBus 接入，但普遍缺输入/输出 schema、注入防护和 i18n。

| Agent | 评分 | 关键问题 | 改进建议 |
|---|---:|---|---|
| profile_agent | 3/5 | 385 行；prompt 硬编码；OCR/视频/LLM 异常均 broad catch；处理姓名/电话/邮箱但无 PII consent/tenant schema；JSON 仅 loads | PromptRegistry；简历 URL allow-list/大小限制；PII purpose consent；结构化输出和 profile schema；fallback 标记 degraded |
| intake_agent | 2.5/5 | 硬编码中文 prompt；直接 JSON 解析；无输入长度、语言和注入策略 | Pydantic 输入输出、locale prompt、确定性 intake fallback、token cap |
| clarifier_agent | 3/5 | 有反思二次调用但成本/延迟高；7 个 try；动态 prompt；输出 repair 无强 schema | 把 draft/reflection 合并为可配置策略；schema parse；预算感知；低置信度请求人工确认 |
| career_planner_agent | 3/5 | 338 行；规划 JSON 宽松；长期建议可能基于不完整画像；仅局部 i18n 痕迹 | 计划模型/证据字段；版本化 prompt；事实与建议分离；计划持久化幂等 |
| daily_journal_agent | 3/5 | 部分从配置取 system prompt，但失败回硬编码；敏感情绪文本可能进入日志/记忆 | 全量 ConfigCenter；情绪/健康安全策略；PII redaction；prompt version metric |
| emotion_agent | 2.5/5 | 健康/情绪高风险场景，却以 broad fallback 为主；无危机分级契约 | 安全分类器、危机升级规则、人工接管、区域化热线/i18n、禁止无依据诊断 |
| compliance_agent | 3/5 | 决策影响高；LLM JSON 失败时 fallback；规则/模型结论边界不清 | 规则引擎为主、LLM 只解释；引用政策版本；人工复核门槛；不可自动批准高风险结果 |
| employer_clarifier_agent | 2.5/5 | prompt 硬编码；输出 schema 弱；缺 injection/超长文本防护 | 结构化需求模型、字段级校验、locale、低置信度追问 |
| hr_service_agent | 3/5 | 368 行、多个业务域耦合；LLM 输出可触发 HR 动作；无明确 tool approval | 拆 intent/plan/action；副作用工具 human-in-loop；审计 action proposal 与批准人 |
| job_spec_agent | 2.5/5 | 硬编码 prompt；职位描述可携带歧视性/注入文本；JSON fallback | 偏见与合规前置校验；结构化 JD schema；证据/政策标记；多语言模板 |
| multi_party_agent | 2.5/5 | 81 行偏薄；共识输出依赖一次 LLM JSON；无参与者权限/顺序/冲突协议 | 明确 participant ACL、消息来源签名、共识算法与人工决策记录 |
| persona_agent | 3/5 | 个性化强但语气配置和安全边界未契约化；fallback 不透明 | 租户/用户授权的 persona profile；禁止推断敏感属性；A/B exposure 与回滚 |
| policy_agent | 3/5 | 制度解释可能被当法律结论；硬编码 prompt；引用/版本不足 | RAG 强制 citation；政策版本/生效日期；免责声明与升级 HR/legal；structured answer |
| talent_brief_agent | 2.5/5 | 一次 JSON 提取；prompt 硬编码；无来源追踪与输出 schema | Brief Pydantic schema；字段 provenance；缺失值而非编造；可配置 prompt |
| vision_agent | 2.5/5 | 战略文本可能极大且敏感；硬编码 prompt；无版本/证据/访问控制 | 文档分块和 token 预算；租户文档 ACL；引用原文；人审后发布 |
| mutual_evaluator | 2.5/5 | 评价关系重大；JSON loads + broad fallback；可能放大偏见 | 双盲/去敏、rubric schema、校准与偏差指标、人工复核、解释证据 |

### Agent 横向结论
- Prompt ConfigCenter 覆盖：**低**。几乎所有 Agent 都定义模块级长字符串，仅少量运行时尝试配置读取。
- 错误处理：**中**。网络/provider 底层有重试熔断，但 Agent 端常把 JSON、业务、网络错误统一 broad catch。
- 降级：**中**。多数有 fallback，但缺 degraded provenance，容易把兜底当真实结果。
- 输入校验/安全：**低**。无统一 Pydantic、token/byte cap、外部内容隔离和 prompt injection policy。
- 输出校验：**低至中**。主要依赖 `json.loads`，没有 provider structured output + schema validation。
- 性能：**中**。有成本字段/缓存/Provider metrics，但部分 Agent 多次 LLM 调用，缺 Agent SLO、并发/超时预算。
- 可观测性/可测试性：**中上**。BaseAgent 可注入 llm/memory/tracer，且有 EventBus/日志；但任意 kwargs 与全局单例降低 mock 精度。
- i18n：**低**。核心 prompt 和 fallback 基本为中文；仅 profile/career planner 有少量 language 痕迹。

## Service 子目录成熟度评估

| Service 组 | 规模 | 评分 | 主要问题 |
|---|---:|---:|---|
| 根目录兼容/门面 | 69 文件 / 2,410 LOC | 3/5 | 文件短但大量是转发/兼容层，领域边界不清；日志和缓存使用少 |
| auth | 4 / 1,508，1 个 >400 | 3.5/5 | SSO 565 行；安全敏感逻辑集中；需威胁模型、session revoke、并发登录测试 |
| billing | 1 / 682，1 个 >400 | 3/5 | 单体文件；支付/订阅/用量职责混合；缺明确事务/outbox 与 money 类型 |
| employer | 16 / 4,696，5 个 >400 | 3/5 | 30 个 broad catch；ATS/compliance/ticket 边界耦合；同步外部调用风险 |
| integrations | 17 / 6,239，4 个 >400 | 2.8/5 | collaboration_room 1115 行；49 个 broad catch；多外部系统的一致性/幂等不足 |
| jobseeker | 19 / 7,581，10 个 >400 | 2.8/5 | 一半文件超 400 行；46 broad catch；PII/视频/简历/面试数据治理压力最大 |
| marketplace | 5 / 1,762，2 个 >400 | 3/5 | catalog/service 偏大；安装、计费、评价事务边界与权限需强化 |
| matching | 5 / 1,883，3 个 >400 | 3/5 | comparison/feedback_loop 偏大；模型版本、可解释性、离线校准治理不足 |
| memory | 6 / 1,329，store 679 | 3/5 | 记忆存储单体、19 broad catch；删除/保留/tenant namespace 与并发写需增强 |
| multiagent | 4 / 1,293，1 个 >400 | 3/5 | orchestrator 519 行；缺持久任务 lease、累计 token budget、恢复与去重 |
| notify | 2 / 846，dispatcher 593 | 3/5 | channel fan-out 集中；重试/DLQ/用户偏好与去重需统一 |
| observability | 10 / 2,521，alerting 723 | 3.5/5 | 能力齐，但 48 broad catch，best-effort 过度；自身故障无 meta-monitoring |
| platform | 50 / 18,951，20 个 >400 | 2.8/5 | 159 broad catch；核心横切能力过度集中且多进程一致性不足，是主要技术债区 |
| rag | 9 / 1,857，均 <400 | 3.2/5 | 分层较好；logger 极少；文档 ACL、citation correctness、embedding version 需治理 |
| rule_engine | 5 / 1,347，1 个 >400 | 3/5 | DSL/evaluator 有分层；20 broad catch；表达式沙箱、资源上限和确定性测试不足 |
| support | 3 / 569，均 <400 | 3.5/5 | 结构清晰；需 webhook 签名、幂等、第三方 outage 策略 |
| training | 7 / 1,138，均 <400 | 3.3/5 | 文件小、并发锁迹象；模型/数据 lineage、审批和回滚需增强 |
| warehouse | 4 / 643，均 <400 | 3.4/5 | 分层简洁；ETL exactly-once、schema evolution、数据质量 SLA 需补 |
| webhook | 4 / 628，均 <400 | 3.5/5 | signer/dispatcher 分层合理；需 replay window、DLQ、secret rotation、tenant egress policy |

## API 路由成熟度

| 维度 | 评分 | 审查结论 |
|---|---:|---|
| 输入校验 | 3/5 | 多数写接口有局部 BaseModel，但 query/path 约束、max length、URL/文件限制并不统一 |
| 权限检查 | 3/5 | 大量路由有 Depends；但若干 admin/agent 路由依靠外围自动 wiring，静态不可证明 |
| 错误响应 | 2.5/5 | 广泛直接抛 HTTPException，缺统一 error code/request_id/details/retryable envelope |
| 限流 | 3/5 | 有 tenant quota 和 slowapi，但覆盖不一致，LLM token/WebSocket/批处理成本未统一 |
| 多租户隔离 | 3/5 | middleware + tenant context + 部分显式 tenant_id；需 repository/RLS 强制与 bypass 测试 |
| OpenAPI | 2.5/5 | response_model 严重不足，主版本仍 0.1.0；operation_id/examples/error schema 不统一 |
| 响应模型 | 2/5 | 640 路由仅约 96 处 response_model，任意 dict 返回仍是主流 |

建议优先治理的路由簇：`admin_config.py`、`admin_feature_flags.py`、`admin_plugins.py`、`workflows.py`、`bias_enforce.py`、`consensus_v2.py`、`daily_suggestions.py`、`jd_marketing.py`、`tone.py`、`v8_1.py`。它们存在零/少 Depends、零 response_model 或高副作用等组合风险；应人工复核外围 dependencies 是否实际生效。

## Provider 适配器成熟度

| 维度 | 评分 | 结论 |
|---|---:|---|
| assessment | 3.5/5 | 有 mock/timeout/retry/429/真实测试；仍有 broad catch |
| ATS | 3.5/5 | Greenhouse/Lever/OAuth 较完整；凭据来源不一致、8 broad catch |
| background_check | 3.5/5 | mock 与真实测试齐；高敏数据需 retention/consent 审计 |
| company_review | 2.8/5 | 实现多但 mock.py 1042 行、13 broad catch；第三方 ToS/抓取合规风险 |
| embedding | 3/5 | 多 provider/mock/真实测试；缺统一 retry，向量模型版本迁移策略不足 |
| job_market | 2.8/5 | 14 文件、多数据源；15 broad catch、rate-limit 信号不统一 |
| LLM | 2.8/5 | provider 丰富、统一 resilience；28 broad catch、Anthropic 过时、无统一 structured output/fallback policy |
| lookup | 3/5 | mock/timeout/key 支持；缺统一 retry，企业查询数据需用途和缓存期限 |
| notify | 3.5/5 | 渠道较全，重试/测试较好；需 DLQ 和幂等 message ID |
| OCR | 3/5 | 多云厂商和 mock；缺统一 retry，文件大小/恶意文档/PII 清理需增强 |
| payment | 3.5/5 | 错误较少、重试和测试存在；未见统一 timeout，需幂等键/账本事务 |
| sourcing | 2.8/5 | 有 mock 和超时；无目录测试、缺 retry；GitHub token/候选人隐私风险 |
| STT | 3/5 | mock/真实测试/超时；缺 retry，音频 retention 与 consent 需治理 |
| video_interview | 3.2/5 | provider/测试/重试较齐；13 broad catch，录制同意/区域驻留是重点 |
| vision | 2.5/5 | 仅 5 文件、无目录测试、缺 retry；图像 PII、安全与输出 schema 薄弱 |

统一 Provider 建议：禁止生产自动 mock；使用 Secret Manager；请求 hard timeout + retry-after；typed error taxonomy；幂等键；provider/model/version/region 指标；contract test + sandbox nightly；数据驻留与删除 hook。

## 扩展性基础设施评估

| 组件 | 评分 | 结论 |
|---|---:|---|
| EventBus | 2.8/5 | 有 sync/async、Redis、本地隔离和大量测试；没有可靠交付、schema/version/tenant/DLQ/replay，Redis async publish 语义有缺口 |
| PluginSDK | 2.5/5 | manifest/loader/registry/runner/sandbox 齐；同进程沙箱不能作为信任边界，且 production 隔离仅文档建议 |
| WorkflowEngine | 2.5/5 | DAG、pause/resume/store/templates/API 齐；并行声明与实现不符，恢复/幂等/补偿/timeout 不成熟 |
| ServiceToggle | 3.2/5 | 约 792 行且有 1000+ 行测试；自动 gate 覆盖面广，但依赖启动顺序、进程内 fallback 和大量 broad catch |
| ConfigCenter | 3.3/5 | 有版本/history/rollback/EventBus/watcher；绝大多数 Agent prompt 未接入，跨节点热更新收敛缺可测 SLA |
| FeatureFlag | 3.2/5 | 百分比 rollout、user/org override、audit 基础齐；内存源为主，remote wrapper 未形成完整读写路径；A/B 统计能力不足 |

### Event 类型覆盖
Event 名称分布广，Agent、config、feature flag、workflow 等均 emit；但事件只是自由字符串和任意 dict，不能把“出现 30+ 名称”视为“覆盖成熟”。应建立事件 catalog，标注 producer/consumer/schema/version/PII/retention/SLO，并在 CI 检查 orphan producer/consumer。

## 错误处理与可观测性

| 项目 | 评分 | 结论 |
|---|---:|---|
| 全局错误处理 | 3/5 | setup 集中初始化，但业务仍大量 HTTPException/broad catch；需统一错误码、request ID 和映射 |
| Sentry | 3.5/5 | FastAPI/Starlette/logging integration 和主动 capture 均存在；无 DSN 或初始化失败时静默关闭，覆盖率不可证明 |
| OTel | 3.5/5 | FastAPI/SQLAlchemy/AsyncPG/Redis/HTTPX instrument；Provider 有 llm_call span；Agent/tool/event/workflow 业务 span 不完整 |
| Prometheus | 3.5/5 | `/metrics`、provider/cache/collab 等指标存在；缺统一 SLO、队列 lag、degraded、prompt/version、tenant-safe 标签 |
| 结构化日志 | 2/5 | 主要为 stdlib logging/free text/f-string，未见统一 JSON schema/context binding/redaction |

可观测性必须补齐四条黄金路径：
1. API request → tenant/auth/gate → service → provider/DB；
2. Agent run → prompt version → LLM attempt/repair/fallback → memory write；
3. Event publish → durable queue → consumer attempt/DLQ；
4. Workflow run → node/attempt/lease/compensation。

## 重点改造清单 (10 项)
- [ ] 1. 建立 Agent Gateway：统一 Pydantic 输入输出、token/byte cap、PII/prompt-injection policy、structured output、degraded/error taxonomy。
- [ ] 2. 将 16 Agent prompt 全迁入 ConfigCenter/PromptRegistry，记录版本/hash/locale/tenant，支持灰度、回滚和 eval gate。
- [ ] 3. 重写 Anthropic Provider：当前模型目录、官方 typed exceptions、adaptive thinking、structured outputs、streaming、stop reason 和准确定价。
- [ ] 4. 把 Plugin 执行强制迁入容器/微 VM，默认拒绝网络和文件系统，能力通过宿主 RPC 授权。
- [ ] 5. 将 EventBus 升级为 durable stream，落地 schema registry、transactional outbox、幂等 inbox、DLQ/replay/lag metrics。
- [ ] 6. 将 WorkflowEngine 合并为单一生产实现，增加持久 frontier、并行调度、lease/heartbeat、节点 timeout/retry/idempotency/compensation。
- [ ] 7. API 契约治理：所有路由显式 auth+tenant+entitlement dependency、request/response model、统一错误 envelope、OpenAPI diff gate。
- [ ] 8. 分解 >400 行 Service，优先 platform/integrations/jobseeker/billing；清理根目录兼容双实现，建立 UnitOfWork/repository 边界。
- [ ] 9. 横切状态分布式化：预算、限流、熔断、FeatureFlag、ServiceToggle、Config cache 使用 Redis 原子操作和明确 fail-open/closed 策略。
- [ ] 10. 可观测性生产门禁：结构化 JSON/redaction、关键组件启动失败 fail-fast、端到端 trace、Agent/provider/workflow/event SLO 与故障演练。

## 建议验收指标
- 100% 非公开 API 路由通过 CI 证明 auth + tenant + entitlement；100% 有 response_model 和标准错误模型。
- 16/16 Agent 无模块级业务 prompt（仅允许受版本控制的 emergency fallback），100% structured output，100% 输入 token/PII policy。
- 生产环境 0 次 silent mock fallback；Provider 429/5xx/timeout 合同测试覆盖全部真实实现。
- EventBus 具备 at-least-once + 幂等，DLQ/replay 演练通过；跨 worker 配置变更 p99 收敛 <5 秒。
- Workflow crash/restart、重复投递、节点 timeout、补偿测试全部通过。
- `except Exception` 降低至少 60%，所有剩余宽泛捕获均有明确边界、metric 和错误语义。
- 所有生产日志 JSON 化且 PII 扫描为 0 泄露；关键 trace 覆盖率 >95%。
- coverage.py 在核心安全/计费/租户/Agent runtime/provider/workflow 模块分支覆盖率 >=90%，全仓行覆盖率 >=85%。

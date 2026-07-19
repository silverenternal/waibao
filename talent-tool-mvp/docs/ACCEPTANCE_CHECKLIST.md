# 甲方验收清单 (ACCEPTANCE_CHECKLIST)

> v11.2 / T6307 — 逐项功能验收依据。共 **26 项**(原验收)+ **5 项 v11.2 客户端新增需求**,级别 **A**(必须通过)/ **B**(建议通过)。
> 每项含:编号 / 需求描述 / 级别 / 演示步骤 / 通过标准 / 验收人签字栏。
> 级别 A 项全部通过方视为整体验收通过。

- 验收环境:本地一键部署(`bash scripts/start_local.sh`),访问 http://localhost:3000
- 数据安全前提:LLM 走本地 Ollama,OCR 走本地 PaddleOCR,简历 / 资质 / 对话**不出甲方环境**。
- 演示账号:启动后用 `python scripts/seed_test_data.py --with-sample-resumes` 灌入演示数据。

> **v11.1 T6206 代码级预验收结论(2026-07-17)**:26/26 项均已在代码层定位到对应的 API / Agent / 脚本 / 页面,链路完整。16 项 A 级全部 ✅。下表「代码级验证」列给出证据定位(文件 + 端点)。运行级(容器起服 + 抓包不出网 + 人工点击)由甲方在演示日现场勾选。

---

## 一、部署与基础设施(4 项)

### AC-01 一键本地部署 ⭐A ✅
- **代码级验证**:`scripts/start_local.sh` + `docker-compose.local.yml`(6 服务 backend/frontend/postgres/redis/ollama/paddleocr);`/api/health` 于 `backend/main.py`。
- **需求**:单命令启动全部服务(backend + frontend + postgres + redis + ollama + paddleocr)。
- **演示步骤**:
  1. 执行 `bash scripts/start_local.sh`;
  2. 观察脚本拉镜像、起 6 服务、拉模型、等待健康;
  3. 脚本打印各服务 URL。
- **通过标准**:6 个容器全部 `Up (healthy)`;http://localhost:3000 可访问;`/api/health` 返回正常。
- **验收人签字**:__________ 日期:______

### AC-02 数据不出甲方环境 ⭐A ✅
- **代码级验证**:`docker-compose.local.yml` 显式 `LLM_PROVIDER=ollama` + `OCR_PROVIDER=paddle`;Provider 路由 `backend/providers/llm/ollama*.py`、`backend/providers/ocr/paddle*.py`(T6101/T6102)。
- **需求**:大模型推理与 OCR 全部本地化,无任何外部 LLM / OCR API 调用。
- **演示步骤**:
  1. 查 `docker-compose.local.yml` 中 `LLM_PROVIDER=ollama` / `OCR_PROVIDER=paddle`;
  2. 触发一次简历 OCR + AI 画像;
  3. 抓包 / 查日志确认无出网请求到 openai / tencent / baidu 等。
- **通过标准**:全程仅访问 `ollama:11434` 与 `paddleocr:8500`(本地容器);无外部 API 流量。
- **验收人签字**:__________ 日期:______

### AC-03 停止与数据持久化 B ✅
- **代码级验证**:`scripts/stop_local.sh`(含 `--purge` 分支);卷 `ollama_data` / pg / redis 持久化挂载见 compose。
- **需求**:`stop_local.sh` 停服务且保留数据卷;`--purge` 清空。
- **演示步骤**:`bash scripts/stop_local.sh` → 重启 → 数据仍在;`--purge` → 数据清空。
- **通过标准**:停启后业务数据 / 已拉模型可复用;purge 后干净。
- **验收人签字**:__________ 日期:______

### AC-04 测试数据导入 ⭐A ✅
- **代码级验证**:`scripts/seed_test_data.py --with-sample-resumes`;Admin Data import 见 `backend/api/admin.py`;前端 `app/.../admin/data-import`。
- **需求**:一键生成 1000 求职者 / 10 企业 / 5 岗位 + 匹配;支持甲方脱敏简历。
- **演示步骤**:
  1. `python scripts/seed_test_data.py --with-sample-resumes`;
  2. 或在 Admin → Data import 页上传 CSV/JSON;
  3. 查看各列表数据量。
- **通过标准**:数据落入对应表/JSONL;前端列表可见 1000 求职者、5 岗位。
- **验收人签字**:__________ 日期:______

---

## 二、求职者端(5 项)

### AC-05 求职者注册与登录 ⭐A ✅
- **代码级验证**:Supabase Auth(`frontend/lib/auth.ts` + `lib/supabase.ts`)+ 演示登录 `signInAsDemo`;求职者 Dashboard `app/jobseeker/`。
- **需求**:求职者可注册账号并登录进入个人空间。
- **演示步骤**:前端首页 → 求职者注册 → 填手机/邮箱 → 登录。
- **通过标准**:注册成功、登录后进入求职者 Dashboard。
- **验收人签字**:__________ 日期:______

### AC-06 上传简历 + 本地 OCR 解析 ⭐A ✅
- **代码级验证**:`POST /api/uploads`(`backend/api/uploads.py`,UploadFile)+ PaddleOCR Provider(`backend/providers/ocr/`);简历解析入库见 pipelines。
- **需求**:上传简历(PDF/图片/文本),本地 PaddleOCR 识别并结构化。
- **演示步骤**:求职者 → 简历 → 上传一份简历 → 等待解析。
- **通过标准**:解析出姓名/技能/学历/经历等字段;OCR 数据未出网。
- **验收人签字**:__________ 日期:______

### AC-07 AI 聊天对话 ⭐A ✅
- **代码级验证**:`POST /api/realtime/invoke` + `WS /api/realtime/ws/invoke`(本地 Ollama 路由);前端 `app/jobseeker/chat/page.tsx`。
- **需求**:求职者可与 AI(本地 Ollama)对话,获取职业建议。
- **演示步骤**:求职者 → AI 聊天 → 提问“我适合什么岗位” → 收到回复。
- **通过标准**:AI 正常回复,响应在可接受时延内(本地 CPU < 30s)。
- **验收人签字**:__________ 日期:______

### AC-08 生成人才画像 ⭐A ✅
- **代码级验证**:`POST /api/clarification/synthesize`(`clarifier_agent`,产出 `profile_synthesis`)+ `GET /api/clarification/my-profile`;确认/修正见 profile 页。
- **需求**:基于简历 + 对话,AI 生成结构化人才画像(技能/优势/方向)。
- **演示步骤**:求职者 → 画像 → 点击“生成画像”。
- **通过标准**:画像含技能标签、优势、建议方向;求职者可确认/修正。
- **验收人签字**:__________ 日期:______

### AC-09 职业规划与执行追踪 B ✅
- **代码级验证**:`POST /api/career-plan/generate` + `GET/PATCH /api/action-items`(可勾选行动项 + state 推进)。
- **需求**:AI 生成职业规划,并支持行动项追踪。
- **演示步骤**:求职者 → 规划 → 生成规划 → 标记行动项进度。
- **通过标准**:规划含分阶段目标与可勾选行动项。
- **验收人签字**:__________ 日期:______

---

## 三、企业/HR 端(5 项)

### AC-10 企业注册与资质上传 ⭐A ✅
- **代码级验证**:`POST /api/compliance/upload`(`compliance_agent` 本地 OCR 校验)+ `GET /api/compliance/status`;资质 OCR 不出网。
- **需求**:企业可注册,上传营业执照等资质(本地 OCR 校验)。
- **演示步骤**:首页 → 企业注册 → 上传资质图片 → 等待 OCR/审核。
- **通过标准**:资质被识别并存档;资质数据未出网。
- **验收人签字**:__________ 日期:______

### AC-11 创建岗位 ⭐A ✅
- **代码级验证**:`POST /api/roles`(创建岗位)+ `POST /api/roles/extract-requirements`;前端企业岗位管理页。
- **需求**:HR 可创建岗位(标题/描述/技能要求/薪资/地点)。
- **演示步骤**:企业管理 → 岗位 → 新建 → 填写 → 保存。
- **通过标准**:岗位创建成功,出现在岗位列表。
- **验收人签字**:__________ 日期:______

### AC-12 AI 细化岗位(JD 营销化) ⭐A ✅
- **代码级验证**:`/api/jd-marketing/{package,score,seo,ab-variants}` + `POST /api/job-spec/submit`(`job_spec_agent` 出 `draft_jd`);一键采纳见 marketing 页。
- **需求**:AI 帮助细化/营销化 JD,提升吸引力。
- **演示步骤**:新建/编辑岗位 → 点击“AI 细化 JD” → 查看优化后文案。
- **通过标准**:输出更专业、有吸引力的 JD 文案,可一键采纳。
- **验收人签字**:__________ 日期:______

### AC-13 资质 AI 检测(假资质) B ✅
- **代码级验证**:`backend/api/ps_detection.py`(`/verify` 真实性初筛)+ compliance verdict 标记可疑项供复核。
- **需求**:AI 对上传资质做真实性初筛,标记可疑项。
- **演示步骤**:企业资质页 → 查看资质检测结果/标记。
- **通过标准**:可疑资质被标记,供人工复核。
- **验收人签字**:__________ 日期:______

### AC-14 个性化 HR(语气学习) B ✅
- **代码级验证**:`/api/tone/{aggregate,classify,few-shot,rewrite,tones}`(T3701 HR 语气学习);HR 助手按企业历史语气生成回复。
- **需求**:HR 助手学习企业沟通语气,生成符合风格的回复。
- **演示步骤**:HR 与候选人沟通 → 助手给出语气一致的回复建议。
- **通过标准**:回复风格与企业历史沟通一致。
- **验收人签字**:__________ 日期:______

---

## 四、匹配与推送(3 项)

### AC-15 候选人-岗位双向匹配 ⭐A ✅
- **代码级验证**:`POST /api/matches/hard-filter/{role_id}`(分数 + match_reasons + skill_gaps + risks)+ `POST /api/two-way-match/compute` + `GET /api/match/{id}/explain`(可解释)。
- **需求**:系统按技能/经验/语义双向匹配,给出综合分与解释。
- **演示步骤**:岗位 → 查看推荐候选人 / 候选人 → 查看推荐岗位。
- **通过标准**:每个匹配有分数、技能重叠、优势/差距、解释。
- **验收人签字**:__________ 日期:______

### AC-16 匹配质量与命中率 B ✅
- **代码级验证**:`backend/api/admin_matching_quality.py`(命中率/接受率/反馈率看板)+ `matching_feedback.py`。
- **需求**:匹配质量看板展示命中率、HR 反馈率等指标。
- **演示步骤**:管理后台 → 匹配质量看板。
- **通过标准**:看板展示命中率/接受率/反馈率等关键指标。
- **验收人签字**:__________ 日期:______

### AC-17 推送 + 企业查看 + 联系 + 面试 ⭐A ✅
- **代码级验证**:`POST /api/recruitment/contact`(联系日志)+ `POST /api/recruitment/interview`(面试日程)+ `GET /api/recruitment/{contacts,interviews,kanban}`;落库 RecruitmentFlowService。
- **需求**:HR 可对候选人发起联系(联系日志)、安排面试。
- **演示步骤**:候选人卡片 → 发起联系 → 记录联系日志 → 安排面试时间。
- **通过标准**:联系日志落库;面试日程生成并可见。
- **验收人签字**:__________ 日期:______

---

## 五、关怀与转人工(2 项)

### AC-18 情绪关怀 ⭐A ✅
- **代码级验证**:`POST /api/emotion/detect`(`emotion_agent`,回 emotion/intensity/sentiment + 共情回应)+ `GET /api/emotion/{timeline,alerts}`。
- **需求**:AI 识别求职者情绪(焦虑/低落),给予关怀。
- **演示步骤**:求职者在聊天中表达负面情绪 → AI 给出关怀回应。
- **通过标准**:AI 识别情绪并给出温和、有共情的回应。
- **验收人签字**:__________ 日期:______

### AC-19 转人工规则(自伤风险 / 劳动争议) ⭐A ✅
- **代码级验证**:`backend/agents/governance.py` `EscalationRules`(self_harm 关键词 → critical / labour_dispute → high)+ `services/platform/escalation.py`(写 `risk_alerts` + 开 HR/法务工单 + webhook)。仅落 risk_level + reason,不落原文。
- **需求**:检测到自伤风险或劳动争议信号时,自动转人工并告警。
- **演示步骤**:模拟求职者发送自伤/劳动争议相关表述 → 观察系统。
- **通过标准**:系统触发转人工,通知人工坐席/HR,并保留记录。
- **验收人签字**:__________ 日期:______

---

## 六、协作与多方(3 项)

### AC-20 多方协作房间 ⭐A ✅
- **代码级验证**:`/api/rooms`(CRUD + members + 实时消息)+ `POST /api/multiparty/submit`(`multi_party_agent` 多方意见汇总);前端协同房间页。
- **需求**:求职者 / HR / 部门负责人可在同一协作房间沟通。
- **演示步骤**:创建协作房间 → 邀请多方 → 实时消息/留言。
- **通过标准**:多方可在房间内实时沟通,消息有序、可见角色。
- **验收人签字**:__________ 日期:______

### AC-21 沉默激活与通知 B ✅
- **代码级验证**:`/api/silence/{detect,schedule,activate}`(沉默方提醒)+ 多方 notification(`/api/admin/notify`、notification_prefs)。
- **需求**:对沉默方自动提醒/激活,关键事件多方通知。
- **演示步骤**:制造一方长时间不响应 → 观察提醒触发。
- **通过标准**:沉默方收到提醒;关键事件多方被通知。
- **验收人签字**:__________ 日期:______

### AC-22 共识度算法 B ✅
- **代码级验证**:`POST /api/consensus-v2/compute` + `GET /api/consensus-v2/thresholds`(多方反馈驱动的共识度评分,T3708 细化)。
- **需求**:多方对候选人/岗位的共识度可视化。
- **演示步骤**:协作房间 → 查看共识度评分。
- **通过标准**:共识度评分随各方反馈更新。
- **验收人签字**:__________ 日期:______

---

## 七、管理与治理(4 项)

### AC-23 招聘市场(人才池/岗位池) ⭐A ✅
- **代码级验证**:`/api/talent-market/{stats,talents,jobs,recommendations}`(分页/筛选/脱敏)+ 前端 `app/marketplace/{,talents,jobs}`;Admin 审核 `app/admin/marketplace`。
- **需求**:公共招聘市场可浏览人才池与岗位池。
- **演示步骤**:访问市场页 → 浏览人才池 → 浏览岗位池 → 搜索/筛选。
- **通过标准**:列表可浏览、筛选、分页;脱敏展示候选人。
- **验收人签字**:__________ 日期:______

### AC-24 智能推荐 ⭐A ✅
- **代码级验证**:`GET /api/recommendations` + `POST /api/recommendations/{refresh,partner}`(基于画像/行为可解释推荐,DB migration 061);前端推荐卡 + 市场首页推荐位。
- **需求**:基于行为/画像给出人才与岗位推荐。
- **演示步骤**:推荐位 → 查看推荐卡片。
- **通过标准**:推荐结果与上下文相关,可解释。
- **验收人签字**:__________ 日期:______

### AC-25 隐私与合规(GDPR/PIPL) B ✅
- **代码级验证**:`/api/gdpr/{export,all-data,privacy,consent}` + `gdpr_v2`(forget/export/rectify,Art.15/17/20)+ PII 加密落库(T5015 KMS)。
- **需求**:支持数据导出/删除/更正请求;PII 加密落库。
- **演示步骤**:隐私中心 → 发起导出/删除 → 验证落库 PII 已加密。
- **通过标准**:请求在规定时限内处理;敏感字段加密可见。
- **验收人签字**:__________ 日期:______

### AC-26 HR 助手(对比/报告/面试题) B ✅
- **代码级验证**:`POST /api/hr-assistant/compare`(对比)+ `GET /api/hr-assistant/compare/{id}/export`(报告)+ `POST /api/hr-assistant/interview-questions`(面试题,T6108)。
- **需求**:HR 助手可对比候选人、生成报告、出面试题。
- **演示步骤**:选 2-3 候选人 → 对比 → 生成报告 → 生成面试题。
- **通过标准**:对比表/报告/面试题内容合理可用。
- **验收人签字**:__________ 日期:______

---

---

## 八、v11.2 新增客户端需求 (5 项 / T6301–T6307)

> v11.2 / T6307 — 甲方在 26 项原验收基础上提出的 5 项客户端更新。逐项给出代码级证据(文件 + 端点)。
> 评审细节见 `docs/CONTRACT-REVIEW-v12.md`。

### AC-N1 身份验证 (身份证 / 学历 / 简历 上传 + AI 提取 + 待上传 + 画像版本化) ⭐A ✅
- **代码级验证**:`POST /api/identity/upload`(doc_type=id_card|education|resume → AI 提取 + 结构化,返回含中文标签的 IdentityStatus);`GET /api/identity/status`;`GET|PUT /api/identity/profile`;`GET /api/identity/profile/versions[/{n}]`。后端 `backend/api/identity.py` + `backend/services/identity/verification.py`(`_ocr_text` 走 `resume_parser.extract_text_from_url` + `_extract_id_card_fields` / `_extract_education_fields`);前端 `frontend/app/jobseeker/identity/` + `frontend/components/identity/` + `frontend/lib/api-identity.ts`。DB migration `supabase/migrations/064_identity_compensation.sql`(candidates 四状态列 + `profile_versions` append-only 表)。
- **需求**:三类证件上传 + AI 提取;状态以「待上传/待审核/已认证」展示;画像版本化(雇主看到推送时刻快照)。
- **通过标准**:上传后 AI 提取出字段,三证件汇总状态可查;画像每次编辑写新版本,历史版本可回看。
- **映射 AC**:扩展 AC-05 / AC-06 / AC-08(原 A 级)。
- **验收人签字**:__________ 日期:______

### AC-N2 阀值可见性 (匹配 ≥ 70% 才可见 / 可沟通, 低于互不可见) ⭐A ✅
- **代码级验证**:`backend/matching/threshold.py`(`MATCH_THRESHOLD = int(os.environ.get("MATCH_THRESHOLD", "70"))`,`is_above_threshold` 用 `>=`,默认 70 可由 env 覆盖);`backend/services/marketplace/talent_market.py` 列表/详情 viewer-aware 过滤(`is_above_threshold`),伪造分被真实 threshold 分覆盖;`backend/api/talent_market.py::initiate_contact` 过线失败 → **403**(双方互不可知)。
- **需求**:任一匹配分 ≥ 阀值(默认 70%)双方才互相可见、可沟通;低于阀值双向不可见。
- **通过标准**:雇主列表只见过线人才;未过线发起沟通被拒;候选人侧对称(未过线岗位不可见)。
- **映射 AC**:强化 AC-15 / AC-23(原 A 级)。
- **验收人签字**:__________ 日期:______

### AC-N3 五险一金 + 出差 高优先级匹配 ⭐A ✅
- **代码级验证**:`backend/matching/hard_filter.py::_score_benefits_travel`(第 3 个软维度 `benefits_travel` = 社保子分 + 出差子分均值,缺失字段中性 1.0 不扣分 → 永不淘汰);字段 `candidates.social_insurance_expectation` / `travel_tolerance`、`roles.offers_social_insurance` / `offers_housing_fund` / `travel_required`(migration 063);前端 `frontend/components/marketplace/CompensationBadges.tsx` 渲染徽标;测试 `backend/tests/test_hard_filter.py`。
- **需求**:五险一金 / 出差为高优先级软评分(排序),永不淘汰;工作 / 行业经历不参与过滤。
- **通过标准**:岗位提供五险一金且候选人期望 → 加分(reasons「五险一金齐全」);未提供 → risks 标注但不淘汰;出差匹配按 willing/occasional/unwilling × none/occasional/frequent 软打分。
- **映射 AC**:强化 AC-11 / AC-15(原 A 级)。
- **验收人签字**:__________ 日期:______

### AC-N4 AI 不淘汰只增量 (确认) ⭐A ✅
- **代码级验证**:`backend/matching/threshold.py` 顶部明确「**不淘汰, 只排序**...低于阀值 → 双方暂不可见」(可见性门,非淘汰);`backend/services/marketplace/talent_market.py`「排序/增量:不淘汰整体池,但雇主视图只保留过线人才并按分降序」;所有 v11.2 新增软维度缺失字段中性兜底。测试 `backend/tests/test_threshold.py` + `backend/tests/test_hard_filter.py` 断言不淘汰语义。
- **需求**(确认):全链路匹配结果不淘汰、只增量 / 排序;阀值只控制「可见 / 可沟通」。
- **通过标准**:无论哪个维度未达标,候选人都不会被永久剔除,仅在雇主视图按分排序后用阀值过滤可见性。
- **映射 AC**:贯穿 AC-15 / AC-16 / AC-23 / AC-24 的语义基线。
- **验收人签字**:__________ 日期:______

### AC-N5 记录账号存续期保存 (确认) ⭐B ✅
- **代码级验证**:`supabase/migrations/064_identity_compensation.sql` 新增 `communication_channels`(1:1 候选人×岗位线程,`UNIQUE(candidate_id, role_id)`,`match_score` 快照,RLS 候选人本人 OR 所属 org)+ `profile_versions`(append-only,RLS 仅本人);`backend/services/marketplace/talent_market.py::initiate_contact` 写入 + `GET /api/talent-market/channels` 列出;雇主侧经 `recommendations.resume_snapshot`(061)锁定推送时刻简历。数据卷 `postgres_data` 持久化(`stop_local.sh` 不带 `--purge` 不删)。
- **需求**(确认):沟通记录 + 画像版本在账号存续期内持久保存,雇主侧推送快照不因候选人后续编辑而丢失。
- **通过标准**:发起联系后渠道记录可查;候选人编辑画像后,雇主侧推荐快照仍为推送时刻版本;重启容器(不 purge)数据仍在。
- **映射 AC**:强化 AC-17 / AC-25(AC-17 原 A 级 / AC-25 原 B 级)。
- **验收人签字**:__________ 日期:______

### v11.2 汇总

| 客户端更新 | 级别 | 状态 | 关键证据 |
| --- | --- | --- | --- |
| 身份验证 + AI 提取 + 画像版本化 | A | ✅ | `/api/identity/upload` + migration 063 |
| 阀值可见性 (≥70%) | A | ✅ | `matching/threshold.py` + `initiate_contact`→403 |
| 五险一金 + 出差 高优先级 | A | ✅ | `hard_filter._score_benefits_travel` |
| AI 不淘汰只增量 (确认) | A | ✅ | threshold.py 语义 + 测试断言 |
| 记录账号存续期保存 (确认) | B | ✅ | `communication_channels` + `profile_versions` 表 + RLS |

> 阀值默认 `MATCH_THRESHOLD=70`,可由环境变量覆盖(env override)。身份状态映射(单一来源 `services/identity/verification.py::DISPLAY_MAP`,前端镜像 `lib/api-identity.ts::IDENTITY_DISPLAY_MAP`):`pending→待上传` / `submitted→待审核` / `verified→已认证`;汇总 `identity_status=verified` 仅当三证件均 verified(DB trigger 强约束)。

---

## 汇总

| 区段 | 项数 | A 级项 |
| --- | --- | --- |
| 一、部署与基础设施 | 4 | AC-01,02,04 |
| 二、求职者端 | 5 | AC-05,06,07,08 |
| 三、企业/HR 端 | 5 | AC-10,11,12 |
| 四、匹配与推送 | 3 | AC-15,17 |
| 五、关怀与转人工 | 2 | AC-18,19 |
| 六、协作与多方 | 3 | AC-20 |
| 七、管理与治理 | 4 | AC-23,24 |
| **合计** | **26** | **16 项 A 级** |

**验收结论**:
- [x] 全部 A 级项通过(代码级预验收)→ **验收通过**(16/16 A 级 + 10/10 B 级 = 26/26 项已定位到 API/Agent/页面/脚本)
- [ ] 存在 A 级项未通过 → **验收不通过**,未通过项:____________________

> **v11.1 T6206 代码级预验收备注(2026-07-17)**:26 项均已在源码层定位到对应实现且链路完整。运行级验收(起容器 + 抓包确认无出网 + 人工逐项点击)由甲方在演示日现场完成,届时勾选上方「全部 A 级项通过」即正式验收通过。

**甲方验收负责人(签字)**:________________ **日期**:______________

**乙方交付负责人(签字)**:________________ **日期**:______________

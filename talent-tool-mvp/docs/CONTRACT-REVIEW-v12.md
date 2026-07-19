# 客户合同变更评审 v11 → v12 (CONTRACT-REVIEW-v12)

> v11.2 / T6301–T6307 — 甲方(客户)在 v11.1 验收基础上提出的 **5 项客户端更新**的逐项代码级评审。
> 每项给出:原始需求 / 改了什么 / 涉及文件 / 如何映射到 26 项验收清单。
> 评审基线 commit:b99d1fa(v11.1,26/26 通过,151 pages)。本版 build:**152/152 pages,tsc 0 错误**。

---

## 0. 关键约定 (Defaults & Maps)

### 0.1 匹配阀值 (Threshold)

- **默认值 `70`**:见 `backend/matching/threshold.py`:`MATCH_THRESHOLD = int(os.environ.get("MATCH_THRESHOLD", "70"))`。
- **环境变量覆盖**:设置 `MATCH_THRESHOLD=<int>` 即可(例如 `MATCH_THRESHOLD=60`)。docker-compose.local.yml 的 backend 服务可直接注入该 env。
- **判定语义**:`is_above_threshold(score)` 用 `score >= MATCH_THRESHOLD`(含等号,等于阀值即过线)。
- **门控位置**:
  - `backend/matching/threshold.py::VisibilityGate.decide()` → `{'visible','threshold','reason'}`。
  - `backend/services/marketplace/talent_market.py` 列表/详情/发起沟通三处复用 `is_above_threshold`。
  - `backend/api/talent_market.py::initiate_contact()` 过线失败返回 **403**。

### 0.2 身份状态展示映射 (Identity Display Map)

数据库存 `pending | submitted | verified` 三态,前端/后端统一映射为中文标签。**单一来源**:`backend/services/identity/verification.py::DISPLAY_MAP`,前端镜像在 `frontend/lib/api-identity.ts::IDENTITY_DISPLAY_MAP`。

| 数据库值 (`*_status`) | 中文标签 | 含义 |
| --- | --- | --- |
| `pending` | **待上传** | 尚未上传该证件 / 字段不清 |
| `submitted` | **待审核** | 已上传,AI 提取中或待复核 |
| `verified` | **已认证** | 字段提取成功且一致 |

> 汇总态 `identity_status` 仅当 `id_card_status` **AND** `education_doc_status` **AND** `resume_status` 三者均为 `verified` 时才为 `verified`(DB trigger `enforce_candidate_identity_rollup` 强约束,见 migration 063)。

---

## 1. 五项客户端更新逐项评审

### 更新 1 — 身份验证 (身份证 / 学历 / 简历 上传 + AI 提取 + 待上传 + 画像版本化) ⭐A

- **需求**:求职者上传三类证件(身份证 / 学历 / 简历),系统 AI 提取并结构化;证件状态以「待上传 / 待审核 / 已认证」展示;人才画像支持版本化(雇主看到的始终是推送时刻锁定快照)。
- **What changed (v11→v12)**:
  - 新增数据模型:migration `064_identity_compensation.sql` 在 `candidates` 上加 `identity_status / id_card_status / education_doc_status / resume_status` 四列 + `identity_verified_at`;新增 `profile_versions` 表(append-only,`candidate_id + version_no` 升序,`snapshot JSONB`)。
  - 新增后端服务 + API:`backend/services/identity/verification.py`(含 `_ocr_text` 走 `resume_parser.extract_text_from_url` + `_extract_id_card_fields` / `_extract_education_fields` 字段提取);`backend/api/identity.py` 挂在 `/api/identity`(`main.py:162`)。
  - 新增前端:`frontend/app/jobseeker/identity/`(page + `_client.tsx`)+ `frontend/components/identity/`(`IdentityStatusBadge` / `DocumentUploader` / `ProfileVersionHistory`)+ `frontend/lib/api-identity.ts`(状态枚举 + `IDENTITY_DISPLAY_MAP`)。
- **Files**:
  - DB:`supabase/migrations/064_identity_compensation.sql`
  - Backend:`backend/api/identity.py`,`backend/services/identity/verification.py`,`backend/services/identity/__init__.py`,`backend/main.py:121-173`
  - Frontend:`frontend/app/jobseeker/identity/page.tsx`,`frontend/app/jobseeker/identity/_client.tsx`,`frontend/components/identity/{IdentityStatusBadge,DocumentUploader,ProfileVersionHistory}.tsx`,`frontend/lib/api-identity.ts`
  - Tests:`backend/tests/test_identity_verification.py`
- **Endpoints**:
  - `POST /api/identity/upload` — 提交证件(doc_type=id_card|education|resume),触发 AI 提取,返回 IdentityStatus(含中文标签)
  - `GET /api/identity/status` — 当前用户三证件汇总状态
  - `GET|PUT /api/identity/profile` — 最新画像(可编辑);PUT 写入新版本
  - `GET /api/identity/profile/versions` — `[{version_no, created_at}, ...]`
  - `GET /api/identity/profile/versions/{version_no}` — 该版本快照
- **映射到 26 项验收**:扩展 **AC-05**(求职者注册登录 → 身份验证生命周期)、**AC-06**(简历上传 + 本地 OCR)、**AC-08**(画像生成 → 版本化锁定)。这两项原 A 级,本版补强仍 A 级。

---

### 更新 2 — 阀值可见性 (匹配 ≥ 70% 才可见 / 可沟通, 低于互不可见) ⭐A

- **需求**:双方仅当任一匹配分 ≥ 阀值(默认 70%)时才互相可见、可发起沟通;低于阀值则**双向不可见**(避免无效沟通)。**不淘汰、只排序**(甲方口径)。
- **What changed (v11→v12)**:
  - 新增阀值模块:`backend/matching/threshold.py`(`MATCH_THRESHOLD` env=70;`VisibilityGate.decide`;`best_score_against_roles/talents`)。
  - 注入 `talent_market` 服务层:`backend/services/marketplace/talent_market.py` 列表用 `is_above_threshold(best_score)` 过滤雇主可见人才(候选人对岗位取最佳分,命中任一即可见)、详情页 viewer-aware 过线判断、`initiate_contact()` 强制校验真实匹配分(失败抛 `ValueError → 403`)。
  - 伪造分替换为真实分:列表里原先的合成 `match_score` 被真实 threshold 分覆盖(`_override_synthetic_score`)。
  - 前端:`_client.tsx` 增加 threshold banner / 发起沟通按钮;详情页 `talents/[id]/page.tsx` 增加「低于阀值不可见」状态。
- **Files**:
  - Backend:`backend/matching/threshold.py`,`backend/services/marketplace/talent_market.py`,`backend/api/talent_market.py`,`backend/api/recommendations.py`(T6304 comm channel 持久化)
  - Frontend:`frontend/app/marketplace/talents/_client.tsx`,`frontend/app/marketplace/talents/[id]/page.tsx`,`frontend/app/marketplace/jobs/_client.tsx`,`frontend/components/marketplace/InitiateContactButton.tsx`,`frontend/lib/api-talent-market.ts`
  - Tests:`backend/tests/test_threshold.py`,`backend/tests/test_threshold_visibility.py`
- **Endpoints**:
  - `GET /api/talent-market/talents` — 雇主视图仅返回过线人才(按分降序)
  - `GET /api/talent-market/talents/{id}` — viewer-aware:雇主未过线 → 404
  - `GET /api/talent-market/jobs` / `/jobs/{id}` — 对称,候选人未过线 → 404
  - `POST /api/talent-market/initiate-contact` — 过线校验失败 → 403
  - `POST /api/recommendations/initiate-contact` — 推荐流对称入口
- **映射到 26 项验收**:强化 **AC-15**(双向匹配,现为带阀值门的双向可见性)、**AC-23**(招聘市场,脱敏 + 阀值过滤后展示)。两项原 A 级,本版补强仍 A 级。

---

### 更新 3 — 五险一金 + 出差 高优先级匹配 ⭐A

- **需求**:五险一金与出差是匹配的**高优先级**维度,但只做软评分(排序 / 增量),**永不淘汰**候选人;工作 / 行业经历不参与过滤。
- **What changed (v11→v12)**:
  - 新增匹配维度:`HardConditionFilter` 加第 3 个软维度 `benefits_travel`(`backend/matching/hard_filter.py:257-265,588+`),`_score_benefits_travel()` = 社保子分 + 出差子分均值;缺失字段 → 中性 1.0(不扣分)。
  - 数据字段:`candidates.social_insurance_expectation`(bool)+ `candidates.travel_tolerance`(willing|occasional|unwilling);`roles.offers_social_insurance`(默认 True)+ `roles.offers_housing_fund` + `roles.travel_required`(none|occasional|frequent)。
  - 前端展示:`frontend/components/marketplace/CompensationBadges.tsx` 渲染五险一金 / 公积金 / 出差徽标。
- **Files**:
  - Backend:`backend/matching/hard_filter.py`,`backend/matching/threshold.py`(包 filter)
  - DB:`supabase/migrations/064_identity_compensation.sql`(candidates + roles 薪酬/出差列)
  - Frontend:`frontend/components/marketplace/CompensationBadges.tsx`,`frontend/app/marketplace/{talents,jobs}/_client.tsx`
  - Tests:`backend/tests/test_hard_filter.py`(benefits_travel 维度)
- **映射到 26 项验收**:强化 **AC-15**(匹配,新增高优先级软维度)、**AC-11**(创建岗位,薪酬/出字段)。A 级补强。

---

### 更新 4 — AI 不淘汰只增量 (确认) ⭐A

- **需求**:确认全链路对 AI / 匹配结果采用「不淘汰、只增量 / 排序」语义 —— 任何匹配维度都不应导致候选人被永久剔除,阀值只控制「可见 / 可沟通」。
- **What changed (v11→v12)**:
  - 阀值模块文档化:`backend/matching/threshold.py` 顶部明确「**不淘汰, 只排序**...低于阀值 → 双方暂不可见」(可见性门,非淘汰)。
  - 服务层注释固化:`talent_market.py`「排序/增量:不淘汰整体池,但雇主视图只保留过线人才并按分降序」。
  - 软维度中性兜底:所有 v11.2 新增维度(benefits_travel 等)缺失字段一律中性分,不淘汰。
  - 这是**契约确认**(contract confirmation),无新增端点,主要落在 threshold.py / hard_filter.py / talent_market 服务层的语义保证 + 测试断言。
- **Files**:`backend/matching/threshold.py`,`backend/matching/hard_filter.py`(中性兜底),`backend/services/marketplace/talent_market.py`,`backend/tests/test_threshold.py`,`backend/tests/test_hard_filter.py`
- **映射到 26 项验收**:贯穿 **AC-15 / AC-16 / AC-23 / AC-24**(所有匹配相关项的语义基线)。A 级。

---

### 更新 5 — 记录账号存续期保存 (确认) ⭐B

- **需求**:确认沟通记录(发起联系 / 渠道)与候选人画像版本在账号存续期内持久保存,即使后续画像被编辑,雇主侧推送快照不丢失。
- **What changed (v11→v12)**:
  - 沟通渠道持久化:新增 `communication_channels` 表(`candidate_id, role_id, org_id, initiated_by, match_score` 快照, `status`),`UNIQUE(candidate_id, role_id)` 1:1 线程;RLS:候选人本人 OR 所属 org 可见。`initiate_contact()` 写入,`GET /api/talent-market/channels` 列出。
  - 画像版本化:新增 `profile_versions` 表(append-only 不可变快照),雇主侧通过 `recommendations.resume_snapshot`(061)锁定推送时刻简历;候选人编辑 → 新版本,旧版本保留。
  - 这是**持久化确认**(persistence confirmation),数据卷 `postgres_data` 持久化(LOCAL_DEPLOYMENT §5.7 / §8),`stop_local.sh`(无 `--purge`)不删数据。
- **Files**:`supabase/migrations/064_identity_compensation.sql`(communication_channels + profile_versions + RLS),`backend/services/marketplace/talent_market.py`(initiate_contact + channels),`backend/api/{talent_market,recommendations}.py`
- **Endpoints**:`POST /api/talent-market/initiate-contact`,`GET /api/talent-market/channels`,`GET /api/identity/profile/versions`
- **映射到 26 项验收**:强化 **AC-17**(推送 + 联系 + 面试,联系日志持久化)、**AC-25**(隐私,profile_versions RLS 仅本人)。B 级确认。

---

## 2. v11 → v12 变更汇总表

| # | 客户端更新 | 级别 | 主要新增文件 | 映射 AC 项 | 默认/约定 |
| --- | --- | --- | --- | --- | --- |
| 1 | 身份验证 + AI 提取 + 画像版本化 | A | `api/identity.py` + `services/identity/` + migration 063 + FE identity | AC-05,06,08 | 三证件状态 → 待上传/待审核/已认证 |
| 2 | 阀值可见性 (≥70% 可见/可沟通) | A | `matching/threshold.py` + talent_market 服务 | AC-15,23 | `MATCH_THRESHOLD=70` env 可覆盖 |
| 3 | 五险一金 + 出差 高优先级软匹配 | A | `hard_filter._score_benefits_travel` + CompensationBadges | AC-11,15 | 软评分,永不淘汰 |
| 4 | AI 不淘汰只增量 (确认) | A | threshold/hard_filter/talent_market 语义 + 测试 | AC-15,16,23,24 | 阀值=可见性门,非淘汰 |
| 5 | 记录账号存续期保存 (确认) | B | communication_channels + profile_versions 表 + RLS | AC-17,25 | append-only,持久化卷 |

---

## 3. 验收清单映射结论

26 项原验收清单中,本版 5 项客户端更新**强化 / 扩展**以下 8 项,不破坏任何既有 A 级项:

- **AC-05**(求职者注册登录)→ + 身份验证生命周期
- **AC-06**(简历 + 本地 OCR)→ + 身份证件 AI 提取
- **AC-08**(生成画像)→ + 画像版本化
- **AC-11**(创建岗位)→ + 五险一金/公积金/出差字段
- **AC-15**(双向匹配)→ + 阀值可见性门 + benefits_travel 维度
- **AC-17**(推送 + 联系 + 面试)→ + 沟通渠道持久化
- **AC-23**(招聘市场)→ + 阀值过滤后展示
- **AC-25**(隐私合规)→ + profile_versions RLS

> 详见 `docs/ACCEPTANCE_CHECKLIST.md`「八、v11.2 新增客户端需求」一节。

---

## 4. 构建与类型门

- `cd frontend && npx tsc --noEmit` → **exit 0**(0 类型错误)。
- `cd frontend && npx next build` → **152/152 pages**(v11.1 为 151,+1 新增 `/jobseeker/identity` 页)。
- 1 个构建警告为既有的可选 `livekit-client` 依赖 `@ts-expect-error`(非本版引入,非错误)。

**评审结论**:5 项客户端更新全部在代码层定位到实现且链路完整;契约确认项(更新 4、5)有表/服务/RLS 落地;阀值默认 70 + env 覆盖就绪;身份状态映射前后端一致。可进入运行级验收(起容器 + 抓包不出网 + 人工逐项点击)。

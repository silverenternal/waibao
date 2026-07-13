# Frontend Components Catalogue (T1607)

This document is the canonical index of every reusable UI component shipped
with the Mothership frontend, organised by domain.  Each component should
have a corresponding `*.stories.tsx` Storybook story so it can be inspected
in isolation.

## Conventions

* Naming: PascalCase for components, kebab-case for filenames of multi-word
  components within folders (`handoff-card.tsx`, `match-detail-card.tsx`).
* Directory layout: components are grouped by surface area —
  `ui/`, `shared/`, `mind/`, `mothership/`, `match/`.
* Each component is self-contained: props in, JSX out, no implicit
  router/auth/i18n side-effects.

## Catalogues

### UI primitives (`components/ui/`)

| Component         | Description                                       |
|-------------------|---------------------------------------------------|
| `Button`          | Primary, outline, ghost, destructive, link styles |
| `Badge`           | Inline status pill                                |
| `Card`            | Composable card surface                           |
| `Avatar`          | Image with fallback initials                      |
| `Input`           | Text input                                        |
| `Textarea`        | Multi-line text input                             |
| `Checkbox`        | Single checkbox                                   |
| `Select`          | Combobox-style select                             |
| `Label`           | Form label                                        |
| `Tabs`            | Tabs / panels                                     |
| `Dialog`          | Modal dialog                                      |
| `Sheet`           | Slide-over panel                                  |
| `Popover`         | Floating popover                                  |
| `DropdownMenu`    | Dropdown menu                                     |
| `Progress`        | Progress bar                                      |
| `Skeleton`        | Loading placeholder                               |
| `Separator`       | Horizontal / vertical divider                     |
| `Table`           | Composable data table                             |
| `Command`         | Command palette                                   |
| `Sonner`          | Toast provider                                    |
| `InputGroup`      | Input with addons                                 |
| `A11yLink`        | Accessible link with external-link support        |

### Shared surfaces (`components/shared/`)

| Component          | Description                                    |
|--------------------|------------------------------------------------|
| `CandidateCard`    | Card representing a candidate                  |
| `MatchCard`        | Match summary card                             |
| `MetricTile`       | KPI tile                                       |
| `EmptyState`       | Empty / no-data state                          |
| `LoadingSkeleton`  | Loading skeletons (card / list / table)        |
| `ConfidenceBadge`  | ML confidence indicator                        |
| `SkillChips`       | Skill chips list                               |
| `ActionCard`       | Call-to-action card                            |
| `DataTable`        | Generic data table                             |
| `DemoOverlay`      | Demo mode banner                               |
| `NotificationToast`| Toast notification                             |
| `KanbanBoard`      | Kanban with drag/drop columns                 |

### Mind surface (`components/mind/`)

Hiring-manager facing widgets.

| Component                | Description                       |
|--------------------------|-----------------------------------|
| `AnonymizedMatchCard`    | Anonymous candidate card          |
| `CandidateFilterBar`     | Search/filter bar                 |
| `CandidateGrid`          | Grid of candidate cards           |
| `CandidateList`          | List of candidates                |
| `DismissDialog`          | Dismiss-candidate dialog          |
| `PipelineCandidateCard`  | Pipeline stage card               |
| `QuoteCard`              | Pricing quote summary             |
| `QuoteRequestDialog`     | Request a quote dialog            |
| `RoleWizard`             | Multi-step role creation wizard   |
| `ViewToggle`             | Grid/list view toggle             |
| `WizardProgress`         | Wizard step progress              |
| `WizardStepTitle`        | Step: title input                 |
| `WizardStepDescription`  | Step: description input           |
| `WizardStepDetails`      | Step: location / type details     |
| `WizardStepRequirements` | Step: skills / experience         |
| `WizardStepReview`       | Step: review                      |

### Mothership surface (`components/mothership/`)

Talent-partner + admin widgets.

| Component               | Description                                |
|-------------------------|--------------------------------------------|
| `AdapterSyncButtons`    | Buttons to trigger ATS adapter sync        |
| `AlternativeWording`    | Suggested alternative phrasings            |
| `BiasAlert`             | Bias warning alert                         |
| `BiasExplanation`       | Bias explanation text                      |
| `CollectionCard`        | Card for a candidate collection            |
| `CollectionDetail`      | Collection detail view                     |
| `CollectionForm`        | Collection create/edit form                |
| `ConsensusScore`        | Match consensus score                      |
| `CopilotInput`          | NL→query input                             |
| `CopilotMessage`        | Chat message bubble                        |
| `CopilotSidebar`        | Sidebar hosting the copilot chat           |
| `CvUploadZone`          | CV file drop-zone                          |
| `DedupComparison`       | Side-by-side dedup view                    |
| `EmployerContradictionList` | List of employer contradictions         |
| `ExtractionField`       | Single extracted field with confidence     |
| `ExtractionViewer`      | Multi-field extraction viewer              |
| `HandoffCard`           | Candidate handoff card                     |
| `HandoffRespondDialog`  | Respond to handoff dialog                  |
| `HandoffSendDialog`     | Send handoff dialog                        |
| `HandoffStatusBadge`    | Handoff status pill                        |
| `HandoffTimeline`       | Handoff event timeline                     |
| `LegalHint`             | In-context legal reminder                  |
| `MatchActions`          | Action buttons for a match                  |
| `MatchDetailCard`       | Detailed match card                        |
| `ScoringBreakdown`      | Breakdown of structured/semantic/experience|
| `SignalFeed`            | Realtime signal feed                       |
| `SourceBadge`           | ATS source badge                           |
| `StakeholderMatrix`     | Stakeholder mapping                        |
| `TalentImageCard`       | Candidate image card                       |
| `TextPasteInput`        | Text-paste input zone                      |

### Match explainability (`components/match/`)

| Component            | Description                              |
|----------------------|------------------------------------------|
| `StrengthsList`      | Match strengths                          |
| `ConcernsList`       | Match concerns                           |
| `MatchReason`        | Single match reason with weight          |
| `MatchWeakPoints`    | Weak points for the match                |
| `MatchCounterfactual`| "What would raise the score" hint        |
| `EvalComparison`     | Candidate vs employer score comparison   |
| `EvalDiscuss`        | NL discussion of the score gap           |

### Top-level components

| Component               | Description                         |
|-------------------------|-------------------------------------|
| `ActionItemTracker`     | To-do tracker                       |
| `AssessmentReport`      | Beisen assessment summary           |
| `ATSConflictResolver`   | Conflict resolution across ATSs     |
| `ATSIntegrationCard`    | ATS integration card                |
| `ATSSyncStatus`         | Sync status indicator               |
| `BackgroundCheckStatus` | Background check status             |
| `CalendarSync`          | Calendar provider sync              |
| `ContradictionBadge`    | Contradiction count badge           |
| `EmotionChip`           | Emotion chip                        |
| `EmotionEventDetail`    | Single emotion event detail         |
| `EmotionTriggerCorrelation` | Trigger correlation chart         |
| `EmotionWeekSummary`    | Weekly emotion summary              |
| `EscalateToHumanButton` | Escalate to human                   |
| `FeedbackWidget`        | Quick feedback widget               |
| `FieldHighlight`        | Highlight a substring in text       |
| `FollowUpQuestions`     | Suggested follow-up questions       |
| `FunnelFilter`          | Funnel-stage filter                 |
| `GlobalSearchBar`       | Global search input                 |
| `GlobalSearchPalette`   | Command-palette search              |
| `InstallPrompt`         | PWA install prompt                  |
| `InterviewFeedback`     | Interview feedback capture          |
| `InterviewQuestion`     | Single interview question           |
| `JournalAdviceList`     | Journal advice list                 |
| `JournalWarningTimeline`| Journal warning timeline            |
| `JsonLd`                | JSON-LD structured data             |
| `LocaleSwitcher`        | Locale switcher                     |
| `NeedsList`             | Hiring needs list                   |
| `NegotiationScript`     | Offer-negotiation script            |
| `OfferBreakdown`        | Offer compensation breakdown        |
| `OfferComparisonTable`  | Side-by-side offer comparison       |
| `OfflineBanner`         | Offline indicator banner            |
| `OnboardingChecklist`   | First-run checklist                 |
| `ProductTour`           | In-app product tour                 |
| `ProfileCard`           | User profile card                   |
| `ProfileCompleteness`   | Profile completion meter            |
| `QuickSurvey`           | One-question survey                 |
| `ReasoningTrace`        | LLM reasoning trace                 |
| `RecommendedCandidate`  | Recommended candidate card          |
| `ResumeUpload`          | Resume upload widget                |
| `SalaryChart`           | Salary distribution chart           |
| `ScheduleVideoInterview`| Schedule a video interview          |
| `SearchResultItem`      | Single search result row            |
| `ServiceWorkerRegister` | Register the service worker         |
| `SkipToMain`            | A11y skip-to-main link              |
| `SubscriptionForm`      | Job subscription form               |
| `SubscriptionMatch`     | Match result for a subscription     |
| `ThemeProvider`         | Light/dark theme provider           |
| `VideoInterviewRecorder`| Video interview recorder           |
| `VideoMeetingCard`      | Video meeting card                  |
| `VoiceRecorder`         | Voice note recorder                 |
| `VoiceWaveform`         | Audio waveform visual               |

## Adding a new component

1. Create the file in the appropriate folder (`ui/`, `shared/`, `mind/`, …).
2. Co-locate a `*.stories.tsx` (CSF3) in the same folder so it shows up in
   Storybook automatically.
3. If the component is exported, re-export it from the relevant barrel file.
4. Update this catalogue with a one-line description.

## Cross-references

* [docs/STORYBOOK.md](STORYBOOK.md) — running and writing stories.
* [frontend/.storybook/main.ts](../talent-tool-mvp/frontend/.storybook/main.ts) — story globs.
* [frontend/.storybook/preview.ts](../talent-tool-mvp/frontend/.storybook/preview.ts) — global decorators.
---

## v9.1 Component Inventory (2026-07-13)

**315 components across 47 domains · 150 Storybook stories.**

### Jobseeker (新增 v9.1 — 主)

| Domain | Component | Purpose |
|---|---|---|
| `jobseeker/` | `<ProactiveBanner/>` | 顶部今日关怀 |
| `jobseeker/` | `<ChatBubble/>` `<ChatInput/>` `<ChatMessageList/>` | AI 知心朋友 |
| `jobseeker/` | `<ResumeSection/>` `<ResumeEditor/>` `<ResumeExport/>` | 简历块 |
| `jobseeker/` | `<JournalCard/>` `<JournalEditor/>` `<JournalRating/>` | 行业日记 |
| `jobseeker/` | `<EmotionDistribution/>` `<EmotionCareCard/>` | 情绪视图 |
| `jobseeker/` | `<PlanTimeline/>` `<PlanMilestoneCard/>` | 规划执行 |
| `jobseeker/` | `<InterviewRealtime/>` `<InterviewPersonaPicker/>` | AI 面试 |
| `jobseeker/` | `<OfferCompare/>` `<OfferNegotiateForm/>` `<OfferScoreCard/>` | Offer |
| `jobseeker/` | `<MemoryTimeline/>` `<MemoryEvidenceList/>` | AI 理解的我 |
| `jobseeker/` | `<ProactiveToast/>` | 主动 push |

### Shared (复用 v9.0 + 增加 v9.1)

| Domain | Count | Notes |
|---|---|---|
| `ui/` | 30+ | Button/Card/Input/Select/Dialog/Tabs/Toast/Tooltip/Badge |
| `shared/` | 15+ | EmptyState/LoadingShell/ErrorBoundary/MetricStat |
| `charts/` | 6 | Tremor KPI/BarChart/LineChart/DonutChart |

### Employer (v9.0)

- `mothership/`: HandoffCard, MatchDetailCard, PipelineStage
- `mind/`: JDGenerator, CandidateRankList
- `hr/`: ToneTrainer, BiasAuditResult, StrategyShoutout, JDMarketing
- `compliance/`: FakeCredentialDetector, PolicyExplainer
- `jd/`: Generator, MarketingDashboard
- `compare/`: CandidateCompare, RoleCompare
- `cost/`: CostBreakdownChart, CostAlertBadge
- `features/`: FeatureFlagToggle, FeatureCatalog
- … 共 31 个 domain

### Admin (v9.0 + 增加)

- `admin/`: ResourceList, ResourceForm, AuditTable
- `audit/`: AuditLogTable, AuditTimeline
- `feature-flags/`: FlagEditor, FlagAuditTrail
- `experiments/`: ExperimentCard, ABTestDetail

### Storybook 共 150 stories — 主要目录

- `components/ui/*.stories.tsx` (30+)
- `components/charts/*.stories.tsx` (6)
- `components/jobseeker/*.stories.tsx` (25+)
- `components/mothership/*.stories.tsx` (20+)
- `components/hr/*.stories.tsx` (10+)
- `components/compliance/*.stories.tsx` (5+)
- `components/admin/*.stories.tsx` (15+)
- `components/mind/*.stories.tsx` (10+)
- … 跨 47 个目录

### 用法 (约定)

```tsx
// 1. import
import { Button } from "@/components/ui/button";

// 2. 用 design token (Tailwind 已经映射 --color-primary 到 bg-primary)
<Button className="bg-primary text-primary-foreground">Save</Button>

// 3. 域组件
import { ProactiveBanner } from "@/components/jobseeker/ProactiveBanner";
<ProactiveBanner items={nudges} locale={locale} />
```

### 测试

- Storybook stories 充当 visual test (`npm run storybook:test` → Chromatic 视觉回归)。
- Domain components 加 Playwright `tests/jobseeker-v91.spec.ts` (7 paths)。

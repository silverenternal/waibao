# waibao v6.0 — EventBus Reference

> Canonical catalog of every domain event published by waibao agents,
> services, and integration surfaces. All events flow through the
> [`backend/eventbus`](../backend/eventbus) abstraction (either
> `InMemoryEventBus` in dev/test or `RedisEventBus` in prod).
>
> Last revised: 2026-07-12

---

## 1. Naming conventions

* **Topic shape:** `<aggregate>.<verb-past-tense>` (e.g. `profile.updated`,
  `ticket.escalated`). Domain names use dotted hierarchical scopes:
  `profile`, `emotion`, `plan`, `journal`, `role`, `strategy`, `ticket`,
  `agent`, `workflow`, `market`, `audit`, `metric`, `config`, `plugin`.
* **Payload contract:** every payload includes `id`, `ts` (UTC ISO), and
  any aggregate-specific fields documented below. Free-form extensions are
  allowed under `metadata: {...}`.
* **Correlation:** every event carries a `correlation_id` (uuid) when it
  is part of a workflow run; standalone events get `null`.
* **Bus envelope:** the bus always sets `event_id` (uuid4), `timestamp`
  (epoch seconds), `source` ("agent.<name>" / "service.<name>"), and
  propagates `metadata` verbatim.

---

## 2. Event catalog

### 2.1 `profile.*` — candidate profile state

| Event | Triggered by | Payload |
|---|---|---|
| `profile.updated` | `clarifier_agent`, `profile_agent` | `{user_id, candidate_id, fields: [str], completeness: float, source}` |
| `profile.created` | `intake_agent` | `{user_id, candidate_id, initial_fields: [str]}` |
| `profile.clarified` | `clarifier_agent` | `{user_id, candidate_id, must_haves: [str], confidence: float, questions: [str]}` |
| `profile.enriched` | `profile_extractor` service | `{user_id, candidate_id, new_skills: [str], source: str}` |

### 2.2 `needs.*`

| Event | Triggered by | Payload |
|---|---|---|
| `needs.clarified` | `clarifier_agent` | `{user_id, candidate_id, must_haves: [...], deal_breakers: [...], confidence: float}` |

### 2.3 `emotion.*`

| Event | Triggered by | Payload |
|---|---|---|
| `emotion.detected` | `emotion_agent` | `{user_id, primary_emotion, intensity, sentiment, evidence}` |
| `emotion.risk` | `emotion_agent` | `{user_id, risk_level, primary_emotion, intensity, recommended_action}` |

### 2.4 `plan.*`, `market.*`

| Event | Triggered by | Payload |
|---|---|---|
| `plan.generated` | `career_planner_agent` | `{user_id, candidate_id, plan_id, milestones: [str], horizon_months: int}` |
| `plan.updated` | `career_planner_agent` | `{user_id, plan_id, diff: {...}}` |
| `market.updated` | `career_planner_agent`, integrations | `{region, jobs_count, delta_pct, top_skills: [str]}` |

### 2.5 `journal.*`

| Event | Triggered by | Payload |
|---|---|---|
| `journal.submitted` | `daily_journal_agent` | `{user_id, journal_id, mood, summary, ts}` |
| `journal.summarized` | `daily_journal_agent` | `{user_id, window: 'weekly'|'monthly', highlights: [str]}` |

### 2.6 `role.*`

| Event | Triggered by | Payload |
|---|---|---|
| `role.image.updated` | `employer_clarifier_agent` | `{employer_id, role_id, traits: [str], must_haves: [str]}` |

### 2.7 `strategy.*`

| Event | Triggered by | Payload |
|---|---|---|
| `strategy.updated` | `vision_agent` | `{employer_id, vision_id, themes: [str], horizon_months: int}` |

### 2.8 `ticket.*`

| Event | Triggered by | Payload |
|---|---|---|
| `ticket.created` | `hr_service_agent` | `{ticket_id, employer_id, severity, category, summary}` |
| `ticket.escalated` | `hr_service_agent` | `{ticket_id, from_level, to_level, reason}` |
| `ticket.resolved` | `hr_service_agent` | `{ticket_id, resolver_id, resolution_time_s}` |

### 2.9 `agent.*` — lifecycle

| Event | Triggered by | Payload |
|---|---|---|
| `agent.started` | `agents.runtime` | `{agent_name, user_id, run_id, input_keys: [str]}` |
| `agent.completed` | `agents.runtime` | `{agent_name, user_id, run_id, latency_ms, artifacts_count}` |
| `agent.failed` | `agents.runtime` | `{agent_name, user_id, run_id, error, recoverable: bool}` |
| `agent.timeout` | `agents.runtime` | `{agent_name, user_id, run_id, after_s}` |

### 2.10 `workflow.*`

| Event | Triggered by | Payload |
|---|---|---|
| `workflow.started` | `WorkflowEngine` | `{workflow_name, run_id, started_by}` |
| `workflow.completed` | `WorkflowEngine` | `{workflow_name, run_id, status}` |
| `workflow.paused` | `WorkflowEngine` | `{workflow_name, run_id, at_node, reason}` |
| `workflow.resumed` | `WorkflowEngine` | `{workflow_name, run_id, decision}` |

### 2.11 `audit.*`, `metric.*`

| Event | Triggered by | Payload |
|---|---|---|
| `audit.recorded` | `services.audit` | `{actor_id, action, resource, before, after}` |
| `metric.emitted` | `services.metrics` | `{metric, value, tags: {...}}` |

### 2.12 `config.*` — runtime configuration

| Event | Triggered by | Payload |
|---|---|---|
| `config.changed` | `config_service` | `{scope, key, version, value, changed_by}` |
| `config.rolled_back` | `config_service` | `{scope, key, from_version, to_version, changed_by}` |

### 2.13 `plugin.*`

| Event | Triggered by | Payload |
|---|---|---|
| `plugin.installed` | `PluginRunner` | `{plugin, version, manifest_hash}` |
| `plugin.enabled` | `Plugin` | `{plugin, version}` |
| `plugin.disabled` | `Plugin` | `{plugin, reason}` |
| `plugin.error` | `PluginRunner` | `{plugin, error_type, message}` |

### 2.14 `matching.*`

| Event | Triggered by | Payload |
|---|---|---|
| `candidate.matched` | `services.candidate_recommender` | `{candidate_id, partner_id, match_id, score}` |
| `match.shortlisted` | `talents` | `{candidate_id, job_id, partner_id, rank}` |

### 2.15 `interview.*`, `offer.*`, `funnel.*`

| Event | Triggered by | Payload |
|---|---|---|
| `interview.scheduled` | `services.calendar_sync` | `{interview_id, candidate_id, partner_id, when_iso}` |
| `interview.scored` | `services.ai_interviewer` | `{interview_id, score, dimensions}` |
| `offer.created` | `services.offer_calculator` | `{offer_id, candidate_id, employer_id, total}` |
| `funnel.stage_changed` | `services.recruitment_funnel` | `{candidate_id, from_stage, to_stage, ts}` |

---

## 3. Subscribers

`backend/eventbus/subscribers.py` registers every cross-cutting handler in
one place. The current roster (15 subscribers):

1. **notify** — `profile.updated` → push to candidate / partner mobile app
2. **notify** — `ticket.escalated` → page on-call HR
3. **analytics** — `agent.completed` / `workflow.completed` → funnel metrics
4. **audit** — `config.changed` / `audit.recorded` → immutable audit log
5. **realtime** — `profile.updated` / `role.image.updated` → SSE channel
6. **match** — `profile.updated` → re-run matchers (debounced)
7. **career** — `market.updated` → re-rank candidate plans
8. **journal** — `emotion.detected` → enrich journal entries
9. **hr** — `ticket.created` → assign queue by severity
10. **workflow** — `agent.completed` → resume paused workflow runs
11. **plugin** — `plugin.enabled` → grant permissions
12. **metric** — `metric.emitted` → forward to OTel collector
13. **sentry** — `agent.failed` → exception capture
14. **crm** — `funnel.stage_changed` → CRM push
15. **roi** — `plan.generated` → billable credit consumption

Adding a new cross-cutter: append a `@on_event("foo.bar")` handler to
`backend/eventbus/subscribers.py` — no other module needs to change.

---

## 4. Versioning

Minor additions (new event names) are non-breaking and shipped at any
time. Breaking changes — payload field removal or type tightening — must
ship under a new event name (`profile.updated.v2`) and the old name must
remain a registered alias for at least one release cycle.

---

## 5. Observability

* Every bus exposes `errors` (list of `{event, error, subscription_id}`)
  for in-memory debugging — see `InMemoryEventBus.errors`.
* In production, an internal `audit.recorded` handler writes every
  emitted event to `platform_event_log` for 30 days (Supabase retention).

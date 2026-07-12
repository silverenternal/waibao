import type { ApiClient } from "./api";
import {
  MOCK_CANDIDATES,
  MOCK_ROLES,
  MOCK_MATCHES,
  MOCK_COLLECTIONS,
  MOCK_USERS,
  anonymizeCandidate,
  getCandidateById,
} from "./mock-data";
import type { Candidate, Role, Collection, Handoff, Quote } from "@/contracts/canonical";

const delay = (ms = 300) => new Promise((resolve) => setTimeout(resolve, ms + Math.random() * 200));

export const mockApi: ApiClient = {
  candidates: {
    list: async () => { await delay(); return [...MOCK_CANDIDATES]; },
    get: async (id) => {
      await delay();
      const c = MOCK_CANDIDATES.find((c) => c.id === id);
      if (!c) throw new Error("Candidate not found");
      return c;
    },
    create: async (data) => {
      await delay(500);
      return {
        id: crypto.randomUUID(),
        ...data,
        email: data.email ?? null,
        phone: data.phone ?? null,
        location: data.location ?? null,
        linkedin_url: data.linkedin_url ?? null,
        cv_text: data.cv_text ?? null,
        profile_text: data.profile_text ?? null,
        skills: [],
        experience: [],
        seniority: null,
        salary_expectation: null,
        availability: null,
        industries: [],
        sources: [],
        dedup_group: null,
        dedup_confidence: null,
        extraction_confidence: 0,
        extraction_flags: [],
        embedding: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        created_by: MOCK_USERS[0].id,
      } as Candidate;
    },
    update: async (id, data) => {
      await delay();
      const c = MOCK_CANDIDATES.find((c) => c.id === id);
      if (!c) throw new Error("Candidate not found");
      return { ...c, ...data, updated_at: new Date().toISOString() } as Candidate;
    },
    search: async (query) => {
      await delay();
      const q = query.toLowerCase();
      return MOCK_CANDIDATES.filter(
        (c) =>
          c.first_name.toLowerCase().includes(q) ||
          c.last_name.toLowerCase().includes(q) ||
          c.skills.some((s) => s.name.toLowerCase().includes(q)) ||
          c.location?.toLowerCase().includes(q)
      );
    },
    uploadCV: async () => {
      await delay(1500);
      return MOCK_CANDIDATES[0];
    },
    extractFromText: async () => {
      await delay(1500);
      return MOCK_CANDIDATES[0];
    },
  },
  roles: {
    list: async () => { await delay(); return [...MOCK_ROLES]; },
    get: async (id) => {
      await delay();
      const r = MOCK_ROLES.find((r) => r.id === id);
      if (!r) throw new Error("Role not found");
      return r;
    },
    create: async (data) => {
      await delay(500);
      return {
        id: crypto.randomUUID(),
        ...data,
        required_skills: [],
        preferred_skills: [],
        seniority: null,
        salary_band: data.salary_band ?? null,
        location: data.location ?? null,
        remote_policy: data.remote_policy ?? "hybrid",
        industry: null,
        extraction_confidence: null,
        embedding: null,
        status: "draft",
        created_at: new Date().toISOString(),
        created_by: MOCK_USERS[1].id,
      } as Role;
    },
    update: async (id, data) => {
      await delay();
      const r = MOCK_ROLES.find((r) => r.id === id);
      if (!r) throw new Error("Role not found");
      return { ...r, ...data } as Role;
    },
    extractRequirements: async () => {
      await delay(1000);
      return {
        required_skills: MOCK_ROLES[0].required_skills,
        preferred_skills: MOCK_ROLES[0].preferred_skills,
        seniority: MOCK_ROLES[0].seniority,
      };
    },
  },
  matches: {
    forRole: async (roleId) => {
      await delay();
      return MOCK_MATCHES.filter((m) => m.role_id === roleId);
    },
    forCandidate: async (candidateId) => {
      await delay();
      return MOCK_MATCHES.filter((m) => m.candidate_id === candidateId);
    },
    updateStatus: async (matchId, status) => {
      await delay();
      const m = MOCK_MATCHES.find((m) => m.id === matchId);
      if (!m) throw new Error("Match not found");
      return { status: "updated", match_id: matchId, new_status: status };
    },
    forRoleAnonymized: async (roleId) => {
      await delay();
      const matches = MOCK_MATCHES.filter((m) => m.role_id === roleId);
      return matches.map((match) => {
        const candidate = getCandidateById(match.candidate_id);
        return {
          match,
          candidate: candidate ? anonymizeCandidate(candidate) : anonymizeCandidate(MOCK_CANDIDATES[0]),
        };
      });
    },
  },
  collections: {
    list: async () => { await delay(); return [...MOCK_COLLECTIONS]; },
    get: async (id) => {
      await delay();
      const c = MOCK_COLLECTIONS.find((c) => c.id === id);
      if (!c) throw new Error("Collection not found");
      return c;
    },
    create: async (data) => {
      await delay();
      return {
        id: crypto.randomUUID(),
        name: data.name,
        description: data.description ?? null,
        owner_id: MOCK_USERS[0].id,
        visibility: data.visibility ?? "private",
        shared_with: data.shared_with ?? null,
        candidate_ids: [],
        tags: data.tags ?? [],
        candidate_count: 0,
        avg_match_score: null,
        available_now_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as Collection;
    },
    addCandidate: async (collectionId) => {
      await delay();
      const c = MOCK_COLLECTIONS.find((c) => c.id === collectionId);
      if (!c) throw new Error("Collection not found");
      return c;
    },
    removeCandidate: async () => { await delay(); },
  },
  handoffs: {
    inbox: async () => { await delay(); return []; },
    outbox: async () => { await delay(); return []; },
    create: async (data) => {
      await delay();
      return {
        id: crypto.randomUUID(),
        from_partner_id: MOCK_USERS[0].id,
        to_partner_id: data.to_partner_id,
        candidate_ids: data.candidate_ids,
        context_notes: data.context_notes,
        target_role_id: data.target_role_id ?? null,
        status: "pending",
        response_notes: null,
        attribution_id: crypto.randomUUID(),
        created_at: new Date().toISOString(),
        responded_at: null,
      } as Handoff;
    },
    respond: async (id, accept, notes) => {
      await delay();
      return {
        id,
        from_partner_id: MOCK_USERS[0].id,
        to_partner_id: MOCK_USERS[0].id,
        candidate_ids: [],
        context_notes: "",
        target_role_id: null,
        status: accept ? "accepted" : "declined",
        response_notes: notes ?? null,
        attribution_id: crypto.randomUUID(),
        created_at: new Date().toISOString(),
        responded_at: new Date().toISOString(),
      } as Handoff;
    },
  },
  quotes: {
    request: async (data) => {
      await delay();
      const isPool = (MOCK_CANDIDATES.find((c) => c.id === data.candidate_id)?.sources.length ?? 0) > 1;
      return {
        id: crypto.randomUUID(),
        client_id: MOCK_USERS[1].id,
        candidate_id: data.candidate_id,
        role_id: data.role_id,
        is_pool_candidate: isPool,
        base_fee: 15000,
        pool_discount: isPool ? 3000 : null,
        final_fee: isPool ? 12000 : 15000,
        fee_breakdown: {
          calculation: "15% of estimated first-year salary",
          base: "15,000",
          discount: isPool ? "Pre-vetted talent network discount: -3,000" : null,
        },
        status: "generated",
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString(),
      } as Quote;
    },
    list: async () => { await delay(); return []; },
    get: async () => { await delay(); throw new Error("Quote not found"); },
    updateStatus: async (quoteId, status) => {
      await delay();
      return {
        id: quoteId,
        client_id: MOCK_USERS[1].id,
        candidate_id: MOCK_CANDIDATES[0].id,
        role_id: MOCK_ROLES[0].id,
        is_pool_candidate: false,
        base_fee: 15000,
        pool_discount: null,
        final_fee: 15000,
        fee_breakdown: {},
        status,
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString(),
      } as Quote;
    },
  },
  copilot: {
    query: async () => {
      return new Response(
        JSON.stringify({
          summary: "Mock copilot response.",
          interpretation: "Interpreted your query",
          results: [],
          total_count: 0,
          actions: [],
          followup_suggestions: ["Show more candidates", "Filter by location"],
        }),
        { headers: { "Content-Type": "application/json" } }
      );
    },
    stream: async () => {
      // Return a mock SSE stream
      const events = [
        `data: ${JSON.stringify({ phase: "parsing", message: "Understanding..." })}\n\n`,
        `data: ${JSON.stringify({ phase: "parsed", interpretation: "Mock query parsed" })}\n\n`,
        `data: ${JSON.stringify({ phase: "executing", message: "Searching..." })}\n\n`,
        `data: ${JSON.stringify({ phase: "executed", total_count: 0 })}\n\n`,
        `data: ${JSON.stringify({ phase: "complete", summary: "Mock results", actions: [], followup_suggestions: [] })}\n\n`,
        `data: ${JSON.stringify({ phase: "done" })}\n\n`,
      ].join("");
      return new Response(events, { headers: { "Content-Type": "text/event-stream" } });
    },
  },
  signals: {
    recent: async () => { await delay(); return []; },
  },
  admin: {
    stats: async () => {
      await delay();
      return {
        totals: { candidates: MOCK_CANDIDATES.length, roles: MOCK_ROLES.length, matches: MOCK_MATCHES.length },
        active: { active_roles: MOCK_ROLES.filter((r) => r.status === "active").length },
        growth_7d: { new_candidates: 5, new_matches: 12 },
      };
    },
    pipelineStatus: async () => {
      await delay();
      return {
        extraction_queue: { pending: 12, low_confidence_review: 3, processed: 847 },
        confidence_distribution: { high: 42, medium: 8, low: 2 },
        embedding_coverage: { with_embedding: 45, total: 52, percentage: 86.5 },
      };
    },
    adapterHealth: async () => {
      await delay();
      return [
        { adapter_name: "bullhorn", status: "healthy", last_sync: "2026-03-24T08:00:00Z", records_processed: 312, error_count: 3 },
        { adapter_name: "hubspot", status: "healthy", last_sync: "2026-03-24T07:30:00Z", records_processed: 189, error_count: 4 },
        { adapter_name: "linkedin", status: "degraded", last_sync: "2026-03-23T22:00:00Z", records_processed: 95, error_count: 8 },
      ];
    },
    users: async () => { await delay(); return [...MOCK_USERS]; },
  },
  users: {
    me: async () => { await delay(); return MOCK_USERS[0]; },
  },
  health: async () => { await delay(); return { status: "ok" }; },
  analytics: {
    funnel: async (days = 30) => {
      await delay();
      const stages = ["sourced", "applied", "screened", "interviewed", "offered", "hired"];
      const counts = [120, 84, 56, 32, 18, 9];
      const stage_metrics = stages.map((s, i) => ({
        stage: s,
        candidates: counts[i],
        events: counts[i] + 5,
      }));
      const conversion: Record<string, number> = {};
      for (let i = 1; i < stages.length; i++) {
        conversion[`${stages[i - 1]}_to_${stages[i]}`] =
          Math.round((counts[i] / counts[i - 1]) * 1000) / 10;
      }
      return {
        org_id: null,
        since_days: days,
        period_start: new Date(Date.now() - days * 86400000).toISOString(),
        period_end: new Date().toISOString(),
        total_candidates: counts[0],
        stages: stage_metrics,
        conversion_rates: conversion,
        by_source: {
          linkedin: { sourced: 60, applied: 42, screened: 28, interviewed: 18, offered: 10, hired: 5 },
          referral: { sourced: 30, applied: 22, screened: 14, interviewed: 8, offered: 5, hired: 3 },
          indeed: { sourced: 30, applied: 20, screened: 14, interviewed: 6, offered: 3, hired: 1 },
        },
        overall_conversion: Math.round((counts[5] / counts[0]) * 1000) / 10,
      };
    },
    funnelStages: async (days = 30) => {
      const f = await mockApi.analytics.funnel(days);
      return {
        stages: f.stages,
        conversion_rates: f.conversion_rates,
        overall_conversion: f.overall_conversion,
        total_candidates: f.total_candidates,
        since_days: f.since_days,
        period_start: f.period_start,
        period_end: f.period_end,
      };
    },
    channels: async (
      days = 30,
      model: "first_touch" | "last_touch" | "multi_touch" = "last_touch",
    ) => {
      await delay();
      const channels = [
        { channel: "linkedin", model, candidates: 60, hires: 5, hire_credit: 1, cost_cents: 30000, revenue_cents: 100000, roi: 2.33, cost_per_hire: 6000 },
        { channel: "referral", model, candidates: 30, hires: 3, hire_credit: 1, cost_cents: 10000, revenue_cents: 100000, roi: 9.0, cost_per_hire: 3333.3 },
        { channel: "indeed", model, candidates: 30, hires: 1, hire_credit: 1, cost_cents: 50000, revenue_cents: 100000, roi: 1.0, cost_per_hire: 50000 },
      ];
      return { model, channels, best_channel: "referral" };
    },
    channelRoi: async (days = 30) => {
      const c = await mockApi.analytics.channels(days);
      const first = await mockApi.analytics.channels(days, "first_touch");
      const multi = await mockApi.analytics.channels(days, "multi_touch");
      return {
        org_id: null,
        since_days: days,
        period_start: new Date(Date.now() - days * 86400000).toISOString(),
        period_end: new Date().toISOString(),
        by_model: {
          first_touch: first.channels,
          last_touch: c.channels,
          multi_touch: multi.channels,
        },
        best_channel_by_model: {
          first_touch: "referral",
          last_touch: "referral",
          multi_touch: "referral",
        },
        summary: {
          first_touch: { channels: first.channels.length, total_hires: 9, total_cost_cents: 90000, total_revenue_cents: 300000, avg_roi: 4.1 },
          last_touch: { channels: c.channels.length, total_hires: 9, total_cost_cents: 90000, total_revenue_cents: 300000, avg_roi: 4.1 },
          multi_touch: { channels: multi.channels.length, total_hires: 9, total_cost_cents: 90000, total_revenue_cents: 300000, avg_roi: 4.1 },
        },
      };
    },
    funnelWithCosts: async (days = 30) => {
      await delay();
      const f = await mockApi.analytics.funnel(days);
      // Add mock cost data per stage
      return {
        ...f,
        stages: f.stages.map((s: any, i: number) => ({
          ...s,
          total_cost_cents: 10000 * (i + 1),
          avg_cost_cents: 10000,
        })),
      };
    },
    funnelTrend: async (weeks = 12) => {
      await delay();
      const trend = Array.from({ length: weeks }, (_, i) => {
        const start = new Date(Date.now() - (weeks - i) * 7 * 86400000);
        const end = new Date(Date.now() - (weeks - i - 1) * 7 * 86400000);
        return {
          week_start: start.toISOString(),
          week_end: end.toISOString(),
          by_stage: { sourced: 20 + i, applied: 15 + i, screened: 10 + i, interviewed: 6 + i, offered: 3 + i, hired: 1 + i },
        };
      });
      return { weeks, trend };
    },
    recordFunnelEvents: async (
      events: Array<{
        candidate_id: string;
        stage: string;
        source?: string;
        role_id?: string;
        cost_cents?: number;
        metadata?: Record<string, unknown>;
        occurred_at?: string;
      }>,
    ) => {
      await delay();
      return { ok: events.length, total: events.length };
    },
  },
  subscriptions: {
    list: async () => {
      await delay();
      return {
        subscriptions: [
          {
            id: "sub-1",
            user_id: "u1",
            name: "Shanghai senior Python",
            criteria: {
              role: "engineer",
              city: "Shanghai",
              salary_min: 30000,
              currency: "CNY",
              skills: ["python", "django"],
              seniority: "senior",
              remote_policy: "hybrid",
            },
            channels: ["web", "email"],
            enabled: true,
            created_at: "2026-07-01T00:00:00Z",
            updated_at: "2026-07-01T00:00:00Z",
          },
        ],
      };
    },
    get: async (id: string) => {
      const { subscriptions } = await mockApi.subscriptions.list();
      const sub = subscriptions.find((s) => s.id === id);
      if (!sub) throw new Error("not found");
      return sub;
    },
    create: async (data) => {
      await delay();
      return {
        id: `sub-${Date.now()}`,
        user_id: "u1",
        name: data.name,
        criteria: data.criteria,
        channels: data.channels,
        enabled: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
    },
    update: async (id, data) => {
      const sub = await mockApi.subscriptions.get(id);
      return {
        ...sub,
        ...data,
        criteria: { ...sub.criteria, ...(data.criteria ?? {}) },
        updated_at: new Date().toISOString(),
      };
    },
    delete: async (id) => {
      await delay();
      return { ok: true, id };
    },
    matches: async (id) => {
      await delay();
      return {
        subscription_id: id,
        count: 2,
        matches: [
          {
            id: "j1",
            title: "Senior Backend Engineer",
            company: "Acme",
            city: "Shanghai",
            salary_min: 30000,
            salary_max: 50000,
            currency: "CNY",
            skills: ["python", "django"],
            seniority: "senior",
            remote_policy: "hybrid",
            score: 0.82,
            reasons: ["title matches 'engineer'", "matched skills: python, django"],
          },
          {
            id: "j2",
            title: "Python Tech Lead",
            company: "Globex",
            city: "Shanghai",
            salary_min: 40000,
            salary_max: 70000,
            currency: "CNY",
            skills: ["python"],
            seniority: "lead",
            remote_policy: "remote",
            score: 0.71,
            reasons: ["title matches 'engineer'"],
          },
        ],
      };
    },
  },
  recommendations: {
    forRole: async (roleId) => {
      await delay();
      return {
        role_id: roleId,
        count: 3,
        candidates: [
          {
            candidate_id: "c1",
            full_name: "Alice Chen",
            headline: "Senior Python",
            city: "Shanghai",
            seniority: "senior",
            skills: ["python", "django", "postgres"],
            years_experience: 7,
            overall_score: 0.86,
            structured_score: 0.9,
            semantic_score: 0.82,
            experience_score: 0.85,
            confidence: "strong",
            reasons: ["matched 3 skills", "seniority matches (senior)"],
            missing_skills: [],
          },
          {
            candidate_id: "c2",
            full_name: "Bob Liu",
            headline: "Backend dev",
            city: "Beijing",
            seniority: "mid",
            skills: ["python"],
            years_experience: 4,
            overall_score: 0.62,
            structured_score: 0.7,
            semantic_score: 0.55,
            experience_score: 0.6,
            confidence: "good",
            reasons: ["matched 1 skills"],
            missing_skills: ["django"],
          },
          {
            candidate_id: "c3",
            full_name: "Carol Wang",
            headline: "Full-stack",
            city: "Shanghai",
            seniority: "senior",
            skills: ["python", "react"],
            years_experience: 6,
            overall_score: 0.58,
            structured_score: 0.6,
            semantic_score: 0.55,
            experience_score: 0.6,
            confidence: "possible",
            reasons: ["seniority matches (senior)"],
            missing_skills: ["django"],
          },
        ],
      };
    },
  },
};

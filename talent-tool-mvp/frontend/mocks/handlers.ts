/**
 * T5007 — MSW request handlers (mock API).
 *
 * These intercept the SAME `fetch` calls the real `apiClient` makes
 * (see lib/api.ts → `${API_BASE}/api/...`), so toggling
 * NEXT_PUBLIC_USE_MOCK=true transparently serves fixture data with zero code
 * changes in pages/components.
 *
 * Coverage (30+ endpoints):
 *   - health
 *   - users (me, admin list)
 *   - candidates (list/get/search/upload/extract)
 *   - roles (list/get/extract-requirements)
 *   - matches (forRole/forCandidate/anonymized/status)
 *   - collections (list/get/add/remove)
 *   - handoffs (inbox/outbox/create/respond)
 *   - analytics funnel + channels
 *   - subscriptions + recommendations
 *   - admin stats / pipeline / adapters
 *
 * Anything not matched falls through to the real network (passthrough).
 */

import { http, HttpResponse, delay, passthrough } from "msw";
import type {
  Candidate,
  Role,
  Collection,
  Handoff,
} from "@/contracts/canonical";
import type { PaginatedResponse } from "@/lib/api";
import {
  MOCK_USERS,
  MOCK_CANDIDATES,
  MOCK_ROLES,
  MOCK_MATCHES,
  MOCK_COLLECTIONS,
  anonymizeCandidate,
  getCandidateById,
} from "./data";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const LATENCY = () => 80 + Math.random() * 160;

// In-memory mutable stores so POST/PATCH reflect immediately within a session.
const candidates: Candidate[] = MOCK_CANDIDATES.map((c) => ({ ...c }));
const roles: Role[] = MOCK_ROLES.map((r) => ({ ...r }));
const collections: Collection[] = MOCK_COLLECTIONS.map((c) => ({ ...c }));
const handoffs: Handoff[] = [];

function paginate<T>(items: T[]): PaginatedResponse<T> {
  return {
    data: items,
    total: items.length,
    page: 1,
    page_size: items.length,
    total_pages: 1,
  };
}

function ok<T>(body: T, init?: ResponseInit) {
  return HttpResponse.json(body as Record<string, unknown>, init);
}

function notFound() {
  return HttpResponse.json(
    { detail: "Not found" },
    { status: 404 },
  );
}

export const handlers = [
  // ---------------------------------------------------------------
  // Health
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/health`, async () => {
    await delay(LATENCY());
    return ok({ status: "ok" });
  }),

  // ---------------------------------------------------------------
  // Users
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/users/me`, async () => {
    await delay(LATENCY());
    return ok(MOCK_USERS[0]);
  }),
  http.get(`${API_BASE}/api/admin/users`, async () => {
    await delay(LATENCY());
    return ok(MOCK_USERS);
  }),

  // ---------------------------------------------------------------
  // Candidates
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/candidates`, async ({ request }) => {
    await delay(LATENCY());
    const url = new URL(request.url);
    const q = url.searchParams.get("q");
    const list = q
      ? candidates.filter((c) =>
          `${c.first_name} ${c.last_name}`.toLowerCase().includes(q.toLowerCase()),
        )
      : candidates;
    return ok(paginate(list));
  }),
  http.get(`${API_BASE}/api/candidates/search`, async ({ request }) => {
    await delay(LATENCY());
    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    return ok(paginate(candidates.filter((c) =>
      `${c.first_name} ${c.last_name} ${c.skills.join(" ")}`
        .toLowerCase()
        .includes(q),
    )));
  }),
  http.get(`${API_BASE}/api/candidates/:id`, async ({ params }) => {
    await delay(LATENCY());
    const c = getCandidateById(String(params.id));
    return c ? ok(c) : notFound();
  }),
  http.post(`${API_BASE}/api/candidates`, async ({ request }) => {
    await delay(LATENCY());
    const body = (await request.json()) as Partial<Candidate>;
    const created: Candidate = {
      id: crypto.randomUUID(),
      email: body.email ?? null,
      phone: body.phone ?? null,
      location: body.location ?? null,
      linkedin_url: body.linkedin_url ?? null,
      cv_text: body.cv_text ?? null,
      profile_text: body.profile_text ?? null,
      first_name: body.first_name ?? "",
      last_name: body.last_name ?? "",
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
    };
    candidates.unshift(created);
    return ok(created, { status: 201 });
  }),
  http.post(`${API_BASE}/api/candidates/extract`, async () => {
    await delay(LATENCY());
    return ok(candidates[0]);
  }),
  http.post(`${API_BASE}/api/candidates/upload`, async () => {
    await delay(LATENCY());
    return ok(candidates[0]);
  }),

  // ---------------------------------------------------------------
  // Roles
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/roles`, async () => {
    await delay(LATENCY());
    return ok(paginate(roles));
  }),
  http.get(`${API_BASE}/api/roles/:id`, async ({ params }) => {
    await delay(LATENCY());
    const r = roles.find((x) => x.id === String(params.id));
    return r ? ok(r) : notFound();
  }),
  http.post(`${API_BASE}/api/roles`, async ({ request }) => {
    await delay(LATENCY());
    const body = (await request.json()) as Partial<Role>;
    const created = {
      ...body,
      id: crypto.randomUUID(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as Role;
    roles.unshift(created);
    return ok(created, { status: 201 });
  }),
  http.post(`${API_BASE}/api/roles/extract-requirements`, async () => {
    await delay(LATENCY());
    return ok({
      required_skills: roles[0].required_skills,
      preferred_skills: roles[0].preferred_skills,
      seniority: roles[0].seniority,
    });
  }),

  // ---------------------------------------------------------------
  // Matches
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/matches/role/:roleId`, async ({ params }) => {
    await delay(LATENCY());
    return ok(MOCK_MATCHES.filter((m) => m.role_id === String(params.roleId)));
  }),
  http.get(`${API_BASE}/api/matches/candidate/:candidateId`, async ({ params }) => {
    await delay(LATENCY());
    return ok(
      MOCK_MATCHES.filter((m) => m.candidate_id === String(params.candidateId)),
    );
  }),
  http.get(`${API_BASE}/api/matches/role/:roleId/anonymized`, async ({ params }) => {
    await delay(LATENCY());
    const ms = MOCK_MATCHES.filter((m) => m.role_id === String(params.roleId));
    return ok(
      ms.map((m) => {
        const c = getCandidateById(m.candidate_id);
        return { match: m, candidate: c ? anonymizeCandidate(c) : ({} as never) };
      }),
    );
  }),
  http.patch(`${API_BASE}/api/matches/:matchId/status`, async ({ params, request }) => {
    await delay(LATENCY());
    const body = (await request.json()) as { status: string };
    return ok({
      status: "ok",
      match_id: String(params.matchId),
      new_status: body.status,
    });
  }),

  // ---------------------------------------------------------------
  // Collections
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/collections`, async () => {
    await delay(LATENCY());
    return ok(collections);
  }),
  http.get(`${API_BASE}/api/collections/:id`, async ({ params }) => {
    await delay(LATENCY());
    const c = collections.find((x) => x.id === String(params.id));
    return c ? ok(c) : notFound();
  }),
  http.post(`${API_BASE}/api/collections`, async ({ request }) => {
    await delay(LATENCY());
    const body = (await request.json()) as Partial<Collection>;
    const created = {
      ...body,
      id: crypto.randomUUID(),
      candidate_ids: [],
      created_at: new Date().toISOString(),
    } as Collection;
    collections.unshift(created);
    return ok(created, { status: 201 });
  }),

  // ---------------------------------------------------------------
  // Handoffs
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/handoffs/inbox`, async () => {
    await delay(LATENCY());
    return ok(handoffs.filter((h) => h.to_partner_id === MOCK_USERS[0].id));
  }),
  http.get(`${API_BASE}/api/handoffs/outbox`, async () => {
    await delay(LATENCY());
    return ok(handoffs.filter((h) => h.from_partner_id === MOCK_USERS[0].id));
  }),
  http.post(`${API_BASE}/api/handoffs`, async ({ request }) => {
    await delay(LATENCY());
    const body = (await request.json()) as Partial<Handoff>;
    const created = {
      ...body,
      id: crypto.randomUUID(),
      status: "pending",
      response_notes: null,
      attribution_id: crypto.randomUUID(),
      created_at: new Date().toISOString(),
      responded_at: null,
    } as Handoff;
    handoffs.unshift(created);
    return ok(created, { status: 201 });
  }),

  // ---------------------------------------------------------------
  // Analytics (funnel + channels)
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/analytics/funnel`, async () => {
    await delay(LATENCY());
    return ok({
      stages: ["applied", "screened", "interviewed", "offered", "hired"],
      counts: { applied: 480, screened: 240, interviewed: 96, offered: 32, hired: 18 },
      conversion: { applied_to_hired: 0.0375 },
    });
  }),
  http.get(`${API_BASE}/api/analytics/funnel/stages`, async () => {
    await delay(LATENCY());
    return ok({
      stages: ["applied", "screened", "interviewed", "offered", "hired"],
    });
  }),
  http.get(`${API_BASE}/api/analytics/channels`, async () => {
    await delay(LATENCY());
    return ok({
      model: "last_touch",
      channels: [
        { channel: "linkedin", count: 120 },
        { channel: "referral", count: 64 },
        { channel: "job_board", count: 200 },
      ],
    });
  }),
  http.get(`${API_BASE}/api/analytics/channels/roi`, async () => {
    await delay(LATENCY());
    return ok({
      channels: [
        { channel: "linkedin", spend_cents: 500000, hires: 6, cpa_cents: 83333 },
        { channel: "referral", spend_cents: 0, hires: 4, cpa_cents: 0 },
      ],
    });
  }),

  // ---------------------------------------------------------------
  // Subscriptions + recommendations
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/subscriptions`, async () => {
    await delay(LATENCY());
    return ok({ subscriptions: [] });
  }),
  http.get(`${API_BASE}/api/recommendations/candidates/:roleId`, async () => {
    await delay(LATENCY());
    return ok({ role_id: "mock", count: 0, candidates: [] });
  }),

  // ---------------------------------------------------------------
  // Admin
  // ---------------------------------------------------------------
  http.get(`${API_BASE}/api/admin/stats`, async () => {
    await delay(LATENCY());
    return ok({ candidates: candidates.length, roles: roles.length, matches: MOCK_MATCHES.length });
  }),
  http.get(`${API_BASE}/api/admin/pipeline/status`, async () => {
    await delay(LATENCY());
    return ok({ status: "ok", queued: 0, processing: 0 });
  }),
  http.get(`${API_BASE}/api/admin/adapters/health`, async () => {
    await delay(LATENCY());
    return ok([
      { name: "bullhorn", healthy: true },
      { name: "greenhouse", healthy: true },
    ]);
  }),

  // ---------------------------------------------------------------
  // Copilot (NL query)
  // ---------------------------------------------------------------
  http.post(`${API_BASE}/api/copilot/query`, async ({ request }) => {
    await delay(LATENCY());
    const body = (await request.json()) as { query?: string };
    return ok({
      answer: `Mock answer for: "${body.query ?? ""}"`,
      citations: [],
    });
  }),

  // ---------------------------------------------------------------
  // Passthrough: anything else hits the real network.
  // ---------------------------------------------------------------
  http.all(`${API_BASE}/*`, () => passthrough()),
];

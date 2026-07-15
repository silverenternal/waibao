/**
 * v11.0 T6110 — Safety / human-escalation API client.
 *
 * Talks to /api/admin/risk-alerts/* and /api/escalation on the FastAPI
 * backend.  Per 甲方要求 the backend returns ONLY risk_level + reason (+ the
 * matched-keyword *category* hint) — never the user's raw private
 * conversation.  The same invariant holds in these types: there is no field
 * for verbatim chat text.
 *
 *   GET  /api/admin/risk-alerts          admin/HR — list redacted alerts
 *   POST /api/admin/risk-alerts/check    preview-screen a snippet (no persist)
 *   POST /api/escalation                 one-click manual escalation (ticket)
 */
import { fetchAPI } from "@/lib/api";

const RISK_BASE = "/api/admin/risk-alerts";
const ESCALATION_BASE = "/api/escalation";

export type EscalationRule = "self_harm" | "labour_dispute";
export type RiskLevel = "critical" | "high";

/** Redacted risk-alert row — no raw conversation, ever. */
export interface RiskAlert {
  id: string;
  user_id: string;
  organisation_id?: string | null;
  rule: EscalationRule;
  risk_level: RiskLevel;
  reason: string;
  matched_keywords: string[];
  message: string;
  ticket_id?: string | null;
  notified: boolean;
  created_at: string;
}

export interface EscalationHit {
  rule: EscalationRule;
  risk_level: RiskLevel;
  reason: string;
  message: string;
  matched_keywords: string[];
}

export interface CheckResult {
  must_escalate: boolean;
  hits: EscalationHit[];
}

/** National 24h psychological-aid hotline (kept client-side for the popup). */
export const SELF_HARM_HOTLINE = "400-161-9995";

/** List redacted risk alerts (admin/HR only). */
export async function listRiskAlerts(params?: {
  risk_level?: RiskLevel;
  organisation_id?: string;
  limit?: number;
}): Promise<RiskAlert[]> {
  const qs = new URLSearchParams();
  if (params?.risk_level) qs.set("risk_level", params.risk_level);
  if (params?.organisation_id) qs.set("organisation_id", params.organisation_id);
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchAPI<RiskAlert[]>(`${RISK_BASE}${suffix}`);
}

/**
 * Preview-screen a snippet for mandatory-escalation triggers WITHOUT
 * persisting or notifying.  Used by chat to decide whether to surface the
 * hand-off dialog before responding.  The verbatim text is not echoed back.
 */
export async function checkEscalation(text: string): Promise<CheckResult> {
  return fetchAPI<CheckResult>(`${RISK_BASE}/check`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

/** One-click manual escalation → creates an HR ticket. */
export async function escalateToHuman(body: {
  text: string;
  department?: string;
  priority?: string;
  organisation_id?: string;
  context?: Record<string, unknown>;
}): Promise<{
  success: boolean;
  ticket_id?: string;
  ticket_no?: string;
  priority: string;
  department: string;
  message: string;
}> {
  return fetchAPI(`${ESCALATION_BASE}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

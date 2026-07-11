// T1004 - Admin audit log API client.
import { fetchAPI } from "@/lib/api";

export interface AuditEntry {
  id: string;
  created_at: string;
  actor_user_id: string | null;
  user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  metadata: Record<string, unknown>;
}

export interface AuditListResponse {
  data: AuditEntry[];
  limit: number;
  offset: number;
}

export interface AuditFilter {
  user_id?: string;
  actor_user_id?: string;
  resource_type?: string;
  action?: string;
  since_days?: number;
  limit?: number;
  offset?: number;
}

export async function listAudit(filter: AuditFilter = {}): Promise<AuditListResponse> {
  const params = new URLSearchParams();
  if (filter.user_id) params.set("user_id", filter.user_id);
  if (filter.actor_user_id) params.set("actor_user_id", filter.actor_user_id);
  if (filter.resource_type) params.set("resource_type", filter.resource_type);
  if (filter.action) params.set("action", filter.action);
  if (filter.since_days !== undefined) params.set("since_days", String(filter.since_days));
  if (filter.limit !== undefined) params.set("limit", String(filter.limit));
  if (filter.offset !== undefined) params.set("offset", String(filter.offset));
  const qs = params.toString();
  return fetchAPI<AuditListResponse>(
    `/api/admin/audit${qs ? `?${qs}` : ""}`
  );
}

export function exportAuditUrl(filter: Pick<AuditFilter, "user_id" | "since_days"> = {}): string {
  const params = new URLSearchParams();
  if (filter.user_id) params.set("user_id", filter.user_id);
  if (filter.since_days !== undefined) params.set("since_days", String(filter.since_days));
  const qs = params.toString();
  return `/api/admin/audit/export${qs ? `?${qs}` : ""}`;
}
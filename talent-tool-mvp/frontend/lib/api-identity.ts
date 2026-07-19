/**
 * v11.2 T6303 — Identity verification + profile versioning API client.
 *
 * Two-sided talent market 甲方 (client) A-level requirement:
 *   jobseeker uploads 身份证 (id_card) / 学历证明 (education) / 简历 (resume),
 *   the backend AI-extracts the main fields, and the per-doc status shows
 *   待上传 (pending) / 待审核 (submitted) / 已认证 (verified). The overall
 *   identity_status is 'verified' ONLY when ALL three docs are 'verified'.
 *
 * Backend routes (mount under /api/identity, auth = current talent user):
 *   POST /api/identity/upload                 {doc_type, file_url|file_id}
 *   GET  /api/identity/status                 -> IdentityStatus
 *   GET  /api/identity/profile                -> {profile: StructuredProfile | null}
 *   PUT  /api/identity/profile                {profile} -> {version_no, profile}
 *   GET  /api/identity/profile/versions       -> {versions: ProfileVersionMeta[]}
 *   GET  /api/identity/profile/versions/{n}   -> {version_no, snapshot}
 *
 * Style mirrors frontend/lib/api-talent-market.ts (typed functions over a
 * shared ``fetchAPI`` from @/lib/api).
 */

import { fetchAPI } from "@/lib/api";

const BASE = "/api/identity";

// ---------------------------------------------------------------------------
// Status enum + display map (shared contract with backend DISPLAY_MAP)
// ---------------------------------------------------------------------------

/** Per-doc / overall verification status. Mirrors DB CHECK constraint. */
export type IdentityDocStatus = "pending" | "submitted" | "verified";

/**
 * pending   -> 待上传  (not verified yet / unclear / not uploaded)
 * submitted -> 待审核  (uploaded, awaiting AI extraction)
 * verified  -> 已认证  (fields extracted + consistent)
 */
export const IDENTITY_DISPLAY_MAP: Record<IdentityDocStatus, string> = {
  pending: "待上传",
  submitted: "待审核",
  verified: "已认证",
};

export function identityStatusLabel(status: string | null | undefined): string {
  if (!status) return IDENTITY_DISPLAY_MAP.pending;
  return IDENTITY_DISPLAY_MAP[status as IdentityDocStatus] ?? status;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** The three document types a talent uploads (exact field names everywhere). */
export type DocType = "id_card" | "education" | "resume";

export const DOC_TYPES: DocType[] = ["id_card", "education", "resume"];

/** Display meta per doc type (label + hint shown in the uploader). */
export const DOC_META: Record<DocType, { label: string; hint: string }> = {
  id_card: { label: "身份证", hint: "上传身份证正反面,系统自动识别号码" },
  education: { label: "学历证明", hint: "上传毕业证 / 学位证,系统识别学校与学历" },
  resume: { label: "简历", hint: "上传 PDF / Word 简历,AI 自动解析结构化档案" },
};

/** Roll-up + per-doc identity status (mirrors backend IdentityStatus.to_dict). */
export interface IdentityStatus {
  /** Computed roll-up: verified only when all three docs are verified. */
  overall: IdentityDocStatus;
  id_card: IdentityDocStatus;
  education: IdentityDocStatus;
  resume: IdentityDocStatus;
  /** Pre-computed Chinese display labels from the backend. */
  overall_display: string;
  id_card_display: string;
  education_display: string;
  resume_display: string;
  /** Optional human-readable reason per doc (why it is still 待上传). */
  reasons: Partial<Record<DocType, string>>;
}

/**
 * Editable structured profile snapshot. Stored as JSONB in profile_versions.
 * The backend treats this as an opaque object; these fields are the canonical
 * editable surface the form binds to (增量 — never deletes previous versions).
 */
export interface StructuredProfile {
  name?: string;
  title?: string;
  city?: string;
  skills?: string[];
  education?: string;
  experience?: string;
  expected_salary?: string;
  /** candidate expects 五险一金 (social insurance + housing fund). HIGH priority. */
  social_insurance_expectation?: boolean;
  /** willingness to travel: willing | occasional | unwilling. HIGH priority. */
  travel_tolerance?: "willing" | "occasional" | "unwilling";
  [key: string]: unknown;
}

export const TRAVEL_TOLERANCE_OPTIONS: Array<{
  value: StructuredProfile["travel_tolerance"];
  label: string;
}> = [
  { value: "willing", label: "接受出差" },
  { value: "occasional", label: "偶尔出差" },
  { value: "unwilling", label: "不出差" },
];

/** Light-weight version metadata (from list_versions). */
export interface ProfileVersionMeta {
  version_no: number;
  created_at: string | null;
}

/** Upload request body. */
export interface UploadDocumentBody {
  doc_type: DocType;
  /** Signed URL of the already-uploaded file (preferred). */
  file_url?: string;
  /** Storage object id / path (fallback when no URL). */
  file_id?: string;
}

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------

/** POST /upload — submit a doc for AI extraction; returns the rolled-up status. */
export async function uploadIdentityDocument(
  body: UploadDocumentBody,
): Promise<IdentityStatus> {
  return fetchAPI<IdentityStatus>(`${BASE}/upload`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /status — current user's rolled-up IdentityStatus (with display labels). */
export async function fetchIdentityStatus(): Promise<IdentityStatus> {
  return fetchAPI<IdentityStatus>(`${BASE}/status`);
}

/** GET /profile — latest editable structured profile (null if none yet). */
export async function fetchProfile(): Promise<StructuredProfile | null> {
  const res = await fetchAPI<{ profile: StructuredProfile | null }>(
    `${BASE}/profile`,
  );
  return res?.profile ?? null;
}

/**
 * PUT /profile — update the structured profile + save a NEW version (增量).
 * Returns the new version_no and the latest profile.
 */
export async function updateProfile(
  profile: StructuredProfile,
): Promise<{ version_no: number; profile: StructuredProfile | null }> {
  return fetchAPI<{ version_no: number; profile: StructuredProfile | null }>(
    `${BASE}/profile`,
    {
      method: "PUT",
      body: JSON.stringify({ profile }),
    },
  );
}

/** GET /profile/versions — all versions newest-first. */
export async function fetchProfileVersions(): Promise<ProfileVersionMeta[]> {
  const res = await fetchAPI<{ versions: ProfileVersionMeta[] }>(
    `${BASE}/profile/versions`,
  );
  return res?.versions ?? [];
}

/** GET /profile/versions/{n} — the snapshot for a specific version_no. */
export async function fetchProfileVersion(
  versionNo: number,
): Promise<StructuredProfile> {
  const res = await fetchAPI<{
    version_no: number;
    snapshot: StructuredProfile;
  }>(`${BASE}/profile/versions/${encodeURIComponent(versionNo)}`);
  return res.snapshot;
}

/**
 * Convenience: classify a status into a badge tone.
 * pending -> amber, submitted -> blue, verified -> green.
 */
export type IdentityBadgeTone = "amber" | "blue" | "green";

export function identityBadgeTone(
  status: string | null | undefined,
): IdentityBadgeTone {
  switch (status) {
    case "verified":
      return "green";
    case "submitted":
      return "blue";
    case "pending":
    default:
      return "amber";
  }
}

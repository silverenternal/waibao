/**
 * T6109 — Recruitment flow API client (contact logs + interview schedule).
 *
 * Talks to /api/recruitment/* on the FastAPI backend. All endpoints are
 * org-scoped: the backend resolves the employer's org_id from the JWT, so
 * the client just needs to be authenticated.
 */

import { fetchAPI } from "@/lib/api";

const BASE = "/api/recruitment";

// ---------------------------------------------------------------------------
// shared enums (mirror backend CHECK constraints)
// ---------------------------------------------------------------------------

export type ContactMethod =
  | "phone"
  | "email"
  | "wechat"
  | "sms"
  | "video"
  | "in_person"
  | "other";

export type ContactStatus =
  | "reached"
  | "no_answer"
  | "left_message"
  | "rejected"
  | "interested"
  | "follow_up";

export type InterviewFormat = "onsite" | "video" | "phone";

export type InterviewStatus =
  | "scheduled"
  | "completed"
  | "cancelled"
  | "no_show"
  | "rescheduled";

export type KanbanStage = "contact" | "interview" | "result";

export const CONTACT_METHOD_LABELS: Record<ContactMethod, string> = {
  phone: "电话",
  email: "邮件",
  wechat: "微信",
  sms: "短信",
  video: "视频",
  in_person: "当面",
  other: "其他",
};

export const CONTACT_STATUS_LABELS: Record<ContactStatus, string> = {
  reached: "已联系上",
  no_answer: "未接听",
  left_message: "已留言",
  rejected: "已拒绝",
  interested: "有意向",
  follow_up: "需跟进",
};

export const INTERVIEW_FORMAT_LABELS: Record<InterviewFormat, string> = {
  onsite: "现场",
  video: "视频",
  phone: "电话",
};

export const INTERVIEW_STATUS_LABELS: Record<InterviewStatus, string> = {
  scheduled: "已安排",
  completed: "已完成",
  cancelled: "已取消",
  no_show: "未到面",
  rescheduled: "已改期",
};

// ---------------------------------------------------------------------------
// response types
// ---------------------------------------------------------------------------

export interface ContactLog {
  id: string;
  candidate_id: string;
  role_id: string;
  org_id: string;
  hr_id: string;
  contact_method: ContactMethod;
  contact_date: string;
  status: ContactStatus;
  notes: string;
  candidate_name: string;
  role_title: string;
  created_at: string;
  updated_at: string;
}

export interface InterviewSlot {
  id: string;
  candidate_id: string;
  role_id: string;
  org_id: string;
  hr_id: string;
  date: string;
  time: string;
  location: string;
  format: InterviewFormat;
  status: InterviewStatus;
  candidate_name: string;
  role_title: string;
  created_at: string;
  updated_at: string;
}

export interface KanbanCandidate {
  candidate_id: string;
  candidate_name: string;
  role_id: string;
  role_title: string;
  contact_status: ContactStatus | null;
  last_contact_date: string | null;
  interview_status: InterviewStatus | null;
  next_interview: string | null;
  contacts: ContactLog[];
  interviews: InterviewSlot[];
  stage: KanbanStage;
}

export interface KanbanBoard {
  org_id: string;
  candidates: KanbanCandidate[];
  totals: {
    contacted: number;
    interviewing: number;
    completed: number;
  };
}

// ---------------------------------------------------------------------------
// request types
// ---------------------------------------------------------------------------

export interface CreateContactInput {
  candidate_id: string;
  role_id?: string;
  contact_method?: ContactMethod;
  contact_date?: string;
  status?: ContactStatus;
  notes?: string;
  candidate_name?: string;
  role_title?: string;
}

export interface ScheduleInterviewInput {
  candidate_id: string;
  role_id?: string;
  date: string;
  time: string;
  location?: string;
  format?: InterviewFormat;
  status?: InterviewStatus;
  candidate_name?: string;
  role_title?: string;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function recordContact(
  input: CreateContactInput
): Promise<ContactLog> {
  return fetchAPI<ContactLog>(`${BASE}/contact`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listContacts(params?: {
  candidate_id?: string;
  status?: ContactStatus;
  limit?: number;
  offset?: number;
}): Promise<ContactLog[]> {
  const qs = new URLSearchParams();
  if (params?.candidate_id) qs.set("candidate_id", params.candidate_id);
  if (params?.status) qs.set("status", params.status);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchAPI<ContactLog[]>(`${BASE}/contacts${suffix}`);
}

export async function scheduleInterview(
  input: ScheduleInterviewInput
): Promise<InterviewSlot> {
  return fetchAPI<InterviewSlot>(`${BASE}/interview`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listInterviews(params?: {
  candidate_id?: string;
  status?: InterviewStatus;
  limit?: number;
  offset?: number;
}): Promise<InterviewSlot[]> {
  const qs = new URLSearchParams();
  if (params?.candidate_id) qs.set("candidate_id", params.candidate_id);
  if (params?.status) qs.set("status", params.status);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchAPI<InterviewSlot[]>(`${BASE}/interviews${suffix}`);
}

export async function updateInterviewStatus(
  interviewId: string,
  status: InterviewStatus
): Promise<InterviewSlot> {
  return fetchAPI<InterviewSlot>(
    `${BASE}/interviews/${interviewId}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }
  );
}

export async function fetchKanban(): Promise<KanbanBoard> {
  return fetchAPI<KanbanBoard>(`${BASE}/kanban`);
}

/**
 * Referrals API client (T2405).
 */

export const REFERRAL_STATUS_LABEL: Record<string, string> = {
  pending: "待审核",
  reviewed: "已查看",
  interview: "面试中",
  offered: "已发 offer",
  hired: "已入职",
  rewarded: "已发奖",
  rejected: "已拒绝",
};

export const REFERRAL_STATUS_COLOR: Record<string, string> = {
  pending: "bg-slate-200 text-slate-700",
  reviewed: "bg-blue-100 text-blue-700",
  interview: "bg-amber-100 text-amber-700",
  offered: "bg-purple-100 text-purple-700",
  hired: "bg-emerald-100 text-emerald-700",
  rewarded: "bg-emerald-500 text-white",
  rejected: "bg-rose-100 text-rose-700",
};

export interface ReferralItem {
  id: string;
  referrer_id: string;
  referrer_name?: string;
  candidate_email: string;
  candidate_name?: string;
  job_title?: string;
  status: keyof typeof REFERRAL_STATUS_LABEL;
  bonus_amount?: number;
  created_at: string;
}

export interface MyReferrals {
  referrer_id: string;
  total_referrals: number;
  status_breakdown: Record<string, number>;
  successful_hires: number;
  total_points: number;
  rewards_earned: number;
}

export interface LeaderboardEntry {
  rank: number;
  referrer_id: string;
  total_points: number;
}

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`Referrals API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function createReferral(payload: {
  candidate_email: string;
  candidate_name?: string;
  role_id?: string;
  job_title?: string;
  notes?: string;
}) {
  return http<{ referral: ReferralItem; points_awarded: { points: number } }>(
    "/api/referrals",
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function fetchMyReferrals() {
  return http<MyReferrals>("/api/referrals/me");
}

export async function fetchHrInbox(status?: string) {
  const url = status
    ? `/api/referrals/team?status=${encodeURIComponent(status)}`
    : "/api/referrals/team";
  return http<{ items: ReferralItem[]; count: number }>(url);
}

export async function reviewReferral(
  referralId: string,
  targetStatus: string,
  hrNotes?: string,
) {
  return http(`/api/referrals/${referralId}/review`, {
    method: "POST",
    body: JSON.stringify({ target_status: targetStatus, hr_notes: hrNotes }),
  });
}

export async function rewardReferral(referralId: string, amount = 5000) {
  return http(`/api/referrals/${referralId}/reward`, {
    method: "POST",
    body: JSON.stringify({ amount, currency: "CNY" }),
  });
}

export async function fetchLeaderboard(limit = 10) {
  return http<{ leaderboard: LeaderboardEntry[] }>(
    `/api/referrals/leaderboard?limit=${limit}`,
  );
}

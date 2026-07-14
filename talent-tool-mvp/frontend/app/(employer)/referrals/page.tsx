"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ReferralCard } from "@/components/referrals/ReferralCard";
import { ReferralLeaderboard } from "@/components/referrals/ReferralLeaderboard";
import { fetchHrInbox, type ReferralItem } from "@/lib/api-referrals";

const STATUS_FILTERS = [
  { value: "", label: "全部" },
  { value: "pending", label: "待审核" },
  { value: "reviewed", label: "已查看" },
  { value: "interview", label: "面试中" },
  { value: "offered", label: "已发 offer" },
  { value: "hired", label: "已入职" },
];

/**
 * HR 内部推荐收件箱 (T2405).
 */
export default function HrReferralInboxPage() {
  const [status, setStatus] = React.useState("");
  const [items, setItems] = React.useState<ReferralItem[]>([]);
  const [loading, setLoading] = React.useState(false);

  const refresh = React.useCallback(async (s: string) => {
    setLoading(true);
    try {
      const r = await fetchHrInbox(s || undefined);
      setItems(r.items);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh(status);
  }, [status, refresh]);

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 space-y-6">
        <h1 className="text-2xl font-bold">内部推荐收件箱</h1>
        <div className="flex flex-wrap gap-2">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              className={`px-3 py-1.5 rounded text-sm transition-colors ${
                status === f.value
                  ? "bg-blue-500 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
              onClick={() => setStatus(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            {loading && <p className="text-slate-500 text-sm">加载中…</p>}
            {!loading && items.length === 0 && (
              <p className="text-slate-500 text-sm">当前状态暂无推荐</p>
            )}
            {items.map((r) => (
              <ReferralCard key={r.id} referral={r} hrView />
            ))}
          </div>
          <div>
            <ReferralLeaderboard />
          </div>
        </div>
      </div>)</ErrorBoundary>
  );
}

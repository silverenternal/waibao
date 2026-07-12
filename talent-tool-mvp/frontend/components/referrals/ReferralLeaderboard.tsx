"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchLeaderboard, type LeaderboardEntry } from "@/lib/api-referrals";

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

export interface ReferralLeaderboardProps {
  limit?: number;
  refreshMs?: number;
}

/**
 * 推荐积分排行榜 — 激励员工推荐.
 */
export function ReferralLeaderboard({ limit = 10, refreshMs = 30000 }: ReferralLeaderboardProps) {
  const [data, setData] = React.useState<LeaderboardEntry[]>([]);

  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetchLeaderboard(limit);
        if (!cancelled) setData(r.leaderboard);
      } catch (e) {
        console.error(e);
      }
    };
    load();
    const t = setInterval(load, refreshMs);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [limit, refreshMs]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>推荐达人榜 (Top {limit})</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <p className="text-sm text-slate-500">暂无数据</p>
        ) : (
          <ol className="space-y-2">
            {data.map((entry) => (
              <li
                key={entry.referrer_id}
                className="flex items-center justify-between text-sm"
              >
                <span className="flex items-center gap-2">
                  <span className="w-6 text-center text-lg">
                    {MEDAL[entry.rank] ?? `#${entry.rank}`}
                  </span>
                  <span className="text-slate-700">{entry.referrer_id}</span>
                </span>
                <span className="font-semibold text-amber-600">
                  {entry.total_points} 分
                </span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

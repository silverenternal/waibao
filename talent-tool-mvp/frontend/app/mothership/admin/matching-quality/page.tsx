"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { QualityDashboard } from "@/components/matching/QualityDashboard";
import { matchingQualityApi, type QualitySnapshot } from "@/lib/api-matching-quality";

export default function AdminMatchingQualityPage() {
  const [snapshot, setSnapshot] = React.useState<QualitySnapshot | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [sinceDays, setSinceDays] = React.useState(7);

  const load = React.useCallback(async (days: number) => {
    setLoading(true);
    setErr(null);
    try {
      const r = await matchingQualityApi.get(days);
      setSnapshot(r);
    } catch (e: any) {
      setErr(e?.message ?? "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load(sinceDays);
  }, [sinceDays, load]);

  return (
    <ErrorBoundary>(<div className="container mx-auto max-w-6xl p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">
              匹配质量仪表盘
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              precision / recall / F1 / 桶分布 / 漂移
            </p>
          </div>
          <div className="w-44">
            <Select
              value={String(sinceDays)}
              onValueChange={(v) => setSinceDays(Number(v))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">最近 7 天</SelectItem>
                <SelectItem value="30">最近 30 天</SelectItem>
                <SelectItem value="90">最近 90 天</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        {err && (
          <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {err}
          </div>
        )}
        {loading ? (
          <Skeleton className="h-96 w-full" />
        ) : snapshot ? (
          <QualityDashboard snapshot={snapshot} />
        ) : null}
      </div>)</ErrorBoundary>
  );
}
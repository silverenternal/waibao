"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MatchReason } from "@/components/match/MatchReason";
import { MatchWeakPoints } from "@/components/match/MatchWeakPoints";
import { MatchCounterfactual } from "@/components/match/MatchCounterfactual";
import {
  matchExplainApi,
  type MatchExplanation,
  type MatchCounterfactual as CF,
} from "@/lib/api-match-explain";

export default function MatchExplainPage() {
  const params = useParams<{ id: string }>();
  const matchId = params?.id ?? "";

  const [explain, setExplain] = React.useState<MatchExplanation | null>(null);
  const [cf, setCf] = React.useState<CF | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    if (!matchId) return;
    setLoading(true);
    setErr(null);
    try {
      const [exp, cfact] = await Promise.all([
        matchExplainApi.getExplain(matchId),
        matchExplainApi.getCounterfactual(matchId),
      ]);
      setExplain(exp);
      setCf(cfact);
    } catch (e: any) {
      setErr(e?.message ?? "加载失败");
    } finally {
      setLoading(false);
    }
  }, [matchId]);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="container mx-auto max-w-4xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            匹配解释
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            匹配 ID: <span className="font-mono">{matchId}</span>
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            重新生成
          </Button>
          <Link
            href={`/match/eval/${matchId}`}
            className="inline-flex items-center px-4 py-2 rounded-md bg-slate-900 text-white text-sm hover:bg-slate-800"
          >
            互评对照 →
          </Link>
        </div>
      </div>

      {err && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">为什么匹配</CardTitle>
            <Badge className="bg-emerald-100 text-emerald-800">reasons</Badge>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-4/5" />
              </div>
            ) : (
              <MatchReason reasons={explain?.reasons ?? []} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">为什么不匹配</CardTitle>
            <Badge className="bg-amber-100 text-amber-800">weak_points</Badge>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            ) : (
              <MatchWeakPoints weak_points={explain?.weak_points ?? []} />
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">反事实匹配</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-20 w-full" />
          ) : (
            <MatchCounterfactual
              if_have={cf?.if_have}
              score_lift={cf?.score_lift}
            />
          )}
        </CardContent>
      </Card>

      {explain?.model_version && (
        <p className="text-xs text-slate-400 text-right">
          model: {explain.model_version}
        </p>
      )}
    </div>
  );
}
"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { WeightTuner } from "@/components/matching/WeightTuner";
import { WeightHistoryChart } from "@/components/matching/WeightHistoryChart";
import { adminWeightsApi, type WeightsSnapshot } from "@/lib/api-admin-weights";

export default function AdminWeightsPage() {
  const [snap, setSnap] = React.useState<WeightsSnapshot | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [draftWeights, setDraftWeights] = React.useState<Record<string, number> | null>(null);
  const [recommendReason, setRecommendReason] = React.useState("");
  const [recommendLoading, setRecommendLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await adminWeightsApi.list();
      setSnap(r);
      setDraftWeights(r.current);
    } catch (e: any) {
      setErr(e?.message ?? "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const handleSave = async (w: Record<string, number>) => {
    setSaving(true);
    try {
      await adminWeightsApi.override(w, "admin manual override from dashboard");
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleRecommend = async () => {
    setRecommendLoading(true);
    setErr(null);
    try {
      const r = await adminWeightsApi.recommend(7);
      setRecommendReason(r.recommendation.reason);
      setDraftWeights(r.recommendation.new_weights);
    } catch (e: any) {
      setErr(e?.message ?? "生成建议失败");
    } finally {
      setRecommendLoading(false);
    }
  };

  const handleApplyRecommendation = async () => {
    if (!draftWeights) return;
    setSaving(true);
    try {
      await adminWeightsApi.apply(draftWeights, recommendReason || "applied recommendation");
      await load();
    } catch (e: any) {
      setErr(e?.message ?? "应用失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ErrorBoundary>(<div className="container mx-auto max-w-6xl p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">匹配权重管理</h1>
          <p className="text-sm text-slate-500 mt-1">
            查看当前权重、生成调整建议、人工覆盖。所有操作会写入 audit log。
          </p>
        </div>
        {err && (
          <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {err}
          </div>
        )}
        {loading ? (
          <Skeleton className="h-64 w-full" />
        ) : snap && draftWeights ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <WeightTuner
              weights={draftWeights}
              defaults={snap.defaults}
              onChange={(w) => setDraftWeights(w)}
              onSave={handleSave}
              saving={saving}
            />

            <Card>
              <CardHeader>
                <CardTitle className="text-base">建议生成</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button
                  variant="outline"
                  onClick={handleRecommend}
                  disabled={recommendLoading}
                >
                  {recommendLoading ? "分析中…" : "基于最近 7 天数据生成建议"}
                </Button>
                {recommendReason && (
                  <>
                    <Textarea
                      readOnly
                      value={recommendReason}
                      className="text-xs"
                      rows={4}
                    />
                    <Button onClick={handleApplyRecommendation} disabled={saving}>
                      应用建议
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        ) : null}
        {snap && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">权重历史</CardTitle>
            </CardHeader>
            <CardContent>
              <WeightHistoryChart history={snap.history} />
            </CardContent>
          </Card>
        )}
        {snap && snap.history.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">最近调整记录</CardTitle>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left border-b">
                    <th className="py-2 pr-3">时间</th>
                    <th className="py-2 pr-3">操作者</th>
                    <th className="py-2 pr-3">权重</th>
                    <th className="py-2">原因</th>
                  </tr>
                </thead>
                <tbody>
                  {snap.history.slice(0, 10).map((h, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 pr-3 text-slate-600">
                        {h.created_at
                          ? new Date(h.created_at).toLocaleString()
                          : "—"}
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">
                        {h.actor ?? "—"}
                      </td>
                      <td className="py-2 pr-3">
                        <div className="flex gap-1 flex-wrap">
                          {Object.entries(h.weights || {}).map(([k, v]) => (
                            <Badge key={k} variant="outline" className="text-xs">
                              {k}:{(Number(v) * 100).toFixed(0)}%
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td className="py-2 text-slate-700">{h.reason ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </div>)</ErrorBoundary>
  );
}
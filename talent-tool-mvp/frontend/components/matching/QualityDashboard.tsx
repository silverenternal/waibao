"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PrecisionRecallChart } from "./PrecisionRecallChart";
import { BucketDistributionChart } from "./BucketDistributionChart";
import { WeightHistoryChart } from "./WeightHistoryChart";
import type { QualitySnapshot } from "@/lib/api-matching-quality";

export interface QualityDashboardProps {
  snapshot: QualitySnapshot;
}

/**
 * 匹配质量仪表盘 — 顶部指标卡 + 三张图.
 */
export function QualityDashboard({ snapshot }: QualityDashboardProps) {
  const s = snapshot.summary;
  const drift = s.drift ?? 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricTile label="Precision" value={s.precision} />
        <MetricTile label="Recall" value={s.recall} />
        <MetricTile label="F1" value={s.f1} highlight />
        <Card>
          <CardContent className="pt-6">
            <div className="text-xs text-slate-500 mb-1">F1 漂移</div>
            <div
              className={`text-2xl font-mono ${
                drift > 0
                  ? "text-emerald-700"
                  : drift < 0
                  ? "text-rose-700"
                  : "text-slate-700"
              }`}
            >
              {drift > 0 ? "+" : ""}
              {(drift * 100).toFixed(2)}%
            </div>
            <div className="text-xs text-slate-400 mt-1">vs 上一次</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Precision / Recall / F1 趋势</CardTitle>
        </CardHeader>
        <CardContent>
          <PrecisionRecallChart history={snapshot.history} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">桶分布转化率</CardTitle>
        </CardHeader>
        <CardContent>
          <BucketDistributionChart distribution={snapshot.bucket_distribution} />
        </CardContent>
      </Card>

      {Object.keys(snapshot.segment_metrics || {}).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Segment 指标 (按 role_seniority)</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="py-2 pr-3">Segment</th>
                  <th className="py-2 pr-3">样本数</th>
                  <th className="py-2 pr-3">Precision</th>
                  <th className="py-2 pr-3">Recall</th>
                  <th className="py-2">F1</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(snapshot.segment_metrics).map(([seg, m]) => (
                  <tr key={seg} className="border-b last:border-0">
                    <td className="py-2 pr-3">
                      <Badge variant="outline">{seg}</Badge>
                    </td>
                    <td className="py-2 pr-3 font-mono">{m.count}</td>
                    <td className="py-2 pr-3 font-mono">
                      {(m.precision * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 pr-3 font-mono">
                      {(m.recall * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 font-mono">{(m.f1 * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-slate-400 text-right">
        生成时间: {new Date(snapshot.generated_at).toLocaleString()} · 样本: {s.total} ·
        时间窗: 最近 {snapshot.since_days} 天
      </p>
    </div>
  );
}

function MetricTile({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <Card className={highlight ? "border-indigo-300 bg-indigo-50/30" : ""}>
      <CardContent className="pt-6">
        <div className="text-xs text-slate-500 mb-1">{label}</div>
        <div className="text-2xl font-mono text-slate-900">
          {(value * 100).toFixed(1)}%
        </div>
      </CardContent>
    </Card>
  );
}

export { WeightHistoryChart };
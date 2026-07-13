"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

interface HitRateReport {
  by_role: Record<string, Record<string, number>>;
  totals: Record<string, number>;
  conversion_rates: Record<string, number>;
  weak_stages: string[];
  insights: string[];
}

const STAGE_LABEL: Record<string, string> = {
  recommended: "推荐",
  contacted: "联系",
  interview: "面试",
  offer: "Offer",
  hired: "入职",
};

export function HitRateChart() {
  const [report, setReport] = useState<HitRateReport | null>(null);

  const load = async () => {
    const r = await fetch("/api/v8_1_p2/matching-feedback/hit-rate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        events: [
          ...Array.from({ length: 100 }, () => ({ role_id: "r1", candidate_id: "c", stage: "recommended" })),
          ...Array.from({ length: 30 }, () => ({ role_id: "r1", candidate_id: "c", stage: "contacted" })),
          ...Array.from({ length: 8 }, () => ({ role_id: "r1", candidate_id: "c", stage: "interview" })),
          ...Array.from({ length: 3 }, () => ({ role_id: "r1", candidate_id: "c", stage: "offer" })),
          ...Array.from({ length: 2 }, () => ({ role_id: "r1", candidate_id: "c", stage: "hired" })),
        ],
      }),
    });
    if (r.ok) setReport(await r.json());
  };

  return (
    <Card className="w-full">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>命中率 · Hit Rate</CardTitle>
        <Button variant="outline" size="sm" onClick={load}>加载示例</Button>
      </CardHeader>
      <CardContent>
        {report && (
          <div className="space-y-4">
            <div className="space-y-2">
              {(["recommended", "contacted", "interview", "offer", "hired"] as const).map(stage => {
                const total = report.totals[stage] || 0;
                return (
                  <div key={stage}>
                    <div className="flex justify-between text-xs">
                      <span>{STAGE_LABEL[stage]}</span>
                      <span className="font-mono">{total}</span>
                    </div>
                    <Progress value={Math.min(100, total)} className="h-2" />
                  </div>
                );
              })}
            </div>

            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground">转化率</div>
              {Object.entries(report.conversion_rates).map(([k, v]) => (
                <div key={k} className="flex justify-between text-sm">
                  <span>{k.replace("->", " → ")}</span>
                  <Badge variant={report.weak_stages.includes(k) ? "destructive" : "outline"}>
                    {((v as number) * 100).toFixed(1)}%
                  </Badge>
                </div>
              ))}
            </div>

            {report.insights.length > 0 && (
              <div className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground">洞察</div>
                {report.insights.map((s, i) => (
                  <div key={i} className="text-sm bg-blue-50 p-2 rounded">{s}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default HitRateChart;

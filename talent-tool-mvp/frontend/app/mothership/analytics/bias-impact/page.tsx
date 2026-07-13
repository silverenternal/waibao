"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface BiasImpact {
  total_jds: number;
  affected_jds: number;
  affected_rate_pct: number;
  department_breakdown: Record<string, number>;
  quarter_breakdown: Record<string, number>;
  narrative: string;
  recommendations: string[];
}

export default function BiasImpactPage() {
  const [report, setReport] = useState<BiasImpact | null>(null);

  const loadDemo = async () => {
    const r = await fetch("/api/v8_1_p2/bias/impact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        historic_jds: [
          { department: "技术", quarter: "Q1",
            bias_report: { hits: [{ category: "age" }] } },
          { department: "技术", quarter: "Q1",
            bias_report: { hits: [{ category: "gender" }] } },
          { department: "市场", quarter: "Q2",
            bias_report: { hits: [{ category: "region" }] } },
          { department: "运营", quarter: "Q1",
            bias_report: { hits: [] } },
        ],
        months: 3,
      }),
    });
    if (r.ok) setReport(await r.json());
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header className="flex justify-between items-end">
        <div>
          <h1 className="text-2xl font-semibold">偏见影响 · Bias Impact</h1>
          <p className="text-sm text-muted-foreground">
            v8.1 T3704: 通过 3 个月历史数据评估偏见对招聘效果的影响
          </p>
        </div>
        <Button onClick={loadDemo}>加载示例</Button>
      </header>

      {report && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">总 JD</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-semibold">{report.total_jds}</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">受影响</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-semibold text-amber-600">
              {report.affected_jds}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">命中率</CardTitle>
            </CardHeader>
            <CardContent className="text-3xl font-semibold text-red-600">
              {report.affected_rate_pct}%
            </CardContent>
          </Card>

          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>分析</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">{report.narrative}</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>部门分布</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {Object.entries(report.department_breakdown).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span>{k}</span> <Badge variant="outline">{v}</Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

interface ConsensusReport {
  overall: number;
  level: string;
  conflicting_dimensions: string[];
  compromise_plan: any;
  can_decide: boolean;
  dimensions: Array<{
    dimension: string;
    score: number;
    variance: number;
    conflicting: boolean;
    notes: string[];
  }>;
}

const LEVEL_VARIANT: Record<string, "default" | "secondary" | "outline" | "destructive"> = {
  strong: "default",
  weak: "secondary",
  fuzzy: "destructive",
};

export function ConsensusChart() {
  const [salary, setSalary] = useState("0.85, 0.9, 0.8, 0.92");
  const [level, setLevel] = useState("0.6, 0.6, 0.65");
  const [timeline, setTimeline] = useState("0.9, 0.2, 0.5");
  const [report, setReport] = useState<ConsensusReport | null>(null);
  const [loading, setLoading] = useState(false);

  const parseList = (s: string) => s.split(",").map(x => parseFloat(x.trim())).filter(x => !Number.isNaN(x));

  const run = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/consensus-v2/compute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dimension_ratings: {
            salary: parseList(salary),
            level: parseList(level),
            timeline: parseList(timeline),
          },
        }),
      });
      if (r.ok) setReport(await r.json());
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>共识度 · Consensus Score</CardTitle>
        <p className="text-sm text-muted-foreground">v8.1 T3708: 3 级共识 + 冲突可视化</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2">
          <div>
            <label className="text-xs">salary (薪资评分 0-1)</label>
            <input className="w-full border rounded px-2 py-1 text-sm" value={salary} onChange={(e) => setSalary(e.target.value)} />
          </div>
          <div>
            <label className="text-xs">level (职级评分)</label>
            <input className="w-full border rounded px-2 py-1 text-sm" value={level} onChange={(e) => setLevel(e.target.value)} />
          </div>
          <div>
            <label className="text-xs">timeline (时间评分)</label>
            <input className="w-full border rounded px-2 py-1 text-sm" value={timeline} onChange={(e) => setTimeline(e.target.value)} />
          </div>
        </div>
        <Button disabled={loading} onClick={run}>计算</Button>

        {report && (
          <div className="space-y-3 rounded border p-3">
            <div className="flex items-center justify-between">
              <Badge variant={LEVEL_VARIANT[report.level]}>
                {report.level} · {report.overall}
              </Badge>
              <span className="text-xs text-muted-foreground">
                可自动决策: {report.can_decide ? "是" : "否"}
              </span>
            </div>

            <div className="space-y-2">
              {report.dimensions.map((d, i) => (
                <div key={i}>
                  <div className="flex justify-between text-xs">
                    <span>{d.dimension}</span>
                    <span>{d.conflicting && "⚠️ "}{d.score.toFixed(2)} (var={d.variance.toFixed(3)})</span>
                  </div>
                  <Progress value={d.score * 100} />
                </div>
              ))}
            </div>

            {report.compromise_plan && (
              <div className="rounded bg-amber-50 p-3 text-xs">
                <div className="font-medium mb-1">{report.compromise_plan.title}</div>
                <div>{report.compromise_plan.suggested}</div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ConsensusChart;

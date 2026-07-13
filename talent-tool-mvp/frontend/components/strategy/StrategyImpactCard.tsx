"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

interface ImpactItem {
  type: string;
  title: string;
  affected_skills: string[];
  estimated_count: number | null;
  detail: string;
  priority: string;
}

interface ImpactReport {
  items: ImpactItem[];
  summary: string;
  auto_notify_targets: string[];
  raw_signals: Record<string, string[]>;
}

const PRIORITY_COLOR: Record<string, string> = {
  high: "destructive",
  medium: "default",
  low: "outline",
};

export function StrategyImpactCard() {
  const [content, setContent] = useState(
    "Q4 我们将重点国际化扩张,招聘 5 个英语人才,关停 A 业务,开拓海外市场。",
  );
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [loading, setLoading] = useState(false);

  const analyze = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/strategy/impact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (r.ok) setReport(await r.json());
    } finally {
      setLoading(false);
    }
  };

  const publish = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/strategy/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (r.ok) setReport((await r.json()) as any);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>战略影响分析 · Strategy Impact</CardTitle>
        <p className="text-sm text-muted-foreground">v8.1 T3703: 战略更新 → 招聘 / 关停 / 通知</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea rows={5} value={content} onChange={(e) => setContent(e.target.value)} />
        <div className="flex gap-2">
          <Button onClick={analyze} disabled={loading}>分析</Button>
          <Button variant="secondary" onClick={publish} disabled={loading}>发布 + 通知</Button>
        </div>

        {report && (
          <div className="space-y-3 rounded border p-3">
            <p className="text-sm">{report.summary}</p>
            {report.auto_notify_targets.length > 0 && (
              <div className="flex gap-2 flex-wrap">
                {report.auto_notify_targets.map((t, i) => (
                  <Badge key={i} variant="outline">notify: {t}</Badge>
                ))}
              </div>
            )}
            <div className="space-y-2">
              {report.items.map((it, i) => (
                <div key={i} className="border-l-2 pl-2 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant={PRIORITY_COLOR[it.priority] as any}>
                      {it.priority}
                    </Badge>
                    <span className="font-medium">{it.title}</span>
                  </div>
                  <p className="text-muted-foreground text-xs mt-1">{it.detail}</p>
                  {it.affected_skills.length > 0 && (
                    <div className="mt-1 flex gap-1 flex-wrap">
                      {it.affected_skills.map((s, j) => (
                        <Badge key={j} variant="outline">{s}</Badge>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default StrategyImpactCard;

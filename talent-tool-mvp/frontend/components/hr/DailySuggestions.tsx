"use client";

import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface Suggestion {
  category: string;
  title: string;
  reason: string;
  priority: number;
  action_type: string;
  payload: Record<string, any>;
}

export function DailySuggestions() {
  const [sugs, setSugs] = useState<Suggestion[]>([]);
  const [breakdown, setBreakdown] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [executed, setExecuted] = useState<string[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/daily-suggestions/today", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pending_offers: [
            { candidate_name: "Alice", days_waiting: 5, candidate_id: "c1", role: "前端" },
            { candidate_name: "Bob", days_waiting: 1, candidate_id: "c2", role: "后端" },
          ],
          pending_interviews: [
            { candidate_name: "Cara", scheduled_at: new Date(Date.now() + 3600 * 1000).toISOString(),
              candidate_id: "c3" },
          ],
          open_tickets: [
            { id: "T-101", age_hours: 60 },
            { id: "T-102", age_hours: 5 },
          ],
          waiting_candidates: [
            { name: "Dora", id: "c4", days_waiting: 7 },
          ],
          stale_jds: [
            { title: "产品经理", age_days: 14, id: "r1" },
          ],
        }),
      });
      if (r.ok) {
        const d = await r.json();
        setSugs(d.suggestions);
        setBreakdown(d.priority_breakdown);
      }
    } finally {
      setLoading(false);
    }
  };

  const execute = async (s: Suggestion) => {
    const r = await fetch("/api/v8_1_p2/daily-suggestions/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_type: s.action_type, payload: s.payload }),
    });
    if (r.ok) setExecuted([...executed, `${s.category}-${s.title}`]);
  };

  useEffect(() => { load(); }, []);

  const PRIORITY_LABEL = ["", "紧急", "高", "中", "低", "很低"];

  return (
    <Card className="w-full">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>今日 HR 建议</CardTitle>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>刷新</Button>
      </CardHeader>
      <CardContent>
        {sugs.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无建议,先去忙吧 ☕</p>
        ) : (
          <>
            <div className="flex gap-2 text-xs mb-3">
              {Object.entries(breakdown).map(([k, v]) => (
                <Badge key={k} variant="outline">P{k}: {v}</Badge>
              ))}
            </div>
            <div className="space-y-2">
              {sugs.map((s, i) => {
                const key = `${s.category}-${s.title}`;
                const done = executed.includes(key);
                return (
                  <div key={i} className="flex items-center justify-between border rounded p-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <Badge variant={s.priority <= 2 ? "destructive" : "secondary"}>
                          P{s.priority} {PRIORITY_LABEL[s.priority]}
                        </Badge>
                        <span className="text-sm font-medium">{s.title}</span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">{s.reason}</p>
                    </div>
                    <Button size="sm" variant={done ? "outline" : "default"} disabled={done} onClick={() => execute(s)}>
                      {done ? "已执行" : "一键执行"}
                    </Button>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default DailySuggestions;

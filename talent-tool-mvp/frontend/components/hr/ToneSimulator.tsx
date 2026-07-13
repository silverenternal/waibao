"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Tone = "formal" | "casual" | "data_driven" | "relationship_driven";

const TONE_OPTIONS: { value: Tone; label: string; emoji: string }[] = [
  { value: "formal", label: "正式得体", emoji: "📜" },
  { value: "casual", label: "亲切口语", emoji: "😊" },
  { value: "data_driven", label: "数据驱动", emoji: "📊" },
  { value: "relationship_driven", label: "关系维护", emoji: "💞" },
];

interface ToneProfile {
  primary_tone: Tone;
  tone_scores: Record<Tone, number>;
  sample_count: number;
}

export function ToneSimulator({ userId, history }: { userId?: string; history?: string[] }) {
  const [scene, setScene] = useState("您对这个 offer 还满意吗?有没有需要讨论的部分");
  const [manualTone, setManualTone] = useState<Tone | "auto">("auto");
  const [profile, setProfile] = useState<ToneProfile | null>(null);
  const [result, setResult] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const aggregate = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/tone/aggregate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId || "demo-user",
          history: history || ["请您按时提交周报。", "请关注转化率指标。"],
          manual_override: manualTone === "auto" ? null : manualTone,
        }),
      });
      if (r.ok) {
        const data = await r.json();
        setProfile(data);
      }
    } finally {
      setLoading(false);
    }
  };

  const rewrite = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/tone/rewrite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template: scene,
          user_id: userId || "demo-user",
          history: history || [],
          manual_override: manualTone === "auto" ? null : manualTone,
        }),
      });
      if (r.ok) {
        const data = await r.json();
        setResult(data.result || "");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>语气模拟器 · Tone Simulator</CardTitle>
        <p className="text-sm text-muted-foreground">
          输入场景文本,系统将按老板历史语气重写。
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">手动覆盖语气</label>
            <Select value={manualTone} onValueChange={(v) => setManualTone(v as Tone | "auto")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">自动 (按历史)</SelectItem>
                {TONE_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.emoji} {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end gap-2">
            <Button onClick={aggregate} disabled={loading} className="flex-1">
              学习画像
            </Button>
            <Button variant="secondary" onClick={rewrite} disabled={loading} className="flex-1">
              去模板化
            </Button>
          </div>
        </div>

        <div>
          <label className="text-xs text-muted-foreground">场景 / 模板</label>
          <Textarea
            rows={3}
            value={scene}
            onChange={(e) => setScene(e.target.value)}
            placeholder="例: 请按时来面试。"
          />
        </div>

        {profile && (
          <div className="rounded border p-3 space-y-2">
            <div className="flex flex-wrap gap-2">
              <Badge variant="default">主语气: {profile.primary_tone}</Badge>
              <Badge variant="outline">样本 {profile.sample_count}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {Object.entries(profile.tone_scores).map(([t, s]) => (
                <div key={t} className="flex justify-between">
                  <span className="text-muted-foreground">{t}</span>
                  <span className="font-mono">{((s as number) * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {result && (
          <div className="rounded border bg-muted p-3">
            <div className="text-xs text-muted-foreground mb-1">改写后</div>
            <pre className="whitespace-pre-wrap text-sm font-sans">{result}</pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ToneSimulator;

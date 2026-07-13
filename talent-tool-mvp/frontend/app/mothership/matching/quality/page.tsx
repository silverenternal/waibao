"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import React, { useState } from "react";

const HitRateChart = dynamic(() => import("@/components/matching/HitRateChart").then(m => m.HitRateChart), { ssr: false });

export default function MatchingQualityPage() {
  const [feedbackResult, setFeedbackResult] = useState<string>("");
  const [candidateId, setCandidateId] = useState("c-1");
  const [roleId, setRoleId] = useState("r-1");
  const [label, setLabel] = useState<"suitable" | "unsuitable">("suitable");
  const [rating, setRating] = useState(5);
  const [note, setNote] = useState("");

  const submitFeedback = async () => {
    const r = await fetch("/api/v8_1_p2/matching-feedback/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        candidate_id: candidateId,
        role_id: roleId,
        label,
        rating,
        note,
      }),
    });
    if (r.ok) {
      const d = await r.json();
      setFeedbackResult(JSON.stringify(d.feedback, null, 2));
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">匹配质量 · Matching Quality</h1>
        <p className="text-sm text-muted-foreground mt-1">
          v8.1 T3710: 命中率分析 + HR 反馈循环 → 自动调整模型权重
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <HitRateChart />
        <Card>
          <CardHeader>
            <CardTitle>HR 反馈</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs">候选人 ID</label>
                <Input value={candidateId} onChange={(e) => setCandidateId(e.target.value)} />
              </div>
              <div>
                <label className="text-xs">岗位 ID</label>
                <Input value={roleId} onChange={(e) => setRoleId(e.target.value)} />
              </div>
              <div>
                <label className="text-xs">标签</label>
                <select
                  className="w-full border rounded px-2 py-1 text-sm"
                  value={label}
                  onChange={(e) => setLabel(e.target.value as any)}
                >
                  <option value="suitable">合适</option>
                  <option value="unsuitable">不合适</option>
                </select>
              </div>
              <div>
                <label className="text-xs">评分 (1-5)</label>
                <Input
                  type="number"
                  min={1}
                  max={5}
                  value={rating}
                  onChange={(e) => setRating(Number(e.target.value))}
                />
              </div>
            </div>
            <div>
              <label className="text-xs">备注</label>
              <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            <Button onClick={submitFeedback}>提交反馈</Button>
            {feedbackResult && (
              <pre className="text-xs bg-muted p-2 rounded overflow-auto">{feedbackResult}</pre>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>反馈 → 模型权重调整</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          <p>· 收到反馈后,系统汇总 suitable / unsuitable 比例;</p>
          <p>· 若不合适 &gt; 合适,模型权重自动偏向「技能匹配 +5%,经验 −5%」;</p>
          <p>· 每条反馈都会进入下次的匹配打分,长期自进化。</p>
          <div className="mt-2 flex gap-2">
            <Badge variant="outline">skill_match = +0.05</Badge>
            <Badge variant="outline">experience = −0.05</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

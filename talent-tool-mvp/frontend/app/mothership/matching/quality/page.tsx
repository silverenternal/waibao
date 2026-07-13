"use client";

/**
 * Matching Quality Dashboard — v8.1 T3710.
 *
 * Combines 4 panels:
 *   1. Hit-rate Chart (per stage)              ← HitRateChart
 *   2. Quality Dashboard (precision / NDCG)    ← QualityDashboard
 *   3. HR Feedback form → model adjustment
 *   4. Weight tuner + history                  ← WeightTuner / WeightHistoryChart
 *
 * Built on existing shared components.
 */

import * as React from "react";
import dynamic from "next/dynamic";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const HitRateChart = dynamic(
  () => import("@/components/matching/HitRateChart").then((m) => m.HitRateChart),
  { ssr: false },
);
const PrecisionRecallChart = dynamic(
  () => import("@/components/matching/PrecisionRecallChart").then((m) => m.PrecisionRecallChart),
  { ssr: false },
);
const WeightTuner = dynamic(
  () => import("@/components/matching/WeightTuner").then((m) => m.WeightTuner),
  { ssr: false },
);
const WeightHistoryChart = dynamic(
  () => import("@/components/matching/WeightHistoryChart").then((m) => m.WeightHistoryChart),
  { ssr: false },
);
const QualityDashboard = dynamic(
  () => import("@/components/matching/QualityDashboard").then((m) => m.QualityDashboard),
  { ssr: false },
);
const BucketDistributionChart = dynamic(
  () => import("@/components/matching/BucketDistributionChart").then((m) => m.BucketDistributionChart),
  { ssr: false },
);

export default function MatchingQualityPage() {
  const [candidateId, setCandidateId] = React.useState("c-1");
  const [roleId, setRoleId] = React.useState("r-1");
  const [label, setLabel] = React.useState<"suitable" | "unsuitable">("suitable");
  const [rating, setRating] = React.useState(5);
  const [note, setNote] = React.useState("");
  const [feedbackResult, setFeedbackResult] = React.useState<string>("");

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
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            匹配质量 · Matching Quality
          </h1>
          <Badge variant="secondary">v8.1 T3710</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          命中率分析 + HR 反馈循环 → 自动调整模型权重
        </p>
      </header>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">总览</TabsTrigger>
          <TabsTrigger value="feedback">反馈</TabsTrigger>
          <TabsTrigger value="weights">权重调优</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <HitRateChart />
            </div>
            <QualityDashboard
              snapshot={{
                summary: { precision: 0.74, recall: 0.62, f1: 0.68, total_evaluations: 240, period_days: 7 },
                bucket_distribution: {},
                segment_metrics: {},
                history: [],
              } as any}
            />
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <PrecisionRecallChart history={[]} />
            <BucketDistributionChart distribution={{}} />
          </div>
        </TabsContent>

        <TabsContent value="feedback" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>HR 反馈 · Feedback</CardTitle>
              <p className="text-xs text-muted-foreground">
                提交后系统会再学习并自动调整权重。
              </p>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
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
                    className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                    value={label}
                    onChange={(e) => setLabel(e.target.value as "suitable" | "unsuitable")}
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
                <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              </div>
              <Button onClick={submitFeedback}>提交反馈</Button>
              {feedbackResult && (
                <pre className="overflow-auto rounded bg-muted p-3 text-xs">
                  {feedbackResult}
                </pre>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>反馈 → 模型权重调整</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm text-muted-foreground">
              <p>· 收到反馈后,系统汇总 suitable / unsuitable 比例;</p>
              <p>· 若不合适 &gt; 合适,模型权重自动偏向「技能匹配 +5%,经验 −5%」;</p>
              <p>· 每条反馈都会进入下次的匹配打分,长期自进化。</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant="outline">skill_match = +0.05</Badge>
                <Badge variant="outline">experience = −0.05</Badge>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="weights" className="space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>实时权重调优</CardTitle>
              </CardHeader>
              <CardContent>
                <WeightTuner weights={{ skill_match: 0.4, semantic: 0.35, experience: 0.25 }} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>权重历史</CardTitle>
              </CardHeader>
              <CardContent>
                <WeightHistoryChart history={[]} />
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

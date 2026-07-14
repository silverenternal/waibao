"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ReviewForm } from "@/components/probation/ReviewForm";
import { ProbationTimeline } from "@/components/probation/ProbationTimeline";

/**
 * 单个员工的试用期评估页.
 */
export default function ProbationDetailPage() {
  const params = useParams<{ id: string }>();
  const employeeId = params?.id ?? "demo";
  const [stage, setStage] = React.useState<"30" | "90" | "180" | "final">("90");

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 space-y-6">
        <h1 className="text-2xl font-bold">员工 {employeeId} · 试用期</h1>
        <div className="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>评估阶段</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                {(["30", "90", "180", "final"] as const).map((s) => (
                  <button
                    key={s}
                    className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                      stage === s
                        ? "bg-blue-500 text-white"
                        : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                    onClick={() => setStage(s)}
                  >
                    {s === "final" ? "转正" : `D+${s}`}
                  </button>
                ))}
              </div>
              <ReviewForm
                employeeId={employeeId}
                orgId="demo-org"
                reviewStage={stage}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>试用期时间轴</CardTitle>
            </CardHeader>
            <CardContent>
              <ProbationTimeline
                hireDate="2026-04-01"
                tasks={[
                  {
                    id: "1",
                    type: "orientation",
                    title: "入职引导",
                    description: "完成入职引导",
                    due_at: "2026-04-01T00:00:00+00:00",
                    completed_at: "2026-04-01T10:00:00+00:00",
                  },
                ]}
              />
            </CardContent>
          </Card>
        </div>
      </div>)</ErrorBoundary>
  );
}

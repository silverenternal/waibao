"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const DailySuggestions = dynamic(() => import("@/components/hr/DailySuggestions").then(m => m.DailySuggestions), { ssr: false });

export default function HRSuggestionsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">今日 HR 建议 · Daily Suggestions</h1>
        <p className="text-sm text-muted-foreground mt-1">
          v8.1 T3709: 早 9 点系统扫所有未处理事项,主动生成建议并一键执行。
        </p>
      </header>

      <DailySuggestions />

      <Card>
        <CardHeader>
          <CardTitle>触发逻辑</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-1">
          <p>· offer 已等 ≥3 天 → P1 紧急</p>
          <p>· 面试 ≤24h 未提醒 → P1 紧急</p>
          <p>· 工单 ≥48h → P1 紧急</p>
          <p>· 候选人等待 ≥7 天无回应 → P4 关怀</p>
          <p>· JD ≥14 天未优化 → P5 复审</p>
        </CardContent>
      </Card>
    </div>
  );
}

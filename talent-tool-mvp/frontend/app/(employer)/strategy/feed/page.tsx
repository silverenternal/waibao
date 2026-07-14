"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const StrategyImpactCard = dynamic(() => import("@/components/strategy/StrategyImpactCard").then(m => m.StrategyImpactCard), { ssr: false });

export default function StrategyFeedPage() {
  return (
    <ErrorBoundary>(<div className="mx-auto max-w-3xl space-y-6 p-6">
        <header>
          <h1 className="text-2xl font-semibold">战略 Feed</h1>
          <p className="text-sm text-muted-foreground mt-1">
            v8.1 T3703: 战略一经发布,自动识别招聘/关停影响并通知关键人。
          </p>
        </header>
        <StrategyImpactCard />
        <Card>
          <CardHeader>
            <CardTitle>已发布战略</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="border-b pb-2">
              <div className="font-medium">Q4 国际化扩张</div>
              <div className="text-muted-foreground text-xs">识别: 招聘 5 英语人才,关停 A 业务</div>
            </div>
            <div className="border-b pb-2">
              <div className="font-medium">Q3 AI 全面升级</div>
              <div className="text-muted-foreground text-xs">识别: 招聘 3 AI/算法</div>
            </div>
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}

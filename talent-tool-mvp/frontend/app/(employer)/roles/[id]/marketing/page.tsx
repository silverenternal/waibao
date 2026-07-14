"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const JDScorer = dynamic(() => import("@/components/jd/JDScorer").then(m => m.JDScorer), { ssr: false });

export default function RoleMarketingPage({ params }: { params: { id: string } }) {
  return (
    <ErrorBoundary>(<div className="mx-auto max-w-4xl space-y-6 p-6">
        <header>
          <h1 className="text-2xl font-semibold">岗位营销化 · Role #{params.id}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            v8.1 T3705: 故事化描述、SEO、A/B 测试、4 维评分
          </p>
        </header>
        <JDScorer />
        <Card>
          <CardHeader>
            <CardTitle>营销技巧 Tips</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>· 用「我们正在构建 X,改变 Y」开篇</p>
            <p>· 团队氛围真实呈现,避免套话</p>
            <p>· 标题变体做 A/B 投放,看投递率</p>
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}

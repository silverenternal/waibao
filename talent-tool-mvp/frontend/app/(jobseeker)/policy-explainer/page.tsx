"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const PolicyExplainer = dynamic(() => import("@/components/policy/PolicyExplainer").then(m => m.PolicyExplainer), { ssr: false });

export default function PolicyExplainerPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">制度 AI 解释</h1>
        <p className="text-sm text-muted-foreground mt-1">
          v8.1 T3706: 把公司制度/法规翻译成「人话」,有任何不清楚的直接问。
        </p>
      </header>

      <PolicyExplainer />

      <Card>
        <CardHeader>
          <CardTitle>常见制度入口</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 text-sm">
          <button className="text-left p-2 border rounded">试用期</button>
          <button className="text-left p-2 border rounded">离职流程</button>
          <button className="text-left p-2 border rounded">加班调休</button>
          <button className="text-left p-2 border rounded">病假/事假</button>
        </CardContent>
      </Card>
    </div>
  );
}

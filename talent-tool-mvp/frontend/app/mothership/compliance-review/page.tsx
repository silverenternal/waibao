"use client";

import dynamic from "next/dynamic";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const VerificationScore = dynamic(() => import("@/components/compliance/VerificationScore").then(m => m.VerificationScore), { ssr: false });

export default function ComplianceReviewPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">合规复审 · Compliance Review</h1>
        <p className="text-sm text-muted-foreground mt-1">
          v8.1 T3702: 假资质 AI 检测 → 自动转人工
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <VerificationScore target="营业执照.png" />
        <Card>
          <CardHeader>
            <CardTitle>人工复审队列</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between border-b pb-2">
              <span>公司 A · 营业执照</span>
              <Badge variant="destructive">高风险 92</Badge>
            </div>
            <div className="flex justify-between border-b pb-2">
              <span>公司 B · 资质证书</span>
              <Badge variant="secondary">复核 78</Badge>
            </div>
            <div className="flex justify-between">
              <span>公司 C · 信用代码</span>
              <Badge variant="outline">通过</Badge>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

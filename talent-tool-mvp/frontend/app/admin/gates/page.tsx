"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { FeatureGateShowcase } from "@/components/FeatureGateExamples";

export default function GatesPage(): React.ReactElement {
  return (
    <ErrorBoundary>(<main className="container mx-auto py-8">
        <h1 className="text-2xl font-bold">Feature Gate 控制中心</h1>
        <p className="mb-6 text-sm text-slate-600">
          服务开关就绪态 UI 预览。所有按钮、状态卡、CTA 跟随
          <code className="mx-1">/api/admin/services/*</code>
          实时刷新。
        </p>
        <FeatureGateShowcase />
      </main>)</ErrorBoundary>
  );
}

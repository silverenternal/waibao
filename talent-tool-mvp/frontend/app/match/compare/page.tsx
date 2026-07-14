import { ErrorBoundary } from "@/components/ErrorBoundary";
/**
 * T2301 — 候选人对比页面
 */

import { Suspense } from "react";
import { CandidateCompareView } from "./CandidateCompareView";

export const metadata = {
  title: "候选人对比 · RecruitTech",
};

export default function CandidateComparePage() {
  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 max-w-7xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">候选人对比</h1>
          <p className="text-sm text-muted-foreground mt-1">
            选择 2-5 个候选人,自动按 5 维度 (技能/经验/教育/文化/潜力) 对齐,高亮差异最大的 3 个维度.
          </p>
        </div>
        <Suspense fallback={<div className="text-sm text-muted-foreground">加载中...</div>}>
          <CandidateCompareView />
        </Suspense>
      </div>)</ErrorBoundary>
  );
}
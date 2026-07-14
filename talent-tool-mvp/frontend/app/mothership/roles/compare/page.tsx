import { ErrorBoundary } from "@/components/ErrorBoundary";
/**
 * T2301 — 岗位对比页面
 */

import { Suspense } from "react";
import { RoleCompareView } from "./RoleCompareView";

export const metadata = {
  title: "岗位对比 · RecruitTech Mothership",
};

export default function RoleComparePage() {
  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 max-w-7xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">岗位对比</h1>
          <p className="text-sm text-muted-foreground mt-1">
            选择 2-5 个岗位,自动按 5 维度对齐,展示技能广度 / 经验要求 / 教育 / 文化 / 潜力 差异.
          </p>
        </div>
        <Suspense fallback={<div className="text-sm text-muted-foreground">加载中...</div>}>
          <RoleCompareView />
        </Suspense>
      </div>)</ErrorBoundary>
  );
}
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { generatePageMetadata } from "@/lib/metadata";
import { RecruitmentKanbanClient } from "./_client";
import type { Metadata } from "next";

export const metadata: Metadata = generatePageMetadata({
  title: "招聘流程看板 — 联系记录 + 面试安排",
  description:
    "招聘流程看板：按候选人聚合联系记录与面试安排，三列流转（联系 → 面试 → 结果）。可记录每次联系（电话/邮件/微信…）、安排面试（日期/时间/地点/形式）并更新面试状态。",
  path: "/marketplace/recruitment",
});

export default function RecruitmentPage() {
  return (
    <ErrorBoundary>
      <RecruitmentKanbanClient />
    </ErrorBoundary>
  );
}

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { generatePageMetadata } from "@/lib/metadata";
import { JobsPoolClient } from "./_client";
import type { Metadata } from "next";

export const metadata: Metadata = generatePageMetadata({
  title: "岗位池 — 浏览在招岗位",
  description:
    "招聘市场岗位池：卡片浏览在招岗位（公司+职位+薪资+城市+技能要求），支持按职位/城市/薪资筛选与关键词搜索。求职者可见完整岗位卡（职责+条件+边界）。",
  path: "/marketplace/jobs",
});

export default function JobsPoolPage() {
  return (
    <ErrorBoundary>
      <JobsPoolClient />
    </ErrorBoundary>
  );
}

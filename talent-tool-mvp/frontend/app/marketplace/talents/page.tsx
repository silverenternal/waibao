import { ErrorBoundary } from "@/components/ErrorBoundary";
import { generatePageMetadata } from "@/lib/metadata";
import { TalentsPoolClient } from "./_client";
import type { Metadata } from "next";

export const metadata: Metadata = generatePageMetadata({
  title: "人才池 — 浏览在线人才",
  description:
    "招聘市场人才池：卡片浏览人才画像（头像+姓名+职位+技能标签+匹配度），支持按职位/技能/城市/薪资/学历筛选与关键词搜索。企业可查看完整简历与联系方式。",
  path: "/marketplace/talents",
});

export default function TalentsPoolPage() {
  return (
    <ErrorBoundary>
      <TalentsPoolClient />
    </ErrorBoundary>
  );
}

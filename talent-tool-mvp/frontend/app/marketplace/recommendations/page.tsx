import { ErrorBoundary } from "@/components/ErrorBoundary";
import { generatePageMetadata } from "@/lib/metadata";
import { RecommendationsClient } from "./_client";
import type { Metadata } from "next";

export const metadata: Metadata = generatePageMetadata({
  title: "推荐中心 — 企业收到的候选人推荐",
  description:
    "匹配成功后推送给企业的候选人推荐：匹配分数 + 匹配理由 + 能力缺口 + 风险提示 + 完整简历 + 联系方式。企业可查看、接受、拒绝；简历下载导出权限仅平台管理员。",
  path: "/marketplace/recommendations",
});

export default function RecommendationsPage() {
  return (
    <ErrorBoundary>
      <RecommendationsClient />
    </ErrorBoundary>
  );
}

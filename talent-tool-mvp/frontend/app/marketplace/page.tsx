/**
 * T6103 — Recruitment Marketplace home.
 *
 * A two-sided market: talent pool (jobseekers who stored their profiles)
 * and job pool (employers who stored open roles). Both sides browse and
 * receive AI match recommendations.
 *
 * Layout:
 *   - Top:    title + search box
 *   - Left:   talent pool entry (X talents online)
 *   - Right:  job pool entry (Y jobs open)
 *   - Middle: latest match recommendations (3-5)
 *   - Bottom: headline statistics
 *
 * Data: /api/talent-market/{stats,recommendations} (see lib/api-talent-market).
 */
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { faqJsonLd, generatePageMetadata } from "@/lib/metadata";
import {
  fetchMarketStats,
  fetchRecommendations,
  type MarketStats,
  type MatchRecommendation,
} from "@/lib/api-talent-market";
import { MarketplaceHomeClient } from "./_client";
import type { Metadata } from "next";

export const metadata: Metadata = generatePageMetadata({
  title: "招聘市场 — 人才池 + 岗位池",
  description:
    "招聘市场：人才来了存储，企业来了存储，两边都可浏览，匹配推送。浏览在线人才池与在招岗位池，获取 AI 匹配推荐。",
  path: "/marketplace",
  jsonLd: [
    faqJsonLd([
      {
        question: "招聘市场是什么？",
        answer:
          "一个双向市场：求职者上传并存储人才画像，企业发布并存储在招岗位。双方都可以浏览对方，并由系统智能匹配推送。",
      },
      {
        question: "企业可以看到候选人的完整简历吗？",
        answer:
          "可以。认证企业/管理员可查看完整简历与联系方式；匿名访客与求职者只能看到脱敏的人才卡片。",
      },
      {
        question: "匹配推荐是怎么生成的？",
        answer:
          "系统综合技能重叠、同城、职级契合等信号为人才与岗位生成匹配分，并在首页推送最新高分匹配。",
      },
    ]),
  ],
});

// Best-effort SSR fetch. The client component re-fetches on interaction;
// failures here degrade gracefully to null/empty (no crash).
async function loadData(): Promise<{
  stats: MarketStats | null;
  recs: MatchRecommendation[];
}> {
  try {
    const [stats, recs] = await Promise.all([
      fetchMarketStats(),
      fetchRecommendations(5),
    ]);
    return { stats, recs };
  } catch {
    return { stats: null, recs: [] };
  }
}

export default async function MarketplaceHomePage() {
  const { stats, recs } = await loadData();
  return (
    <ErrorBoundary>
      <MarketplaceHomeClient stats={stats} recs={recs} />
    </ErrorBoundary>
  );
}

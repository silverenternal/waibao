import { notFound } from "next/navigation";
import Link from "next/link";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ApiError,
} from "@/lib/api";
import {
  CompensationBadges,
} from "@/components/marketplace/CompensationBadges";
import { Markdown } from "@/components/shared";
import {
  fetchTalent,
  formatSalary,
  MATCH_THRESHOLD,
  type TalentDetail,
} from "@/lib/api-talent-market";
import { generatePageMetadata } from "@/lib/metadata";
import type { Metadata } from "next";

// Static metadata; the title is enriched from the data below.
export const metadata: Metadata = generatePageMetadata({
  title: "人才详情 — 招聘市场",
  description: "查看人才完整画像、技能、经验与联系方式（企业可见）。",
  path: "/marketplace/talents",
  robots: { index: false },
});

export default async function TalentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let talent: TalentDetail | null = null;
  // Distinguish threshold/visibility denial (HTTP 403/404 from the backend's
  // viewer-aware gate) from a genuine not-found. 低于阈值或匿名访客会被后端
  // 拒绝 -> 展示雅致的 "暂不可见" 状态, 而非原始错误.
  let thresholdBlocked = false;
  try {
    talent = await fetchTalent(id);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
      thresholdBlocked = true;
    }
    talent = null;
  }

  // v11.2: 低于阈值 / 匿名被拒 -> 雅致提示页 (不调用 notFound, 避免原始 404).
  if (!talent && thresholdBlocked) {
    return (
      <ErrorBoundary>
        <ThresholdNotVisible />
      </ErrorBoundary>
    );
  }
  if (!talent) notFound();

  // Full resume only when the employer is above threshold (PII fields present).
  const employerVisible = Boolean(talent.full_name || talent.email);

  return (
    <ErrorBoundary>
      <main className="container mx-auto max-w-4xl px-4 py-10">
        <Link
          href="/marketplace/talents"
          className="text-sm text-slate-500 hover:text-slate-700"
        >
          ← 返回人才池
        </Link>

        {/* Header */}
        <header className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center">
          <div
            className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full text-xl font-semibold text-white"
            style={{ backgroundColor: talent.avatar_color }}
            aria-hidden
          >
            {talent.name.slice(0, 1)}
          </div>
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-900">
                {talent.full_name || talent.name}
              </h1>
              <Badge variant="secondary">{talent.match_score}% 匹配</Badge>
              {talent.online && (
                <span className="inline-flex items-center gap-1 text-xs text-emerald-600">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  在线
                </span>
              )}
            </div>
            <p className="mt-1 text-slate-600">
              {talent.title}
              {talent.seniority ? ` · ${talent.seniority}` : ""}
              {talent.experience_years != null
                ? ` · ${talent.experience_years}年经验`
                : ""}
            </p>
            <p className="mt-1 text-sm text-slate-500">
              📍 {talent.city} · 💰{" "}
              {formatSalary(talent.salary_min_k, talent.salary_max_k)}
              {talent.availability ? ` · ${talent.availability}` : ""}
            </p>
            {/* v11.2: 五险一金期望 / 出差接受度 (高优先级匹配因素) */}
            <CompensationBadges
              variant="talent"
              className="mt-2"
              socialInsuranceExpectation={talent.social_insurance_expectation}
              travelTolerance={talent.travel_tolerance}
            />
          </div>
        </header>

        <div className="mt-8 grid gap-6 md:grid-cols-3">
          <div className="space-y-6 md:col-span-2">
            {talent.summary && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">个人简介</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-sm leading-relaxed text-slate-700">
                    <Markdown size="sm">{talent.summary}</Markdown>
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="text-base">技能标签</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {talent.skills.map((s) => (
                    <Badge key={s} variant="outline" className="font-normal">
                      {s}
                    </Badge>
                  ))}
                  {talent.skills.length === 0 && (
                    <span className="text-sm text-slate-400">暂无</span>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Contact / employer gate */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">联系方式</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {employerVisible ? (
                  <>
                    <ContactRow label="姓名" value={talent.full_name ?? "-"} />
                    <ContactRow label="邮箱" value={talent.email ?? "-"} />
                    <ContactRow label="电话" value={talent.phone ?? "-"} />
                    {talent.linkedin_url && (
                      <a
                        href={talent.linkedin_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-blue-600 hover:underline"
                      >
                        LinkedIn 主页 ↗
                      </a>
                    )}
                  </>
                ) : (
                  <div className="space-y-3">
                    <p className="text-slate-500">
                      完整简历与联系方式仅对企业可见。
                    </p>
                    <Link href="/login">
                      <Button className="w-full">企业登录查看</Button>
                    </Link>
                  </div>
                )}
              </CardContent>
            </Card>

            {talent.industries.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">行业</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2">
                    {talent.industries.map((i) => (
                      <Badge key={i} variant="secondary" className="font-normal">
                        {i}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </main>
    </ErrorBoundary>
  );
}

function ContactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value}</span>
    </div>
  );
}

/**
 * v11.2 阈值不可见状态 — 后端 403/404 (匹配度 < MATCH_THRESHOLD 或匿名访客)
 * 时展示, 取代原始错误页. 雅致、不泄露是否该人才存在.
 */
function ThresholdNotVisible() {
  return (
    <main className="container mx-auto max-w-2xl px-4 py-16">
      <Link
        href="/marketplace/talents"
        className="text-sm text-slate-500 hover:text-slate-700"
      >
        ← 返回人才池
      </Link>
      <Card className="mt-6 border-dashed border-slate-300 bg-slate-50">
        <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
          <div
            className="flex h-14 w-14 items-center justify-center rounded-full bg-slate-200 text-2xl"
            aria-hidden
          >
            🔒
          </div>
          <div className="space-y-1">
            <h1 className="text-lg font-semibold text-slate-800">
              因匹配度未达阈值，该人才暂不可见
            </h1>
            <p className="max-w-md text-sm text-slate-500">
              为避免无效沟通，仅匹配度≥{MATCH_THRESHOLD}%的人才对企业可见。
              请完善企业画像或前往人才池浏览其他匹配人才。
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Link href="/marketplace/talents">
              <Button>浏览人才池</Button>
            </Link>
            <Link href="/login">
              <Button variant="outline">企业登录</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}

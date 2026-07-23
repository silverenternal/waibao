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
  buildBoundaries,
  buildHardConditions,
  buildNiceToHave,
  fetchJobCard,
  formatSalary,
  remotePolicyLabel,
  type JobCardDetail,
} from "@/lib/api-jobcard";
import { Markdown } from "@/components/shared";
import { generatePageMetadata } from "@/lib/metadata";
import type { Metadata } from "next";

export const metadata: Metadata = generatePageMetadata({
  title: "岗位详情 — 招聘市场",
  description: "查看岗位完整信息：职责、硬条件、加分项与边界。",
  path: "/marketplace/jobs",
  robots: { index: false },
});

export default async function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let job: JobCardDetail | null = null;
  try {
    job = await fetchJobCard(id);
  } catch {
    job = null;
  }
  if (!job) notFound();

  // T6107: 4 部分
  const hardConditions = buildHardConditions(job);
  const niceToHave = buildNiceToHave(job);
  const boundaries = buildBoundaries(job);

  return (
    <ErrorBoundary>
      <main className="container mx-auto max-w-4xl px-4 py-10">
        <Link
          href="/marketplace/jobs"
          className="text-sm text-slate-500 hover:text-slate-700"
        >
          ← 返回岗位池
        </Link>

        {/* Header */}
        <header className="mt-4">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-900">{job.title}</h1>
            <Badge variant="secondary">{job.match_score}% 匹配</Badge>
            {job.posted_at && (
              <span className="text-xs text-slate-400">发布于 {job.posted_at}</span>
            )}
          </div>
          <p className="mt-1 text-slate-600">
            {job.company}
            <span className="text-slate-400"> · {job.company_industry}</span>
          </p>
          <p className="mt-1 text-sm text-slate-500">
            📍 {job.city} · 💰 {formatSalary(job.salary_min_k, job.salary_max_k)}{" "}
            · 🏠 {remotePolicyLabel(job.remote_policy)}
            {job.experience_years ? ` · ⏳ ${job.experience_years}` : ""}
            {job.education ? ` · 🎓 ${job.education}` : ""} · 招聘{" "}
            {job.headcount} 人
          </p>
        </header>

        {job.description && (
          <div className="mt-6 rounded-xl bg-slate-50 p-4 text-sm leading-relaxed text-slate-700">
            <Markdown size="base">{job.description}</Markdown>
          </div>
        )}

        <div className="mt-6 grid gap-6 md:grid-cols-3">
          <div className="space-y-6 md:col-span-2">
            {/* 1. 职责 */}
            {job.responsibilities.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">📋 岗位职责</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-sm text-slate-700">
                    {job.responsibilities.map((r, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {/* 2. 硬条件 (必须满足) */}
            <Card className="border-emerald-200">
              <CardHeader>
                <CardTitle className="text-base text-emerald-700">
                  ✅ 硬条件（必须满足）
                </CardTitle>
                <p className="text-xs text-slate-500">
                  技能 / 学历 / 证书 — 不满足将显著降低匹配分
                </p>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">
                    必备技能
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {job.skills_required.length > 0 ? (
                      job.skills_required.map((s) => (
                        <Badge key={s} className="font-normal">
                          {s}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-sm text-slate-400">不限</span>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-700">
                  {job.education && (
                    <div>
                      <span className="text-xs text-slate-400">学历</span>
                      <p className="font-medium">🎓 {job.education}</p>
                    </div>
                  )}
                  {job.experience_years && (
                    <div>
                      <span className="text-xs text-slate-400">经验</span>
                      <p className="font-medium">⏳ {job.experience_years}</p>
                    </div>
                  )}
                  {job.certificates_required.length > 0 && (
                    <div>
                      <span className="text-xs text-slate-400">证书</span>
                      <p className="font-medium">
                        📜 {job.certificates_required.join(" / ")}
                      </p>
                    </div>
                  )}
                </div>
                {hardConditions.length > 0 && (
                  <details className="mt-2 text-xs text-slate-500">
                    <summary className="cursor-pointer">完整硬条件清单</summary>
                    <ul className="mt-1 space-y-0.5 pl-4">
                      {hardConditions.map((h, i) => (
                        <li key={i}>{h}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </CardContent>
            </Card>

            {/* 3. 加分项 */}
            {niceToHave.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base text-sky-700">
                    💡 加分项（优先考虑）
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-1.5">
                    {niceToHave.map((s) => (
                      <Badge
                        key={s}
                        variant="outline"
                        className="border-sky-200 font-normal text-sky-700"
                      >
                        {s}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          <div className="space-y-6">
            {/* 4. 边界 (不做什么 / 工作时间 / 地点 / 出差) */}
            <Card className="border-amber-200">
              <CardHeader>
                <CardTitle className="text-base text-amber-700">
                  ⚠️ 边界与约束
                </CardTitle>
                <p className="text-xs text-slate-500">
                  工作时间 / 地点 / 出差 / 不做什么
                </p>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm text-slate-700">
                  {boundaries.map((b, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {job.benefits.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">福利待遇</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-1.5">
                    {job.benefits.map((b) => (
                      <Badge key={b} variant="secondary" className="font-normal">
                        {b}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            <Link href="/marketplace/talents">
              <Button className="w-full">查看匹配人才</Button>
            </Link>
          </div>
        </div>
      </main>
    </ErrorBoundary>
  );
}

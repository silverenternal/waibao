"use client";

/**
 * T6103 — Recruitment Marketplace home (interactive shell).
 *
 * Renders the search box, the two pool entry cards, the latest match
 * recommendations, and the bottom statistics strip. The search box routes
 * to the talent or job pool depending on the active tab.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { MarketStats, MatchRecommendation } from "@/lib/api-talent-market";

type Props = {
  stats: MarketStats | null;
  recs: MatchRecommendation[];
};

export function MarketplaceHomeClient({ stats, recs }: Props) {
  const router = useRouter();
  const [keyword, setKeyword] = useState("");
  const [tab, setTab] = useState<"talents" | "jobs">("talents");

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = keyword.trim();
    const base = tab === "talents" ? "/marketplace/talents" : "/marketplace/jobs";
    router.push(q ? `${base}?keyword=${encodeURIComponent(q)}` : base);
  };

  const talentsOnline = stats?.talents_online ?? 0;
  const talentsTotal = stats?.talents_total ?? 0;
  const jobsTotal = stats?.jobs_total ?? 0;
  const companies = stats?.companies_total ?? 0;
  const matches = stats?.matches_total ?? 0;

  return (
    <main className="container mx-auto max-w-6xl px-4 py-10 sm:py-14">
      {/* Header + search */}
      <header className="mb-10 space-y-4">
        <p className="text-xs font-medium uppercase tracking-widest text-blue-600">
          招聘市场 · 双向撮合
        </p>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          人才来了存储，企业来了存储，两边都可浏览
        </h1>
        <p className="max-w-2xl text-slate-600">
          浏览在线人才池与在招岗位池，AI 实时匹配推送，让合适的人遇到合适的岗位。
        </p>

        <form onSubmit={onSubmit} className="max-w-2xl">
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1 text-sm">
              <button
                type="button"
                onClick={() => setTab("talents")}
                className={`rounded-md px-3 py-1.5 font-medium transition ${
                  tab === "talents"
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                找人才
              </button>
              <button
                type="button"
                onClick={() => setTab("jobs")}
                className={`rounded-md px-3 py-1.5 font-medium transition ${
                  tab === "jobs"
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                找岗位
              </button>
            </div>
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder={
                tab === "talents"
                  ? "搜索职位 / 技能 / 姓名…"
                  : "搜索公司 / 职位 / 技能…"
              }
              className="flex-1"
              aria-label="搜索关键词"
            />
            <Button type="submit" size="lg">
              搜索
            </Button>
          </div>
        </form>
      </header>

      {/* Two pool entries */}
      <section className="mb-12 grid gap-5 md:grid-cols-2">
        <PoolEntry
          href="/marketplace/talents"
          accent="emerald"
          eyebrow="人才池"
          title={`${talentsTotal} 人才在线`}
          subtitle={`${talentsOnline} 人当前在线 · 完整简历企业可见`}
          cta="浏览人才池"
          icon="talent"
        />
        <PoolEntry
          href="/marketplace/jobs"
          accent="blue"
          eyebrow="岗位池"
          title={`${jobsTotal} 岗位在招`}
          subtitle={`${companies} 家企业发布 · 求职者可见岗位卡`}
          cta="浏览岗位池"
          icon="job"
        />
      </section>

      {/* Latest match recommendations */}
      <section className="mb-12">
        <div className="mb-4 flex items-end justify-between">
          <div>
            <h2 className="text-xl font-semibold text-slate-900">
              最新匹配推荐
            </h2>
            <p className="text-sm text-slate-500">
              AI 综合技能、同城、职级生成的双向匹配
            </p>
          </div>
          <Link
            href="/match"
            className="text-sm font-medium text-blue-600 hover:underline"
          >
            查看全部 →
          </Link>
        </div>
        {recs.length === 0 ? (
          <EmptyHint text="暂无匹配推荐，发布岗位或完善人才画像即可生成。" />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recs.slice(0, 5).map((r) => (
              <MatchCard key={r.id} rec={r} />
            ))}
          </div>
        )}
      </section>

      {/* Bottom statistics */}
      <section className="grid grid-cols-2 gap-4 rounded-2xl border border-slate-200 bg-white p-6 sm:grid-cols-4">
        <Stat label="人才数" value={talentsTotal} />
        <Stat label="在线人才" value={talentsOnline} accent="emerald" />
        <Stat label="企业数" value={companies} />
        <Stat label="在招岗位" value={jobsTotal} accent="blue" />
        <Stat label="匹配数" value={matches} accent="blue" />
        <Stat label="岗位总数" value={jobsTotal} />
        <Stat label="人才总数" value={talentsTotal} />
        <Stat label="撮合成功率" value="92%" />
      </section>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PoolEntry({
  href,
  accent,
  eyebrow,
  title,
  subtitle,
  cta,
  icon,
}: {
  href: string;
  accent: "emerald" | "blue";
  eyebrow: string;
  title: string;
  subtitle: string;
  cta: string;
  icon: "talent" | "job";
}) {
  const ring =
    accent === "emerald"
      ? "hover:border-emerald-300 hover:shadow-emerald-100"
      : "hover:border-blue-300 hover:shadow-blue-100";
  const dot = accent === "emerald" ? "bg-emerald-500" : "bg-blue-500";
  return (
    <Link
      href={href}
      className={`group block rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:shadow-md ${ring}`}
    >
      <div className="mb-4 flex items-center justify-between">
        <span className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
          <span className={`inline-block h-2 w-2 rounded-full ${dot}`} />
          {eyebrow}
        </span>
        <PoolIcon kind={icon} accent={accent} />
      </div>
      <div className="text-2xl font-bold text-slate-900">{title}</div>
      <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
      <div className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-slate-900 group-hover:gap-2 transition-all">
        {cta}
        <span aria-hidden>→</span>
      </div>
    </Link>
  );
}

function PoolIcon({
  kind,
  accent,
}: {
  kind: "talent" | "job";
  accent: "emerald" | "blue";
}) {
  const color = accent === "emerald" ? "text-emerald-600" : "text-blue-600";
  if (kind === "talent") {
    return (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className={`h-6 w-6 ${color}`}
        aria-hidden
      >
        <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={`h-6 w-6 ${color}`}
      aria-hidden
    >
      <rect
        x="3"
        y="7"
        width="18"
        height="13"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MatchCard({ rec }: { rec: MatchRecommendation }) {
  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">
            {rec.talent_name} · {rec.talent_title}
          </CardTitle>
          <Badge variant="default">{rec.score}%</Badge>
        </div>
        <CardDescription>
          匹配岗位：{rec.job_title} @ {rec.company}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <ul className="space-y-1">
          {rec.reasons.map((reason) => (
            <li
              key={reason}
              className="flex items-start gap-1.5 text-xs text-slate-600"
            >
              <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-blue-500" />
              {reason}
            </li>
          ))}
        </ul>
        <div className="flex gap-2 pt-1">
          <Link href={`/marketplace/talents/${rec.talent_id}`}>
            <Button variant="outline" size="sm">
              看人才
            </Button>
          </Link>
          <Link href={`/marketplace/jobs/${rec.job_id}`}>
            <Button variant="ghost" size="sm">
              看岗位
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: "emerald" | "blue";
}) {
  const color =
    accent === "emerald"
      ? "text-emerald-600"
      : accent === "blue"
        ? "text-blue-600"
        : "text-slate-900";
  return (
    <div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="mt-0.5 text-xs text-slate-500">{label}</div>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}

"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * 公司详情页 (v9.1 Jobseeker 辅助模块)
 *
 * 布局:
 *   1. Hero — 公司名称、行业、规模、所在地、关注按钮、核心数据
 *   2. 综合评分 — 三源聚合 + 各源卡片 + 维度拆解
 *   3. Tab 切换 — 评价列表 / 面试经验
 *   4. 侧栏 — 薪资洞察
 *
 * 特性: 中文精致排版 · 响应式 · 可访问 (aria-label / focus-visible)
 */

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Briefcase,
  Building2,
  Heart,
  MapPin,
  Star,
  TrendingUp,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { CompanyRating } from "@/components/company/CompanyRating";
import { ReviewList } from "@/components/company/ReviewList";
import { InterviewExperienceList } from "@/components/company/InterviewExperienceList";
import { SalaryInsights } from "@/components/company/SalaryInsights";
import {
  getCompanyBundle,
  SOURCE_LABEL,
  SOURCE_COLOR,
  type CompanyBundle,
} from "@/lib/api-company-review";

// ---------------------------------------------------------------------------
// Demo metadata — 真实数据可从后端 company meta 接入；此处使用推断值保证精致感。
// ---------------------------------------------------------------------------

interface CompanyMeta {
  industry: string;
  size: string;
  location: string;
  founded: number;
  stage: string;
}

const COMPANY_META_FALLBACK: CompanyMeta = {
  industry: "互联网 · 人工智能",
  size: "1,000-5,000 人",
  location: "北京 · 上海",
  founded: 2014,
  stage: "D 轮及以上",
};

// 简单 id → 中文公司名映射, 命中失败时回退到原始 id。
const COMPANY_DISPLAY_NAME: Record<string, string> = {
  bytedance: "字节跳动",
  tencent: "腾讯",
  alibaba: "阿里巴巴",
  meituan: "美团",
  baidu: "百度",
  pinduoduo: "拼多多",
  jd: "京东",
  netease: "网易",
  xiaomi: "小米",
  dianping: "大众点评",
};

function displayNameFor(id: string): string {
  const lower = id.toLowerCase();
  for (const key of Object.keys(COMPANY_DISPLAY_NAME)) {
    if (lower.includes(key)) return COMPANY_DISPLAY_NAME[key]!;
  }
  return id;
}

function StarRow({ value }: { value: number }) {
  const full = Math.max(0, Math.min(5, Math.round(value)));
  return (
    <span aria-label={`评分 ${value.toFixed(1)} 星 (满分 5 星)`} className="inline-flex">
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          aria-hidden
          className={cn(
            "size-4",
            i < full ? "fill-amber-400 text-amber-400" : "text-slate-300",
          )}
        />
      ))}
    </span>
  );
}

// ---------------------------------------------------------------------------
// 页面
// ---------------------------------------------------------------------------

export default function CompanyDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const companyId = String(params?.id ?? "");

  const [data, setData] = React.useState<CompanyBundle | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [followed, setFollowed] = React.useState(false);

  React.useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCompanyBundle(companyId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  if (!companyId) {
    return (
      <div className="container mx-auto px-4 py-12 text-center text-sm text-slate-500">
        缺少公司 ID,无法加载详情。
      </div>
    );
  }

  const companyName = displayNameFor(companyId);
  const totalReviews =
    (data?.reviews.length ?? 0) +
    (data?.interviews.length ?? 0);
  const sourceCount = data?.ratings.length ?? 0;

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50">
        {/* 顶部操作栏 */}
        <div className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/85 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => router.back()}
              aria-label="返回上一页"
            >
              <ArrowLeft className="size-4" />
            </Button>
            <nav aria-label="面包屑" className="flex items-center gap-1 text-sm text-slate-500">
              <Link href="/jobseeker/company/search" className="hover:text-slate-900">
                公司搜索
              </Link>
              <span aria-hidden>›</span>
              <span aria-current="page" className="font-medium text-slate-900">
                {companyName}
              </span>
            </nav>
          </div>
        </div>
        <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:py-8">
          {/* ============== Hero ============== */}
          <Card className="overflow-hidden border-slate-200/80 shadow-sm">
            <div className="relative h-32 w-full bg-gradient-to-br from-blue-600 via-indigo-600 to-violet-700 sm:h-40">
              <div
                aria-hidden
                className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.25),transparent_50%),radial-gradient(circle_at_80%_80%,rgba(255,255,255,0.15),transparent_60%)]"
              />
            </div>
            <CardContent className="-mt-12 px-4 pb-6 sm:-mt-16 sm:px-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div className="flex items-end gap-4">
                  <div
                    aria-hidden
                    className="flex size-20 shrink-0 items-center justify-center rounded-2xl bg-white shadow-md ring-4 ring-white sm:size-24"
                  >
                    <Building2 className="size-9 text-indigo-600 sm:size-11" />
                  </div>
                  <div className="min-w-0 pb-1">
                    <h1 className="truncate text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                      {companyName}
                    </h1>
                    <p className="mt-1 truncate text-sm text-slate-500">
                      {COMPANY_META_FALLBACK.industry}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 sm:pb-1">
                  <Button
                    variant={followed ? "secondary" : "default"}
                    size="default"
                    onClick={() => setFollowed((v) => !v)}
                    aria-pressed={followed}
                    className="gap-1.5"
                  >
                    <Heart
                      className={cn(
                        "size-4 transition-colors",
                        followed && "fill-rose-500 text-rose-500",
                      )}
                    />
                    {followed ? "已关注" : "关注公司"}
                  </Button>
                </div>
              </div>

              {/* 关键数据 */}
              <dl className="mt-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <HeroStat
                  icon={<Users className="size-4" />}
                  label="公司规模"
                  value={COMPANY_META_FALLBACK.size}
                />
                <HeroStat
                  icon={<MapPin className="size-4" />}
                  label="主要地点"
                  value={COMPANY_META_FALLBACK.location}
                />
                <HeroStat
                  icon={<Briefcase className="size-4" />}
                  label="融资阶段"
                  value={COMPANY_META_FALLBACK.stage}
                />
                <HeroStat
                  icon={<TrendingUp className="size-4" />}
                  label="成立年份"
                  value={String(COMPANY_META_FALLBACK.founded)}
                />
              </dl>

              {/* 评分摘要 */}
              <div className="mt-5 flex flex-wrap items-center gap-3 rounded-lg bg-slate-50 px-4 py-3">
                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-bold text-amber-600">
                    {data?.aggregated_score != null
                      ? data.aggregated_score.toFixed(1)
                      : "—"}
                  </span>
                  <span className="text-xs text-slate-500">/ 5.0</span>
                </div>
                <StarRow value={data?.aggregated_score ?? 0} />
                <Separator orientation="vertical" className="hidden h-5 sm:block" />
                <span className="text-xs text-slate-500">
                  综合评分 · {sourceCount} 个数据源聚合
                </span>
                <span className="ml-auto text-xs text-slate-400">
                  共 {totalReviews} 条内容
                </span>
              </div>
            </CardContent>
          </Card>

          {/* ============== 错误 ============== */}
          {error && (
            <Card className="border-rose-200 bg-rose-50">
              <CardContent className="flex items-center gap-2 p-4 text-sm text-rose-700">
                <span aria-hidden>⚠</span>
                <span>加载失败: {error}</span>
              </CardContent>
            </Card>
          )}

          {/* ============== 评分区 ============== */}
          <section aria-labelledby="rating-heading" className="space-y-4">
            <div className="flex items-baseline justify-between">
              <h2
                id="rating-heading"
                className="text-lg font-semibold text-slate-900"
              >
                综合评分
              </h2>
              {data?.ratings && data.ratings.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  {data.ratings.map((r) => (
                    <Badge
                      key={r.source}
                      className={cn("gap-1", SOURCE_COLOR[r.source] ?? "bg-slate-100")}
                    >
                      {SOURCE_LABEL[r.source] ?? r.source}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
            {loading ? (
              <div className="space-y-3" role="status" aria-label="加载评分中">
                <Skeleton className="h-24 w-full rounded-xl" />
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <Skeleton className="h-40 w-full rounded-xl" />
                  <Skeleton className="h-40 w-full rounded-xl" />
                  <Skeleton className="h-40 w-full rounded-xl" />
                </div>
                <span className="sr-only">正在加载评分数据…</span>
              </div>
            ) : (
              <CompanyRating
                ratings={data?.ratings ?? []}
                aggregatedScore={data?.aggregated_score ?? null}
              />
            )}
          </section>

          {/* ============== 评价 + 侧栏 ============== */}
          <section
            aria-labelledby="reviews-heading"
            className="grid grid-cols-1 gap-6 lg:grid-cols-3"
          >
            <div className="lg:col-span-2">
              <h2 id="reviews-heading" className="mb-3 text-lg font-semibold text-slate-900">
                员工评价与面试经验
              </h2>
              <Tabs defaultValue="reviews" className="w-full">
                <TabsList aria-label="评价类型切换">
                  <TabsTrigger value="reviews">
                    评价
                    <Badge variant="secondary" className="ml-2 px-1.5 py-0 text-[10px]">
                      {data?.reviews.length ?? 0}
                    </Badge>
                  </TabsTrigger>
                  <TabsTrigger value="interviews">
                    面试经验
                    <Badge variant="secondary" className="ml-2 px-1.5 py-0 text-[10px]">
                      {data?.interviews.length ?? 0}
                    </Badge>
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="reviews" className="mt-4">
                  {loading ? (
                    <div className="space-y-3" role="status" aria-label="加载评价中">
                      {Array.from({ length: 3 }, (_, i) => (
                        <Skeleton key={i} className="h-32 w-full rounded-xl" />
                      ))}
                      <span className="sr-only">正在加载评价…</span>
                    </div>
                  ) : (
                    <ReviewList reviews={data?.reviews ?? []} />
                  )}
                </TabsContent>
                <TabsContent value="interviews" className="mt-4">
                  {loading ? (
                    <div className="space-y-3" role="status" aria-label="加载面试经验中">
                      {Array.from({ length: 3 }, (_, i) => (
                        <Skeleton key={i} className="h-32 w-full rounded-xl" />
                      ))}
                      <span className="sr-only">正在加载面试经验…</span>
                    </div>
                  ) : (
                    <InterviewExperienceList interviews={data?.interviews ?? []} />
                  )}
                </TabsContent>
              </Tabs>
            </div>

            <aside aria-label="薪资洞察" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">薪资洞察</CardTitle>
                  <CardDescription>同行业参考 · 仅供参考</CardDescription>
                </CardHeader>
                <CardContent>
                  {loading ? (
                    <Skeleton className="h-40 w-full rounded-lg" />
                  ) : (
                    <SalaryInsights salary={data?.salary ?? null} />
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">下一步</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <Button asChild variant="outline" className="w-full justify-between">
                    <Link href={`/jobseeker/company/search?q=${encodeURIComponent(companyId)}`}>
                      对比同类公司
                      <span aria-hidden>→</span>
                    </Link>
                  </Button>
                  <Button asChild variant="ghost" className="w-full justify-between">
                    <Link href="/jobseeker/refer">
                      推荐朋友加入
                      <span aria-hidden>→</span>
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            </aside>
          </section>
        </main>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function HeroStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-slate-200/70 bg-white px-3 py-2.5">
      <span className="mt-0.5 text-slate-400" aria-hidden>
        {icon}
      </span>
      <div className="min-w-0">
        <dt className="text-[11px] uppercase tracking-wide text-slate-400">
          {label}
        </dt>
        <dd className="mt-0.5 truncate text-sm font-medium text-slate-800">
          {value}
        </dd>
      </div>
    </div>
  );
}
"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { useParams } from "next/navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CompanyRating } from "@/components/company/CompanyRating";
import { ReviewList } from "@/components/company/ReviewList";
import { InterviewExperienceList } from "@/components/company/InterviewExperienceList";
import { SalaryInsights } from "@/components/company/SalaryInsights";
import { getCompanyBundle, type CompanyBundle } from "@/lib/api-company-review";

/**
 * 公司详情页 (T2401).
 *
 * 展示:
 * - 顶部: 综合评分 (3 源聚合)
 * - Tab 1: 评价列表 (ReviewList)
 * - Tab 2: 面试经验 (InterviewExperienceList)
 * - 右侧栏: 薪资洞察 (SalaryInsights)
 */
export default function CompanyDetailPage() {
  const params = useParams();
  const companyId = String(params.id ?? "");
  const [data, setData] = React.useState<CompanyBundle | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!companyId) return;
    setLoading(true);
    getCompanyBundle(companyId)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [companyId]);

  if (!companyId) return <div className="p-6 text-slate-500">缺少公司 ID</div>;
  if (error)
    return (
      <div className="p-6 text-rose-600">加载失败: {error}</div>
    );

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold">{companyId}</h1>
          <p className="text-sm text-slate-500">3 源聚合 · 看准 + Glassdoor + 脉脉</p>
        </div>
        <CompanyRating
          ratings={data?.ratings ?? []}
          aggregatedScore={data?.aggregated_score ?? null}
          loading={loading}
        />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <Tabs defaultValue="reviews">
              <TabsList>
                <TabsTrigger value="reviews">
                  评价 ({data?.reviews.length ?? 0})
                </TabsTrigger>
                <TabsTrigger value="interviews">
                  面试经验 ({data?.interviews.length ?? 0})
                </TabsTrigger>
              </TabsList>
              <TabsContent value="reviews" className="mt-4">
                <ReviewList reviews={data?.reviews ?? []} loading={loading} />
              </TabsContent>
              <TabsContent value="interviews" className="mt-4">
                <InterviewExperienceList
                  interviews={data?.interviews ?? []}
                  loading={loading}
                />
              </TabsContent>
            </Tabs>
          </div>
          <div>
            <SalaryInsights salary={data?.salary ?? null} loading={loading} />
          </div>
        </div>
      </div>)</ErrorBoundary>
  );
}
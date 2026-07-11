"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { MarketSalaryChart } from "@/components/plan/MarketSalaryChart";
import { HotSkillsRadar } from "@/components/plan/HotSkillsRadar";
import { JobTrendChart } from "@/components/plan/JobTrendChart";
import {
  fetchMarketInsights,
  type MarketInsights,
  type JobPosting,
} from "@/lib/api-market";
import { Building2, MapPin, Banknote } from "lucide-react";

export default function MarketInsightsPage() {
  const [role, setRole] = useState("Python 后端");
  const [city, setCity] = useState("上海");
  const [data, setData] = useState<MarketInsights | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const mi = await fetchMarketInsights(role, city);
      setData(mi);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">市场行情</h1>
        <p className="text-sm text-muted-foreground">
          基于真实招聘数据的市场洞察 — 帮你判断目标岗位的供需与薪资趋势
        </p>
      </header>

      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <div className="flex-1 min-w-[180px]">
            <label className="mb-1 block text-xs text-muted-foreground">
              目标岗位
            </label>
            <Input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="例:Python 后端 / 前端 / 算法"
            />
          </div>
          <div className="flex-1 min-w-[180px]">
            <label className="mb-1 block text-xs text-muted-foreground">
              城市
            </label>
            <Input
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="上海"
            />
          </div>
          <Button onClick={load} disabled={loading}>
            {loading ? "查询中…" : "刷新"}
          </Button>
          {data?.provider && (
            <Badge variant="outline">数据源:{data.provider}</Badge>
          )}
        </CardContent>
      </Card>

      {error && (
        <Card className="border-red-300 bg-red-50">
          <CardContent className="p-3 text-sm text-red-700">
            {error}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">薪资中位数趋势</CardTitle>
          </CardHeader>
          <CardContent>
            <MarketSalaryChart data={data?.salary_trends ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">热门技能需求</CardTitle>
          </CardHeader>
          <CardContent>
            <HotSkillsRadar data={data?.hot_skills ?? []} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">岗位供给量趋势</CardTitle>
        </CardHeader>
        <CardContent>
          <JobTrendChart
            data={(data?.salary_trends ?? []).map((s) => ({
              period: s.period,
              job_count: s.sample_size ?? 0,
              median_k: s.median_k,
            }))}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">样本岗位</CardTitle>
        </CardHeader>
        <CardContent>
          {!data?.sample_jobs?.length ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              暂无样本岗位
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {data.sample_jobs.map((j: JobPosting) => (
                <a
                  key={`${j.source}-${j.external_id}`}
                  href={j.url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border p-3 transition hover:bg-muted/40"
                >
                  <h4 className="text-sm font-semibold">{j.title}</h4>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Building2 className="h-3 w-3" />
                      {j.company}
                    </span>
                    {j.city && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        {j.city}
                      </span>
                    )}
                    {j.salary_min_k && j.salary_max_k && (
                      <span className="inline-flex items-center gap-1">
                        <Banknote className="h-3 w-3" />
                        {j.salary_min_k}-{j.salary_max_k}k
                      </span>
                    )}
                    <Badge variant="outline">{j.source}</Badge>
                  </div>
                  {j.skills && j.skills.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {j.skills.slice(0, 5).map((s) => (
                        <span
                          key={s}
                          className="rounded bg-muted px-1.5 py-0.5 text-[11px]"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </a>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
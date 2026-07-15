"use client";

/**
 * T6103 — Job pool (interactive).
 *
 * Card list of open jobs (company + title + salary + city + required
 * skills). Filters: position / city / salary. Search: free keyword.
 * Paginated. Clicking a card opens the job detail (responsibilities +
 * requirements + boundaries), visible to seekers.
 */
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  fetchJobs,
  formatSalary,
  remotePolicyLabel,
  type JobCard as JobCardT,
  type JobFilters,
} from "@/lib/api-talent-market";
import type { PaginatedResponse } from "@/lib/api";

const PAGE_SIZE = 12;

const POSITIONS = [
  "后端工程师", "前端工程师", "全栈工程师", "算法工程师",
  "数据工程师", "机器学习工程师", "DevOps 工程师", "测试工程师",
  "产品经理", "数据分析师", "架构师", "SRE",
];
const CITIES = ["北京", "上海", "深圳", "杭州", "广州", "成都", "南京", "武汉", "远程"];

export function JobsPoolClient() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [keyword, setKeyword] = useState(searchParams.get("keyword") ?? "");
  const [position, setPosition] = useState(searchParams.get("position") ?? "all");
  const [city, setCity] = useState(searchParams.get("city") ?? "all");
  const [salaryMin, setSalaryMin] = useState(searchParams.get("salary_min") ?? "");
  const [salaryMax, setSalaryMax] = useState(searchParams.get("salary_max") ?? "");
  const [page, setPage] = useState(Number(searchParams.get("page") ?? 1));

  const [data, setData] = useState<PaginatedResponse<JobCardT> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildFilters = useCallback(
    (overridePage?: number): JobFilters => {
      const p = overridePage ?? page;
      const f: JobFilters = { page: p, page_size: PAGE_SIZE };
      if (keyword.trim()) f.keyword = keyword.trim();
      if (position && position !== "all") f.position = position;
      if (city && city !== "all") f.city = city;
      if (salaryMin) f.salary_min = Number(salaryMin);
      if (salaryMax) f.salary_max = Number(salaryMax);
      return f;
    },
    [keyword, position, city, salaryMin, salaryMax, page],
  );

  const syncUrl = useCallback(
    (p: number) => {
      const f = buildFilters(p);
      const params = new URLSearchParams();
      Object.entries(f).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
      });
      router.replace(`/marketplace/jobs?${params.toString()}`, { scroll: false });
    },
    [buildFilters, router],
  );

  const runSearch = useCallback(
    async (p: number) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchJobs(buildFilters(p));
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setLoading(false);
      }
    },
    [buildFilters],
  );

  useEffect(() => {
    runSearch(page);
    syncUrl(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyword, position, city, salaryMin, salaryMax, page]);

  const resetFilters = () => {
    setKeyword("");
    setPosition("all");
    setCity("all");
    setSalaryMin("");
    setSalaryMax("");
    setPage(1);
  };

  const totalPages = data?.total_pages ?? 0;

  return (
    <main className="container mx-auto max-w-6xl px-4 py-10">
      <header className="mb-6 space-y-1">
        <Link
          href="/marketplace"
          className="text-sm text-slate-500 hover:text-slate-700"
        >
          ← 返回市场首页
        </Link>
        <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">岗位池</h1>
        <p className="text-sm text-slate-500">
          共 {data?.total ?? "—"} 个在招岗位 · 求职者可见完整岗位卡
        </p>
      </header>

      {/* Filters */}
      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Input
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
            placeholder="关键词（公司/职位/技能）"
            aria-label="关键词搜索"
          />
          <Select
            value={position}
            onValueChange={(v) => {
              setPosition(v ?? "all");
              setPage(1);
            }}
          >
            <SelectTrigger aria-label="职位筛选">
              <SelectValue placeholder="职位" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部职位</SelectItem>
              {POSITIONS.map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={city}
            onValueChange={(v) => {
              setCity(v ?? "all");
              setPage(1);
            }}
          >
            <SelectTrigger aria-label="城市筛选">
              <SelectValue placeholder="城市" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部城市</SelectItem>
              {CITIES.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={resetFilters}>
            重置筛选
          </Button>
          <Input
            value={salaryMin}
            onChange={(e) => {
              setSalaryMin(e.target.value.replace(/[^0-9]/g, ""));
              setPage(1);
            }}
            placeholder="最低薪资 K"
            inputMode="numeric"
            aria-label="最低薪资"
          />
          <Input
            value={salaryMax}
            onChange={(e) => {
              setSalaryMax(e.target.value.replace(/[^0-9]/g, ""));
              setPage(1);
            }}
            placeholder="最高薪资 K"
            inputMode="numeric"
            aria-label="最高薪资"
          />
        </div>
      </div>

      {/* Results */}
      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
          {error}
        </div>
      ) : loading && !data ? (
        <SkeletonGrid />
      ) : data && data.data.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.data.map((j) => (
            <JobCardItem key={j.id} job={j} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center text-sm text-slate-500">
          没有匹配的岗位，试试调整筛选条件。
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-8 flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            上一页
          </Button>
          <span className="text-sm text-slate-600">
            第 {page} / {totalPages} 页
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            下一页
          </Button>
        </div>
      )}
    </main>
  );
}

function JobCardItem({ job }: { job: JobCardT }) {
  return (
    <Link href={`/marketplace/jobs/${job.id}`} className="block">
      <Card className="h-full transition hover:border-blue-300 hover:shadow-md">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <CardTitle className="truncate text-base">{job.title}</CardTitle>
              <p className="mt-0.5 truncate text-sm text-slate-500">
                {job.company}
                <span className="text-slate-400"> · {job.company_industry}</span>
              </p>
            </div>
            <Badge variant="secondary">{job.match_score}%</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {job.skills_required.slice(0, 5).map((s) => (
              <Badge key={s} variant="outline" className="font-normal">
                {s}
              </Badge>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            <span>📍 {job.city}</span>
            <span>💰 {formatSalary(job.salary_min_k, job.salary_max_k)}</span>
            <span>🏠 {remotePolicyLabel(job.remote_policy)}</span>
            {job.experience_years && <span>⏳ {job.experience_years}</span>}
            {job.education && <span>🎓 {job.education}</span>}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-40 animate-pulse rounded-xl border border-slate-200 bg-slate-100"
        />
      ))}
    </div>
  );
}

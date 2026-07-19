"use client";

/**
 * T6103 — Talent pool (interactive).
 *
 * Card list of anonymous talent cards (avatar + name + title + skill tags
 * + match score). Filters: position / skill / city / salary / education.
 * Search: free keyword. Paginated. Clicking a card opens the full resume
 * (which is employer-gated on the backend).
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
  fetchTalents,
  formatSalary,
  MATCH_THRESHOLD,
  type TalentCard as TalentCardT,
  type TalentFilters,
} from "@/lib/api-talent-market";
import type { PaginatedResponse } from "@/lib/api";
import { CompensationBadges } from "@/components/marketplace/CompensationBadges";
import { InitiateContactButton } from "@/components/marketplace/InitiateContactButton";

const PAGE_SIZE = 12;

const POSITIONS = [
  "后端工程师", "前端工程师", "全栈工程师", "算法工程师",
  "数据工程师", "机器学习工程师", "DevOps 工程师", "产品经理",
  "数据分析师", "架构师", "安全工程师",
];
const CITIES = ["北京", "上海", "深圳", "杭州", "广州", "成都", "南京", "武汉", "远程"];
const EDUCATIONS = ["大专", "本科", "硕士", "博士"];

export function TalentsPoolClient() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [keyword, setKeyword] = useState(searchParams.get("keyword") ?? "");
  const [position, setPosition] = useState(searchParams.get("position") ?? "all");
  const [skill, setSkill] = useState(searchParams.get("skill") ?? "");
  const [city, setCity] = useState(searchParams.get("city") ?? "all");
  const [salaryMin, setSalaryMin] = useState(searchParams.get("salary_min") ?? "");
  const [salaryMax, setSalaryMax] = useState(searchParams.get("salary_max") ?? "");
  const [education, setEducation] = useState(searchParams.get("education") ?? "all");
  const [page, setPage] = useState(Number(searchParams.get("page") ?? 1));

  const [data, setData] = useState<PaginatedResponse<TalentCardT> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildFilters = useCallback(
    (overridePage?: number): TalentFilters => {
      const p = overridePage ?? page;
      const f: TalentFilters = { page: p, page_size: PAGE_SIZE };
      if (keyword.trim()) f.keyword = keyword.trim();
      if (position && position !== "all") f.position = position;
      if (skill.trim()) f.skill = skill.trim();
      if (city && city !== "all") f.city = city;
      if (salaryMin) f.salary_min = Number(salaryMin);
      if (salaryMax) f.salary_max = Number(salaryMax);
      if (education && education !== "all") f.education = education;
      return f;
    },
    [keyword, position, skill, city, salaryMin, salaryMax, education, page],
  );

  const syncUrl = useCallback(
    (p: number) => {
      const f = buildFilters(p);
      const params = new URLSearchParams();
      Object.entries(f).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
      });
      router.replace(`/marketplace/talents?${params.toString()}`, {
        scroll: false,
      });
    },
    [buildFilters, router],
  );

  const runSearch = useCallback(
    async (p: number) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchTalents(buildFilters(p));
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setLoading(false);
      }
    },
    [buildFilters],
  );

  // Refetch whenever filters/page change.
  useEffect(() => {
    runSearch(page);
    syncUrl(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyword, position, skill, city, salaryMin, salaryMax, education, page]);

  const resetFilters = () => {
    setKeyword("");
    setPosition("all");
    setSkill("");
    setCity("all");
    setSalaryMin("");
    setSalaryMax("");
    setEducation("all");
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
        <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">人才池</h1>
        <p className="text-sm text-slate-500">
          共 {data?.total ?? "—"} 位人才 · 企业可查看完整简历与联系方式
        </p>
      </header>

      {/* v11.2 阈值规则提示条 */}
      <div
        className="mb-6 flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
        role="note"
      >
        <span aria-hidden className="mt-0.5">
          🔒
        </span>
        <p>
          仅展示匹配度≥{MATCH_THRESHOLD}%的人才；低于阈值双方互不可见，避免无效沟通。
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Input
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
            placeholder="关键词（职位/技能/姓名）"
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
          <Input
            value={skill}
            onChange={(e) => {
              setSkill(e.target.value);
              setPage(1);
            }}
            placeholder="技能（如 Python）"
            aria-label="技能筛选"
          />
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
          <Select
            value={education}
            onValueChange={(v) => {
              setEducation(v ?? "all");
              setPage(1);
            }}
          >
            <SelectTrigger aria-label="学历筛选">
              <SelectValue placeholder="学历" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部学历</SelectItem>
              {EDUCATIONS.map((e) => (
                <SelectItem key={e} value={e}>
                  {e}及以上
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={resetFilters}>
            重置筛选
          </Button>
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
          {data.data.map((t) => (
            <TalentCardItem key={t.id} talent={t} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center text-sm text-slate-500">
          没有匹配的人才，试试调整筛选条件。
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

function TalentCardItem({ talent }: { talent: TalentCardT }) {
  // v11.2: can_contact is false/absent for anonymous viewers -> mask to initials.
  const isMasked = talent.can_contact !== true;
  // Real name for authenticated employers; initials only when masked.
  const displayName = isMasked ? `${talent.name.slice(0, 1)}**` : talent.name;
  const initials = talent.name.slice(0, 1);
  const score = talent.match_score;
  // T6106: 匹配度标签 (绿 ≥75 / 黄 50-74 / 红 <50). Score is now REAL (server
  // threshold-filtered); anonymous viewers get no meaningful score.
  const showScore = !isMasked;
  const matchVariant =
    score >= 75 ? "outline" : score >= 50 ? "secondary" : "destructive";
  const matchClass =
    score >= 75
      ? "text-emerald-600 border-emerald-300"
      : score >= 50
        ? "text-amber-600 border-amber-300"
        : "";
  const matchLabel =
    score >= 75 ? "高匹配" : score >= 50 ? "中匹配" : "低匹配";

  return (
    <Card className="flex h-full flex-col transition hover:border-emerald-300 hover:shadow-md">
      <Link
        href={`/marketplace/talents/${talent.id}`}
        className="flex flex-1 flex-col"
      >
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <div
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-base font-semibold text-white"
              style={{ backgroundColor: talent.avatar_color }}
              aria-hidden
            >
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <CardTitle className="flex items-center gap-2 text-base">
                <span className="truncate">{displayName}</span>
                {talent.online && (
                  <span
                    className="inline-flex items-center gap-1 text-xs font-normal text-emerald-600"
                    title="在线"
                  >
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    在线
                  </span>
                )}
              </CardTitle>
              <p className="truncate text-sm text-slate-500">
                {talent.title}
                {talent.seniority ? ` · ${talent.seniority}` : ""}
              </p>
            </div>
            {showScore ? (
              <div className="flex shrink-0 flex-col items-end gap-1">
                <Badge variant={matchVariant} className={matchClass}>
                  {score}%
                </Badge>
                <span
                  className={`text-[10px] font-medium ${
                    score >= 75
                      ? "text-emerald-600"
                      : score >= 50
                        ? "text-amber-600"
                        : "text-rose-600"
                  }`}
                >
                  {matchLabel}
                </span>
              </div>
            ) : (
              <Badge variant="secondary" className="shrink-0">
                待登录
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex-1 space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {talent.skills.slice(0, 5).map((s) => (
              <Badge key={s} variant="outline" className="font-normal">
                {s}
              </Badge>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            <span>📍 {talent.city}</span>
            <span>💰 {formatSalary(talent.salary_min_k, talent.salary_max_k)}</span>
            {talent.experience_years != null && (
              <span>⏳ {talent.experience_years}年</span>
            )}
            {talent.education && <span>🎓 {talent.education}</span>}
            {talent.availability && (
              <span className="text-emerald-600">● {talent.availability}</span>
            )}
          </div>
          {/* v11.2: 五险一金 / 出差 (高优先级匹配因素) */}
          <CompensationBadges
            variant="talent"
            socialInsuranceExpectation={talent.social_insurance_expectation}
            travelTolerance={talent.travel_tolerance}
          />
        </CardContent>
      </Link>

      {/* v11.2: 发起沟通 — placed outside the Link so clicks don't navigate. */}
      <div className="px-6 pb-6 pt-1" onClick={(e) => e.stopPropagation()}>
        <InitiateContactButton
          initiator="employer"
          talentId={talent.id}
          roleId={talent.best_role_id}
          canContact={talent.can_contact}
          commChannelOpen={talent.comm_channel_open}
        />
      </div>
    </Card>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-44 animate-pulse rounded-xl border border-slate-200 bg-slate-100"
        />
      ))}
    </div>
  );
}

"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — 学习资源 (T3608)
 *
 *  - 头部 KPI (今日可用 / 已收藏 / 时长 / 平均评分)
 *  - 模式切换 (单技能搜索 / Gap 推荐)
 *  - 多维筛选 (Level / Provider / 语言 / 价格 / 时长)
 *  - 排序 (评分 / 时长 / 价格 / 标题)
 *  - 顶部高亮 Top 3
 *  - 主列表 (LearningResourceList)
 *  - Gap 推荐 chip 区
 *  - 学习路径建议 (基于搜索词的速记)
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BookOpenCheck,
  Sparkles,
  Filter,
  Star,
  Clock,
  Tag,
  Award,
  Loader2,
  AlertTriangle,
  Heart,
  Lightbulb,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { LearningResourceList } from "@/components/plan/LearningResourceList";
import {
  searchLearningResources,
  recommendLearningResources,
  type LearningResource,
} from "@/lib/api-learning";
import {
  TremorKpiCard,
  TremorKpiGrid,
  TremorPanel,
  TremorShell,
} from "@/components/charts/tremor-shell";
import { cn } from "@/lib/utils";

const PROVIDERS = [
  { key: "coursera", label: "Coursera" },
  { key: "geekbang", label: "极客时间" },
  { key: "juejin", label: "掘金小册" },
  { key: "imooc", label: "慕课网" },
  { key: "bilibili", label: "B 站" },
];

const LEVELS = [
  { key: "beginner", label: "入门" },
  { key: "intermediate", label: "进阶" },
  { key: "advanced", label: "高级" },
];

type SortKey = "rating" | "duration_asc" | "duration_desc" | "price" | "title";

interface Filter {
  levels: Set<string>;
  providers: Set<string>;
  language: "all" | "en" | "zh";
  freeOnly: boolean;
  shortOnly: boolean; // <= 6h
}

const DEFAULT_FILTER: Filter = {
  levels: new Set(),
  providers: new Set(),
  language: "all",
  freeOnly: false,
  shortOnly: false,
};

export default function LearningPage() {
  const [skill, setSkill] = React.useState("Python");
  const [items, setItems] = React.useState<LearningResource[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [mode, setMode] = React.useState<"search" | "recommend">("search");
  const [filter, setFilter] = React.useState<Filter>(DEFAULT_FILTER);
  const [sort, setSort] = React.useState<SortKey>("rating");
  const [favorites, setFavorites] = React.useState<Set<string>>(new Set());

  // 收藏写入 localStorage
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("learning_favorites");
      if (raw) setFavorites(new Set(JSON.parse(raw)));
    } catch {
      /* ignore */
    }
  }, []);

  const persistFavorites = React.useCallback((next: Set<string>) => {
    setFavorites(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        "learning_favorites",
        JSON.stringify([...next]),
      );
    }
  }, []);

  const loadSearch = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await searchLearningResources(skill);
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [skill]);

  const loadRecommend = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const skills = skill
        .split(/[,，\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const rows = await recommendLearningResources(
        skills.length ? skills : ["Python"],
      );
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [skill]);

  React.useEffect(() => {
    void loadSearch();
  }, [loadSearch]);

  const submit = React.useCallback(async () => {
    if (mode === "search") await loadSearch();
    else await loadRecommend();
  }, [mode, loadSearch, loadRecommend]);

  const toggleFavorite = React.useCallback(
    (key: string) => {
      const next = new Set(favorites);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      persistFavorites(next);
    },
    [favorites, persistFavorites],
  );

  const filteredItems = React.useMemo(() => {
    let list = items;
    if (filter.levels.size) {
      list = list.filter((it) => filter.levels.has(it.level));
    }
    if (filter.providers.size) {
      list = list.filter((it) => filter.providers.has(it.provider));
    }
    if (filter.language !== "all") {
      list = list.filter((it) => it.language === filter.language);
    }
    if (filter.freeOnly) {
      list = list.filter((it) => !it.price || it.price === 0);
    }
    if (filter.shortOnly) {
      list = list.filter((it) => it.duration_hours <= 6);
    }
    const sorted = [...list];
    if (sort === "rating") {
      sorted.sort((a, b) => b.rating - a.rating);
    } else if (sort === "duration_asc") {
      sorted.sort((a, b) => a.duration_hours - b.duration_hours);
    } else if (sort === "duration_desc") {
      sorted.sort((a, b) => b.duration_hours - a.duration_hours);
    } else if (sort === "price") {
      sorted.sort((a, b) => (a.price ?? 0) - (b.price ?? 0));
    } else if (sort === "title") {
      sorted.sort((a, b) => a.title.localeCompare(b.title));
    }
    return sorted;
  }, [items, filter, sort]);

  // ---- stats ----
  const stats = React.useMemo(() => {
    if (filteredItems.length === 0) {
      return {
        count: 0,
        avgHours: 0,
        avgRating: 0,
        free: 0,
        topPicks: [] as LearningResource[],
      };
    }
    const totalHours = filteredItems.reduce(
      (a, b) => a + (b.duration_hours ?? 0),
      0,
    );
    const rated = filteredItems.filter((r) => r.rating > 0);
    const avgRating = rated.length
      ? rated.reduce((a, b) => a + b.rating, 0) / rated.length
      : 0;
    const free = filteredItems.filter((r) => !r.price || r.price === 0).length;
    const topPicks = [...filteredItems]
      .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
      .slice(0, 3);
    return {
      count: filteredItems.length,
      avgHours: totalHours / filteredItems.length,
      avgRating,
      free,
      topPicks,
    };
  }, [filteredItems]);

  const gapChips = React.useMemo(
    () =>
      skill
        .split(/[,，\s]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    [skill],
  );

  const resetFilters = () => setFilter(DEFAULT_FILTER);

  const toolbar = (
    <Button asChild size="sm" variant="outline">
      <Link href="/jobseeker/plan">
        <ArrowLeft className="mr-1.5 size-3.5" /> 返回规划
      </Link>
    </Button>
  );

  return (
    <ErrorBoundary>(<TremorShell
        title="学习资源"
        subtitle="聚合 Coursera / 极客时间 / 掘金小册 / 慕课网 / Bilibili 公开课"
        badge={`${stats.count} 条结果`}
        toolbar={toolbar}
      >
        {/* mode + input */}
        <Card>
          <CardContent className="flex flex-wrap items-end gap-3 p-4">
            <div className="min-w-[220px] flex-1">
              <label className="mb-1 block text-xs text-muted-foreground">
                {mode === "search" ? "技能关键词" : "Gap skills (逗号分隔)"}
              </label>
              <Input
                value={skill}
                onChange={(e) => setSkill(e.target.value)}
                placeholder={
                  mode === "search"
                    ? "例:Python / FastAPI / Kubernetes"
                    : "例:Python, FastAPI, Kubernetes"
                }
              />
              {gapChips.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {gapChips.map((g) => (
                    <Badge
                      key={g}
                      variant="secondary"
                      className="gap-1 bg-violet-100 text-violet-700"
                    >
                      <Tag className="size-3" />
                      {g}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant={mode === "search" ? "default" : "outline"}
                onClick={() => setMode("search")}
              >
                <BookOpenCheck className="mr-1.5 size-3.5" /> 单技能搜索
              </Button>
              <Button
                size="sm"
                variant={mode === "recommend" ? "default" : "outline"}
                onClick={() => setMode("recommend")}
              >
                <Sparkles className="mr-1.5 size-3.5" /> Gap 推荐
              </Button>
            </div>
            <Button onClick={() => void submit()} disabled={loading}>
              {loading ? (
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              ) : (
                <Filter className="mr-1.5 size-3.5" />
              )}
              刷新
            </Button>
          </CardContent>
        </Card>
        {error && (
          <Card className="border-rose-200 bg-rose-50/60">
            <CardContent className="flex items-center gap-3 p-3 text-sm text-rose-700">
              <AlertTriangle className="size-4" />
              <span>{error}</span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                onClick={() => void submit()}
              >
                重试
              </Button>
            </CardContent>
          </Card>
        )}
        {/* KPI band */}
        <TremorKpiGrid>
          <TremorKpiCard
            title="结果数"
            value={stats.count}
            unit="条"
            helper={mode === "recommend" ? "基于 Gap 推荐" : "基于关键词搜索"}
          />
          <TremorKpiCard
            title="平均时长"
            value={stats.avgHours ? stats.avgHours.toFixed(1) : "—"}
            unit={stats.avgHours ? "h" : ""}
            helper="完成课程平均所需"
          />
          <TremorKpiCard
            title="平均评分"
            value={stats.avgRating ? stats.avgRating.toFixed(1) : "—"}
            helper={stats.avgRating ? "≥ 4.0 为优质" : "无评分数据"}
          />
          <TremorKpiCard
            title="免费资源"
            value={stats.free}
            unit="条"
            helper="筛选可降低成本"
          />
        </TremorKpiGrid>
        <Tabs defaultValue="results" className="space-y-4">
          <TabsList className="flex flex-wrap">
            <TabsTrigger value="results">
              <BookOpenCheck className="mr-1.5 size-3.5" /> 资源列表
            </TabsTrigger>
            <TabsTrigger value="picks">
              <Award className="mr-1.5 size-3.5" /> Top 3
            </TabsTrigger>
            <TabsTrigger value="path">
              <Lightbulb className="mr-1.5 size-3.5" /> 学习路径
            </TabsTrigger>
          </TabsList>

          <TabsContent value="results">
            <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
              {/* filters */}
              <TremorPanel
                title="筛选"
                description="按 level / 来源 / 语言 / 价格"
                actions={
                  <Button size="sm" variant="ghost" onClick={resetFilters}>
                    清空
                  </Button>
                }
              >
                <FilterGroup
                  label="难度"
                  options={LEVELS.map((l) => ({ key: l.key, label: l.label }))}
                  active={filter.levels}
                  onToggle={(k) => toggleSet(filter.levels, k, (s) => ({ ...filter, levels: s }))}
                />
                <FilterGroup
                  label="来源"
                  options={PROVIDERS.map((p) => ({ key: p.key, label: p.label }))}
                  active={filter.providers}
                  onToggle={(k) => toggleSet(filter.providers, k, (s) => ({ ...filter, providers: s }))}
                />
                <div className="mt-3">
                  <p className="text-xs font-medium text-slate-700">语言</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(
                      [
                        { key: "all", label: "全部" },
                        { key: "zh", label: "中文" },
                        { key: "en", label: "英文" },
                      ] as const
                    ).map((opt) => (
                      <button
                        key={opt.key}
                        onClick={() => setFilter({ ...filter, language: opt.key })}
                        className={cn(
                          "rounded border px-2 py-0.5 text-[11px] transition",
                          filter.language === opt.key
                            ? "border-blue-300 bg-blue-50 text-blue-700"
                            : "border-slate-200 text-slate-600 hover:bg-slate-50",
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="mt-3 space-y-1">
                  <Toggle
                    label="仅免费"
                    checked={filter.freeOnly}
                    onChange={(v) => setFilter({ ...filter, freeOnly: v })}
                  />
                  <Toggle
                    label="短时 (< 6h)"
                    checked={filter.shortOnly}
                    onChange={(v) => setFilter({ ...filter, shortOnly: v })}
                  />
                </div>
              </TremorPanel>

              {/* results */}
              <TremorPanel
                title="推荐结果"
                description={`${filteredItems.length} / ${items.length} 条匹配`}
                actions={
                  <div className="flex items-center gap-1 text-xs">
                    <span className="text-muted-foreground">排序:</span>
                    {(
                      [
                        { key: "rating", label: "评分" },
                        { key: "duration_asc", label: "时长 ↑" },
                        { key: "duration_desc", label: "时长 ↓" },
                        { key: "price", label: "价格" },
                        { key: "title", label: "标题" },
                      ] as const
                    ).map((s) => (
                      <button
                        key={s.key}
                        onClick={() => setSort(s.key)}
                        className={cn(
                          "rounded border px-2 py-0.5 transition",
                          sort === s.key
                            ? "border-blue-300 bg-blue-50 text-blue-700"
                            : "border-slate-200 text-slate-600 hover:bg-slate-50",
                        )}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                }
              >
                {loading ? (
                  <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
                    <Loader2 className="size-4 animate-spin" /> 加载中…
                  </div>
                ) : (
                  <LearningResourceList
                    items={filteredItems.map((it) => ({
                      ...it,
                      // 用 title+provider 作 key 时通过 favorites 标记
                    }))}
                    emptyText={
                      mode === "search"
                        ? "未找到相关资源 — 试试别的关键词或清空筛选"
                        : "未找到推荐资源 — 调整 Gap skills 或清空筛选"
                    }
                  />
                )}
              </TremorPanel>
            </div>
          </TabsContent>

          <TabsContent value="picks">
            <TremorPanel
              title="Top 3 高分精选"
              description="基于当前筛选下评分排序的前三条"
            >
              {stats.topPicks.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  暂无数据
                </p>
              ) : (
                <div className="grid gap-3 md:grid-cols-3">
                  {stats.topPicks.map((r, i) => {
                    const key = `${r.provider}-${r.title}`;
                    const isFav = favorites.has(key);
                    return (
                      <Card
                        key={key}
                        className="overflow-hidden border-amber-200 bg-gradient-to-br from-amber-50 to-white"
                      >
                        <CardContent className="space-y-2 p-4">
                          <div className="flex items-start gap-2">
                            <span className="grid size-7 place-items-center rounded-full bg-amber-500 text-xs font-bold text-white">
                              {i + 1}
                            </span>
                            <p className="line-clamp-2 flex-1 text-sm font-semibold text-slate-800">
                              {r.title}
                            </p>
                            <button
                              onClick={() => toggleFavorite(key)}
                              aria-label="收藏"
                              className="text-slate-400 hover:text-rose-500"
                            >
                              <Heart
                                className={cn(
                                  "size-4",
                                  isFav && "fill-rose-500 text-rose-500",
                                )}
                              />
                            </button>
                          </div>
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <Badge variant="secondary">{r.provider}</Badge>
                            <span className="inline-flex items-center gap-1 text-amber-600">
                              <Star className="size-3 fill-current" />
                              {r.rating?.toFixed(1) ?? "—"}
                            </span>
                            <span className="inline-flex items-center gap-1 text-muted-foreground">
                              <Clock className="size-3" />
                              {r.duration_hours?.toFixed(1) ?? "—"}h
                            </span>
                            <span className="text-muted-foreground">
                              {r.price && r.price > 0 ? `¥${r.price}` : "免费"}
                            </span>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            className="w-full"
                            onClick={() =>
                              r.url && window.open(r.url, "_blank", "noreferrer")
                            }
                          >
                            打开
                          </Button>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </TremorPanel>
          </TabsContent>

          <TabsContent value="path">
            <TremorPanel
              title="学习路径建议"
              description="基于当前关键词自动生成的速记路径"
            >
              <LearningPath skill={skill} chips={gapChips} />
            </TremorPanel>
          </TabsContent>
        </Tabs>
      </TremorShell>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function FilterGroup({
  label,
  options,
  active,
  onToggle,
}: {
  label: string;
  options: { key: string; label: string }[];
  active: Set<string>;
  onToggle: (key: string) => void;
}) {
  return (
    <div className="mt-3 first:mt-0">
      <p className="text-xs font-medium text-slate-700">{label}</p>
      <div className="mt-1 flex flex-wrap gap-1">
        {options.map((opt) => (
          <button
            key={opt.key}
            onClick={() => onToggle(opt.key)}
            className={cn(
              "rounded border px-2 py-0.5 text-[11px] transition",
              active.has(opt.key)
                ? "border-blue-300 bg-blue-50 text-blue-700"
                : "border-slate-200 text-slate-600 hover:bg-slate-50",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={cn(
        "flex w-full items-center justify-between rounded-md border px-2 py-1 text-xs transition",
        checked
          ? "border-blue-300 bg-blue-50 text-blue-700"
          : "border-slate-200 text-slate-600 hover:bg-slate-50",
      )}
    >
      <span>{label}</span>
      <span
        className={cn(
          "inline-block size-2.5 rounded-full",
          checked ? "bg-blue-500" : "bg-slate-300",
        )}
      />
    </button>
  );
}

function toggleSet<T>(
  set: Set<string>,
  key: string,
  next: (s: Set<string>) => T,
): T {
  const cloned = new Set(set);
  if (cloned.has(key)) cloned.delete(key);
  else cloned.add(key);
  return next(cloned);
}

function LearningPath({
  skill,
  chips,
}: {
  skill: string;
  chips: string[];
}) {
  const focus = chips.length > 0 ? chips[0] : skill || "Python";
  const steps = [
    {
      title: "基础打底",
      desc: `了解 ${focus} 的核心概念 / 语法 / 工具链`,
      hint: "入门课程 · 0-4 周",
      color: "from-emerald-50 to-emerald-100 border-emerald-200",
    },
    {
      title: "项目实战",
      desc: `用 ${focus} 搭建 1-2 个可演示的小项目`,
      hint: "进阶课程 · 4-10 周",
      color: "from-sky-50 to-sky-100 border-sky-200",
    },
    {
      title: "深入原理",
      desc: `阅读 ${focus} 源码 / RFC / 论文,理解底层原理`,
      hint: "高级课程 · 10-20 周",
      color: "from-violet-50 to-violet-100 border-violet-200",
    },
    {
      title: "沉淀分享",
      desc: `输出 ${focus} 学习笔记 / 博客 / 内部分享`,
      hint: "持续 · 20 周+",
      color: "from-amber-50 to-amber-100 border-amber-200",
    },
  ];
  return (
    <ol className="relative space-y-3 border-l-2 border-slate-200 pl-4">
      {steps.map((s, i) => (
        <li key={i} className="relative">
          <span className="absolute -left-[22px] grid size-5 place-items-center rounded-full bg-slate-900 text-[10px] font-bold text-white">
            {i + 1}
          </span>
          <div className={cn("rounded-lg border bg-gradient-to-br p-3", s.color)}>
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-800">{s.title}</p>
              <Badge variant="outline" className="text-[10px]">
                {s.hint}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-slate-600">{s.desc}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
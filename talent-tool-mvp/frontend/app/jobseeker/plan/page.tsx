"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — 职业规划主页 (T3605/T3606)
 *
 *  - 头部 KPI (目标 / 学习路径 / 推荐岗位 / 缺口)
 *  - 三段时间线 (短/中/长期)
 *  - 自研 SVG 甘特图 (PlanGantt 沿用 + 进度汇总)
 *  - 推荐岗位 (Top 5)
 *  - 技能缺口 + gap 技能 chip 链接到学习页
 *  - AI 调整建议 (AdjustmentSuggestionList)
 *  - 每日打卡 (CheckinModal)
 *  - 跳转到 子页: 进度 / 市场 / 学习
 *
 * 复用组件:
 *  - PlanGantt, AdjustmentSuggestionList, CheckinModal
 *  - TremorKpiCard / TremorKpiGrid / TremorPanel / TremorShell
 *  - Badge / Button / Card
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Sparkles,
  Target,
  Compass,
  Briefcase,
  GraduationCap,
  BookOpenCheck,
  ListChecks,
  CheckCircle2,
  Clock,
  Lightbulb,
  ExternalLink,
  Flame,
  TrendingUp,
  AlertTriangle,
  Wand2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  PlanGantt,
  type GanttTask,
  type GanttMilestone,
} from "@/components/plan/PlanGantt";
import {
  AdjustmentSuggestionList,
  type AdjustmentSuggestion,
} from "@/components/plan/AdjustmentSuggestion";
import { CheckinModal } from "@/components/plan/CheckinModal";
import {
  TremorKpiCard,
  TremorKpiGrid,
  TremorPanel,
  TremorShell,
} from "@/components/charts/tremor-shell";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

interface PlanItem {
  title: string;
  detail?: string;
  duration?: string;
  priority?: string;
}

interface RecommendedRole {
  title: string;
  reason?: string;
  match_score?: number;
}

interface SkillGap {
  skill: string;
  importance: "high" | "medium" | "low" | string;
}

interface PlanMilestone {
  title: string;
  target_date: string;
  completed: boolean;
}

interface Plan {
  short_term: PlanItem[];
  mid_term: PlanItem[];
  long_term: PlanItem[];
  learning_paths: Array<{ title: string; items?: string[]; duration?: string }>;
  recommended_roles: RecommendedRole[];
  market_insights: {
    salary_trends?: Array<{ period: string; median_k: number; sample_size?: number | null }>;
    hot_skills?: Array<{ skill: string; demand_score: number }>;
    sample_jobs?: unknown[];
    provider?: string;
  } | null;
  skill_gaps: SkillGap[];
  milestones: PlanMilestone[];
  ai_suggestions?: AdjustmentSuggestion[];
}

interface PlanProgressLite {
  overall_progress: number;
  items: Array<{
    title: string;
    progress: number;
    completed: boolean;
    duration?: string;
    bucket: "short" | "mid" | "long";
    priority?: string;
  }>;
}

async function authHeaders(): Promise<HeadersInit> {
  if (typeof window !== "undefined") {
    const legacy = window.localStorage.getItem("sb_token");
    if (legacy) return { Authorization: `Bearer ${legacy}` };
  }
  try {
    const { createClient } = await import("@/lib/supabase");
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {
    /* ignore */
  }
  return {};
}

const BUCKET_TONE: Record<string, string> = {
  short: "from-emerald-50 to-emerald-100 border-emerald-200",
  mid: "from-sky-50 to-blue-100 border-blue-200",
  long: "from-violet-50 to-purple-100 border-violet-200",
};

const BUCKET_LABEL: Record<string, string> = {
  short: "短期 · 3 个月内",
  mid: "中期 · 1 年内",
  long: "长期 · 3 年+",
};

const BUCKET_ICON: Record<string, React.ReactNode> = {
  short: <ListChecks className="size-4 text-emerald-600" />,
  mid: <Compass className="size-4 text-blue-600" />,
  long: <Sparkles className="size-4 text-violet-600" />,
};

const IMPORTANCE_TONE: Record<string, string> = {
  high: "bg-rose-100 text-rose-700 ring-1 ring-rose-200",
  medium: "bg-amber-100 text-amber-700 ring-1 ring-amber-200",
  low: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",
};

export default function CareerPlanPage() {
  const router = useRouter();
  const [plan, setPlan] = React.useState<Plan | null>(null);
  const [progress, setProgress] = React.useState<PlanProgressLite | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [checkinOpen, setCheckinOpen] = React.useState(false);
  const [userId, setUserId] = React.useState<string>("demo-user");

  // 加载已有规划 + 进度
  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        // resolve userId
        try {
          const { createClient } = await import("@/lib/supabase");
          const supabase = createClient();
          const { data } = await supabase.auth.getSession();
          const uid = data.session?.user?.id;
          if (uid) {
            if (!cancelled) setUserId(uid);
          } else if (typeof window !== "undefined") {
            const dev = window.localStorage.getItem("dev_user_id");
            if (!cancelled && dev) setUserId(dev);
          }
        } catch {
          /* ignore */
        }

        const headers = await authHeaders();
        const resp = await fetch(`${API_BASE}/api/career-plan/current`, {
          headers,
          cache: "no-store",
        });
        if (resp.ok) {
          const json = (await resp.json()) as Plan;
          if (!cancelled && json?.short_term) setPlan(json);
        }
        // 进度
        try {
          const presp = await fetch(`${API_BASE}/api/plan/progress/${encodeURIComponent(userId)}`, {
            headers,
            cache: "no-store",
          });
          if (presp.ok) {
            const pj = (await presp.json()) as PlanProgressLite;
            if (!cancelled) setProgress(pj);
          }
        } catch {
          /* progress optional */
        }
      } catch {
        /* first-time visitors without a plan will see the empty state */
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const generate = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const headers = await authHeaders();
      const r = await fetch(`${API_BASE}/api/career-plan/generate`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
      });
      if (!r.ok) throw new Error(`生成失败 ${r.status}`);
      const data = (await r.json()) as { plan?: Plan };
      if (data.plan) {
        setPlan(data.plan);
        // 刷新进度
        try {
          const pr = await fetch(`${API_BASE}/api/plan/progress/${encodeURIComponent(userId)}`, {
            headers,
            cache: "no-store",
          });
          if (pr.ok) setProgress((await pr.json()) as PlanProgressLite);
        } catch {
          /* ignore */
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败,请稍后再试");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  // ----- 派生数据 -----
  const buckets = React.useMemo(() => {
    if (!plan) return null;
    return [
      { key: "short" as const, items: plan.short_term ?? [] },
      { key: "mid" as const, items: plan.mid_term ?? [] },
      { key: "long" as const, items: plan.long_term ?? [] },
    ];
  }, [plan]);

  const ganttTasks: GanttTask[] = React.useMemo(() => {
    const out: GanttTask[] = [];
    const progressByTitle = new Map(
      (progress?.items ?? []).map((i) => [i.title, i]),
    );
    for (const bucket of ["short", "mid", "long"] as const) {
      const items =
        bucket === "short"
          ? plan?.short_term ?? []
          : bucket === "mid"
            ? plan?.mid_term ?? []
            : plan?.long_term ?? [];
      for (const it of items) {
        const p = progressByTitle.get(it.title);
        out.push({
          title: it.title,
          progress: p?.progress ?? 0,
          completed: p?.completed ?? false,
          duration: it.duration,
          bucket,
          priority: it.priority,
        });
      }
    }
    return out;
  }, [plan, progress]);

  const ganttMilestones: GanttMilestone[] = React.useMemo(() => {
    return (plan?.milestones ?? []).map((m) => ({
      title: m.title,
      target_date: m.target_date,
      completed: m.completed,
    }));
  }, [plan]);

  const checkinItems = React.useMemo(() => {
    return (progress?.items ?? ganttTasks).map((it) => ({
      title: "title" in it ? it.title : "",
    }));
  }, [progress, ganttTasks]);

  const onCheckin = React.useCallback(
    async (itemTitle: string, note: string) => {
      const headers = await authHeaders();
      await fetch(`${API_BASE}/api/plan/checkin`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          item_title: itemTitle,
          progress_delta: 0.1,
          note,
        }),
      });
      // 刷新进度
      try {
        const pr = await fetch(`${API_BASE}/api/plan/progress/${encodeURIComponent(userId)}`, {
          headers,
          cache: "no-store",
        });
        if (pr.ok) setProgress((await pr.json()) as PlanProgressLite);
      } catch {
        /* ignore */
      }
    },
    [userId],
  );

  const overallPct = progress?.overall_progress
    ? Math.round(progress.overall_progress * 100)
    : 0;

  const suggestions: AdjustmentSuggestion[] =
    plan?.ai_suggestions && plan.ai_suggestions.length > 0
      ? plan.ai_suggestions
      : deriveSuggestions(plan, progress);

  // ----- render -----
  const toolbar = (
    <>
      <Button
        onClick={() => setCheckinOpen(true)}
        variant="outline"
        size="sm"
        disabled={!plan}
      >
        <Flame className="mr-1.5 size-3.5" /> 每日打卡
      </Button>
      <Button
        onClick={() => void generate()}
        disabled={loading}
        size="sm"
      >
        <Wand2 className="mr-1.5 size-3.5" />
        {loading ? "生成中..." : plan ? "重新生成" : "生成规划"}
      </Button>
    </>
  );

  return (
    <ErrorBoundary>(<TremorShell
        title="🎯 职业规划"
        subtitle="智能体基于你的画像、需求和市场行情生成多层次规划"
        badge={plan ? "已生成" : "待生成"}
        toolbar={toolbar}
      >
        {!plan && !loading && (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
              <Sparkles className="size-8 text-violet-500" />
              <p className="max-w-md text-sm text-slate-500">
                还没有可用的职业规划。点击右上角「生成规划」,智能体将根据你的画像、需求缺口与最新市场行情,
                拆解出短/中/长期目标、推荐岗位、补充技能缺口,并自动生成打卡与调整建议。
              </p>
              <Button onClick={() => void generate()} disabled={loading}>
                <Wand2 className="mr-1.5 size-3.5" /> 立即生成
              </Button>
            </CardContent>
          </Card>
        )}
        {loading && !plan && (
          <Card>
            <CardContent className="py-10 text-center text-sm text-slate-500">
              智能体正在拆解目标 · 评估缺口 · 起草规划,大约需要 10-30 秒…
            </CardContent>
          </Card>
        )}
        {error && (
          <Card className="border-rose-200 bg-rose-50/60">
            <CardContent className="flex items-center gap-3 p-3 text-sm text-rose-700">
              <AlertTriangle className="size-4" />
              <span>{error}</span>
              <Button size="sm" variant="outline" className="ml-auto" onClick={() => void generate()}>
                重试
              </Button>
            </CardContent>
          </Card>
        )}
        {plan && (
          <>
            {/* KPI band */}
            <TremorKpiGrid>
              <TremorKpiCard
                title="总体进度"
                value={`${overallPct}%`}
                helper={overallPct > 0 ? "继续按计划推进" : "尚无进度"}
                delta={overallPct > 0 ? overallPct : undefined}
              />
              <TremorKpiCard
                title="行动计划"
                value={
                  (plan.short_term?.length ?? 0) +
                  (plan.mid_term?.length ?? 0) +
                  (plan.long_term?.length ?? 0)
                }
                unit="项"
                helper={`短期 ${plan.short_term?.length ?? 0} · 中期 ${plan.mid_term?.length ?? 0} · 长期 ${plan.long_term?.length ?? 0}`}
              />
              <TremorKpiCard
                title="推荐岗位"
                value={plan.recommended_roles?.length ?? 0}
                unit="个"
                helper={
                  plan.recommended_roles?.length
                    ? `匹配度 ${Math.round(
                        Math.max(
                          ...plan.recommended_roles.map((r) => r.match_score ?? 0),
                        ) * 100,
                      )}%`
                    : "尚未推荐"
                }
              />
              <TremorKpiCard
                title="技能缺口"
                value={plan.skill_gaps?.length ?? 0}
                unit="项"
                helper={`${plan.skill_gaps?.filter((g) => g.importance === "high").length ?? 0} 项高优先级`}
              />
            </TremorKpiGrid>

            {/* tabs */}
            <Tabs defaultValue="overview" className="space-y-4">
              <TabsList className="flex flex-wrap">
                <TabsTrigger value="overview">
                  <Target className="mr-1.5 size-3.5" /> 概览
                </TabsTrigger>
                <TabsTrigger value="gantt">
                  <Clock className="mr-1.5 size-3.5" /> 甘特图
                </TabsTrigger>
                <TabsTrigger value="suggestions">
                  <Lightbulb className="mr-1.5 size-3.5" /> AI 建议
                </TabsTrigger>
                <TabsTrigger value="subnav">
                  <ExternalLink className="mr-1.5 size-3.5" /> 子页面
                </TabsTrigger>
              </TabsList>

              {/* ====== overview ====== */}
              <TabsContent value="overview">
                <div className="grid gap-4 lg:grid-cols-3">
                  {buckets?.map((b) => (
                    <BucketColumn key={b.key} bucket={b.key} items={b.items} />
                  ))}
                </div>

                {/* recommended roles + skill gaps */}
                <div className="mt-4 grid gap-4 lg:grid-cols-3">
                  <TremorPanel
                    title="推荐岗位"
                    description="基于画像 + 缺口匹配排序"
                    className="lg:col-span-2"
                  >
                    {plan.recommended_roles?.length ? (
                      <ul className="space-y-2">
                        {plan.recommended_roles.slice(0, 5).map((r, i) => {
                          const pct = Math.round((r.match_score ?? 0) * 100);
                          return (
                            <li
                              key={`${r.title}-${i}`}
                              className="flex items-center gap-3 rounded-lg border bg-white/60 p-3 transition hover:bg-white"
                            >
                              <Briefcase className="size-4 text-blue-500" />
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-medium text-slate-800">
                                  {r.title}
                                </p>
                                {r.reason && (
                                  <p className="line-clamp-1 text-xs text-muted-foreground">
                                    {r.reason}
                                  </p>
                                )}
                              </div>
                              <div className="flex w-24 flex-col items-end gap-1">
                                <span className="text-sm font-semibold text-blue-600 tabular-nums">
                                  {pct}%
                                </span>
                                <Progress value={pct} className="h-1" />
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    ) : (
                      <p className="py-6 text-center text-xs text-muted-foreground">
                        暂无推荐岗位
                      </p>
                    )}
                  </TremorPanel>

                  <TremorPanel
                    title="技能缺口"
                    description="按重要性排序"
                    actions={
                      plan.skill_gaps?.length ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => router.push("/jobseeker/plan/learning")}
                        >
                          <BookOpenCheck className="mr-1.5 size-3.5" /> 去学习
                        </Button>
                      ) : null
                    }
                  >
                    {plan.skill_gaps?.length ? (
                      <ul className="space-y-2">
                        {plan.skill_gaps.map((g, i) => (
                          <li
                            key={`${g.skill}-${i}`}
                            className="flex items-center justify-between gap-2 rounded-md border bg-white/40 px-2 py-1.5 text-sm"
                          >
                            <span className="truncate font-medium text-slate-800">
                              {g.skill}
                            </span>
                            <span
                              className={cn(
                                "rounded-full px-2 py-0.5 text-[11px] font-medium",
                                IMPORTANCE_TONE[g.importance] ?? IMPORTANCE_TONE.low,
                              )}
                            >
                              {g.importance}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="py-6 text-center text-xs text-muted-foreground">
                        没有明显缺口,继续巩固即可
                      </p>
                    )}
                  </TremorPanel>
                </div>
              </TabsContent>

              {/* ====== gantt ====== */}
              <TabsContent value="gantt">
                <div className="grid gap-4 lg:grid-cols-3">
                  <TremorPanel
                    title="规划甘特图"
                    description="横轴时间, 纵轴任务. 蓝/绿 = 进行中/已完成, 红 = 高优先级"
                    className="lg:col-span-2"
                  >
                    <PlanGantt tasks={ganttTasks} milestones={ganttMilestones} />
                  </TremorPanel>
                  <TremorPanel
                    title="里程碑"
                    description="关键节点到期提醒"
                  >
                    {plan.milestones?.length ? (
                      <ul className="space-y-2">
                        {plan.milestones.map((m, i) => (
                          <li
                            key={`${m.title}-${i}`}
                            className="flex items-start gap-2 rounded-md border bg-white/60 p-2 text-xs"
                          >
                            {m.completed ? (
                              <CheckCircle2 className="mt-0.5 size-4 text-emerald-500" />
                            ) : (
                              <Clock className="mt-0.5 size-4 text-amber-500" />
                            )}
                            <div className="flex-1">
                              <p className="font-medium text-slate-800">{m.title}</p>
                              <p className="text-[11px] text-muted-foreground">
                                目标 {m.target_date}
                              </p>
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="py-6 text-center text-xs text-muted-foreground">
                        暂无里程碑
                      </p>
                    )}
                  </TremorPanel>
                </div>
              </TabsContent>

              {/* ====== suggestions ====== */}
              <TabsContent value="suggestions">
                <div className="grid gap-4 lg:grid-cols-2">
                  <TremorPanel
                    title="AI 调整建议"
                    description="基于进度与缺口动态生成的建议"
                  >
                    <AdjustmentSuggestionList suggestions={suggestions} />
                  </TremorPanel>
                  <TremorPanel
                    title="学习路径"
                    description="按缺口映射到对应课程/任务"
                  >
                    {plan.learning_paths?.length ? (
                      <ul className="space-y-2">
                        {plan.learning_paths.map((lp, i) => (
                          <li
                            key={`${lp.title}-${i}`}
                            className="rounded-md border bg-white/60 p-3"
                          >
                            <div className="flex items-center gap-2">
                              <GraduationCap className="size-4 text-blue-500" />
                              <span className="text-sm font-medium text-slate-800">
                                {lp.title}
                              </span>
                              {lp.duration && (
                                <Badge variant="outline" className="ml-auto text-[10px]">
                                  {lp.duration}
                                </Badge>
                              )}
                            </div>
                            {lp.items && lp.items.length > 0 && (
                              <ul className="mt-2 list-disc pl-5 text-xs text-muted-foreground">
                                {lp.items.map((it, k) => (
                                  <li key={k}>{it}</li>
                                ))}
                              </ul>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="py-6 text-center text-xs text-muted-foreground">
                        暂无学习路径
                      </p>
                    )}
                  </TremorPanel>
                </div>
              </TabsContent>

              {/* ====== subnav ====== */}
              <TabsContent value="subnav">
                <div className="grid gap-3 sm:grid-cols-3">
                  <SubnavCard
                    href="/jobseeker/plan/progress"
                    icon={<TrendingUp className="size-5 text-emerald-500" />}
                    title="执行进度"
                    desc="按里程碑 + 打卡记录"
                  />
                  <SubnavCard
                    href="/jobseeker/plan/market-insights"
                    icon={<Compass className="size-5 text-blue-500" />}
                    title="市场行情"
                    desc="薪资 · 趋势 · 热门技能"
                  />
                  <SubnavCard
                    href="/jobseeker/plan/learning"
                    icon={<BookOpenCheck className="size-5 text-violet-500" />}
                    title="学习资源"
                    desc="Gap 推荐 + 单技能搜索"
                  />
                </div>
              </TabsContent>
            </Tabs>
          </>
        )}
        <CheckinModal
          open={checkinOpen}
          onOpenChange={setCheckinOpen}
          items={checkinItems}
          onSubmit={onCheckin}
        />
      </TremorShell>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function BucketColumn({
  bucket,
  items,
}: {
  bucket: "short" | "mid" | "long";
  items: PlanItem[];
}) {
  return (
    <Card className={cn("border bg-gradient-to-br", BUCKET_TONE[bucket])}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          {BUCKET_ICON[bucket]} {BUCKET_LABEL[bucket]}
          <Badge variant="outline" className="ml-auto text-[10px]">
            {items.length} 项
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="py-6 text-center text-xs text-muted-foreground">暂未规划</p>
        ) : (
          <ul className="space-y-2">
            {items.map((it, i) => (
              <li
                key={`${it.title}-${i}`}
                className="rounded-md border border-white/60 bg-white/80 p-3 shadow-sm"
              >
                <p className="text-sm font-medium text-slate-900">{it.title}</p>
                {it.detail && (
                  <p className="mt-1 text-xs text-slate-600">{it.detail}</p>
                )}
                {it.duration && (
                  <p className="mt-1 inline-flex items-center gap-1 text-[11px] text-slate-500">
                    <Clock className="size-3" /> {it.duration}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function SubnavCard({
  href,
  icon,
  title,
  desc,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <Link href={href}>
      <Card className="group cursor-pointer transition hover:shadow-md">
        <CardContent className="flex items-start gap-3 p-4">
          <span className="grid size-10 place-items-center rounded-lg bg-white shadow-sm ring-1 ring-black/5">
            {icon}
          </span>
          <div className="flex-1">
            <p className="text-sm font-semibold text-slate-800">{title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">{desc}</p>
          </div>
          <ExternalLink className="size-4 text-slate-300 transition group-hover:text-slate-500" />
        </CardContent>
      </Card>
    </Link>
  );
}

function deriveSuggestions(
  plan: Plan | null,
  progress: PlanProgressLite | null,
): AdjustmentSuggestion[] {
  if (!plan) return [];
  const out: AdjustmentSuggestion[] = [];
  const overall = progress?.overall_progress ?? 0;
  if (overall > 0 && overall < 0.3) {
    out.push({
      kind: "shrink_scope",
      item: "整体推进",
      suggestion: "近期推进较慢,建议先把短期任务压缩到 2-3 项,聚焦核心目标。",
      priority: "medium",
    });
  }
  if ((plan.skill_gaps ?? []).filter((g) => g.importance === "high").length > 0) {
    out.push({
      kind: "add_bonus",
      item: "高优先级技能缺口",
      suggestion: "补充高频缺口技能将显著提升推荐岗位的匹配度。",
      priority: "high",
    });
  }
  if ((plan.long_term ?? []).length === 0) {
    out.push({
      kind: "add_bonus",
      item: "长期目标",
      suggestion: "缺少 3 年+ 长期目标,建议补一个愿景级方向(技术专家 / 管理 / 转型)。",
      priority: "low",
    });
  }
  return out;
}
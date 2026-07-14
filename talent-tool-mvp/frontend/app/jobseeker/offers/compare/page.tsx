"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — /jobseeker/offers/compare — 多 Offer 横向比较
 *
 * v9.1 改动:
 *  - 头部增加「差异亮点 + 风险提示」面板
 *  - OfferBreakdown 列表改为响应式 sticky grid
 *  - OfferComparisonTable 接入键盘 Tab 焦点 + 表格 + 雷达图
 *  - 排名表支持按列排序,带"市场分位/汇率"说明
 *  - 状态/错误用 AlertRole;无障碍的 skip 链接
 *
 * 数据接口保持不变
 */

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Award,
  CircleAlert,
  Scale,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { OfferBreakdown } from "@/components/OfferBreakdown";
import { OfferComparisonTable } from "@/components/OfferComparisonTable";

// ---------- 埋点 ----------
function track(event: string, props?: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  try {
    (window as unknown as { dataLayer: unknown[] }).dataLayer =
      (window as unknown as { dataLayer: unknown[] }).dataLayer || [];
    (window as unknown as { dataLayer: unknown[] }).dataLayer.push({
      event,
      ts: Date.now(),
      ...(props || {}),
    });
    fetch("/api/signals/track", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("sb_token") || ""}`,
      },
      body: JSON.stringify({ event, props: props || {} }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // 静默
  }
}

// ---------- 类型 ----------
interface AnnualTotal {
  location: string;
  currency: string;
  gross: number;
  tax: number;
  social: number;
  net: number;
  benefits: number;
  equity_pv: number;
  bonus: number;
  signing_bonus: number;
  total_comp: number;
  total_with_signing: number;
  monthly_net: number;
  effective_tax_rate: number;
}

interface OfferRow {
  id: string;
  title: string;
  company: string;
  location: string;
  currency: string;
}

interface CompareResult {
  offers: AnnualTotal[];
  best_by_total: string;
  best_by_monthly_net: string;
  radar: {
    base: number[];
    net_monthly: number[];
    equity_pv: number[];
    benefits: number[];
    total_comp: number[];
  };
  rank: Array<{
    rank: number;
    title: string;
    company: string;
    location: string;
    currency: string;
    total_comp_local: number;
    total_comp_cny_equiv: number;
    monthly_net_local: number;
    score_cny_equiv: number;
  }>;
}

// ---------- 主组件 ----------
function ComparePageInner() {
  const params = useSearchParams();
  const router = useRouter();

  const [result, setResult] = useState<CompareResult | null>(null);
  const [titles, setTitles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"rank" | "local" | "cny">("rank");

  useEffect(() => {
    const token = localStorage.getItem("sb_token") || "";
    const ids = (params?.get("ids") || "").split(",").filter(Boolean);
    if (ids.length < 2) {
      router.push("/jobseeker/offers");
      return;
    }
    track("compare_page_view", { offer_ids: ids, count: ids.length });
    (async () => {
      try {
        const fetched: OfferRow[] = [];
        for (const id of ids) {
          const r = await fetch(`/api/offers/${id}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (r.ok) {
            const d = await r.json();
            fetched.push(d.offer);
          }
        }
        setTitles(fetched.map((o) => o.title || o.company || "Offer"));

        const r2 = await fetch("/api/offers/compare", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ offer_ids: ids }),
        });
        if (!r2.ok) throw new Error(await r2.text());
        const data: CompareResult = await r2.json();
        setResult(data);
      } catch (e) {
        setError((e as Error)?.message || "比较失败");
      } finally {
        setLoading(false);
      }
    })();
  }, [params, router]);

  const sortedRank = useMemo(() => {
    if (!result) return [];
    const arr = [...result.rank];
    if (sortBy === "local") {
      arr.sort((a, b) => b.total_comp_local - a.total_comp_local);
    } else if (sortBy === "cny") {
      arr.sort((a, b) => b.total_comp_cny_equiv - a.total_comp_cny_equiv);
    }
    return arr;
  }, [result, sortBy]);

  // 简单风险提示:分散度 / 汇率影响
  const insights = useMemo(() => {
    if (!result) return null;
    const locations = new Set(result.rank.map((r) => r.location));
    const currencies = new Set(result.rank.map((r) => r.currency));
    const cnEquivs = result.rank.map((r) => r.total_comp_cny_equiv);
    const max = Math.max(...cnEquivs);
    const min = Math.min(...cnEquivs);
    const ratio = max > 0 ? max / min : 1;
    const list: { icon: React.ReactNode; text: string; tone: string }[] = [];
    list.push({
      icon: <Scale className="size-3.5" />,
      text: `${result.rank.length} 份 offer 跨 ${locations.size} 个地区、${currencies.size} 种币种`,
      tone: "text-slate-600",
    });
    if (ratio > 1.5) {
      list.push({
        icon: <CircleAlert className="size-3.5 text-amber-500" />,
        text: `最高与最低总包相差 ${ratio.toFixed(1)} 倍,建议结合「月到手 + 城市生活成本」综合判断`,
        tone: "text-amber-700",
      });
    } else {
      list.push({
        icon: <Sparkles className="size-3.5 text-emerald-500" />,
        text: `差距温和 (${ratio.toFixed(2)}x),可以重点比较「签字费 / 股权 / 福利」三块`,
        tone: "text-emerald-700",
      });
    }
    return list;
  }, [result]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-slate-400">
        正在计算多 offer 横向对比…
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="mx-auto max-w-md p-8 text-center"
        role="alert"
        aria-live="assertive"
      >
        <EmptyState
          title="比较失败"
          description={error}
          action={
            <Button asChild variant="outline">
              <Link href="/jobseeker/offers">返回 Offer 列表</Link>
            </Button>
          }
        />
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-indigo-50/30">
      <a
        href="#compare-table"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:rounded focus:bg-sky-600 focus:px-3 focus:py-1.5 focus:text-white"
      >
        跳到对比表
      </a>

      <header className="border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <nav
              aria-label="面包屑"
              className="flex items-center gap-1 text-xs text-slate-500"
            >
              <Link href="/jobseeker/dashboard" className="hover:text-slate-700">
                工作台
              </Link>
              <span aria-hidden>/</span>
              <Link href="/jobseeker/offers" className="hover:text-slate-700">
                Offer
              </Link>
              <span aria-hidden>/</span>
              <span className="text-slate-700">横向对比</span>
            </nav>
            <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold text-slate-900">
              <Scale className="size-5 text-indigo-600" aria-hidden /> Offer 横向对比
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              共 {titles.length} 份 · 按 CNY 等价综合衡量 + 雷达图多维透视
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" asChild>
              <Link href="/jobseeker/offers">
                <ArrowLeft className="mr-1.5 size-4" /> 返回管理
              </Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
        {/* 推荐 */}
        <section
          className="grid gap-4 md:grid-cols-2"
          aria-label="推荐结果"
        >
          <Recommend
            label="总包最佳"
            title={result.best_by_total}
            color="from-sky-500 to-indigo-600"
            sub="以 CNY 等价计算的总包年化"
            icon={<Award className="size-4" />}
          />
          <Recommend
            label="月到手最佳"
            title={result.best_by_monthly_net}
            color="from-emerald-500 to-teal-600"
            sub="实际现金流最友好的方案"
            icon={<Wallet2 className="size-4" />}
          />
        </section>

        {/* 差异亮点 */}
        {insights && insights.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingUp className="size-4 text-indigo-500" />
                差异亮点
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {insights.map((it, i) => (
                  <li
                    key={i}
                    className={`flex items-start gap-2 text-sm ${it.tone}`}
                  >
                    <span className="mt-0.5">{it.icon}</span>
                    <span>{it.text}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {/* 雷达 + 表格 */}
        <Card id="compare-table">
          <CardHeader>
            <CardTitle className="text-base">五维雷达 & 数据透视</CardTitle>
            <p className="text-xs text-slate-500">
              五个维度归一化到 0–100 区间,数字越大越优。
            </p>
          </CardHeader>
          <CardContent>
            <OfferComparisonTable titles={titles} radar={result.radar} />
          </CardContent>
        </Card>

        {/* 明细卡片 */}
        <section aria-label="各 offer 明细">
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-slate-600 uppercase">
            各项明细
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {result.offers.map((ot, idx) => (
              <OfferBreakdown
                key={idx}
                offer={{
                  ...ot,
                  title: titles[idx] || `Offer ${idx + 1}`,
                  company: result.rank[idx]?.company || "",
                }}
              />
            ))}
          </div>
        </section>

        {/* 排名表 */}
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <CardTitle className="text-base">综合排名</CardTitle>
                <p className="text-xs text-slate-500">
                  按 CNY 等价综合得分排序,本地币种仅作参考。
                </p>
              </div>
              <div
                className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-0.5 text-xs"
                role="tablist"
                aria-label="排名排序"
              >
                {(
                  [
                    { v: "rank", l: "综合" },
                    { v: "local", l: "本币" },
                    { v: "cny", l: "CNY 等价" },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.v}
                    role="tab"
                    aria-selected={sortBy === opt.v}
                    onClick={() => {
                      setSortBy(opt.v);
                      track("compare_sort_change", { by: opt.v });
                    }}
                    className={`rounded-full px-3 py-1 transition ${
                      sortBy === opt.v
                        ? "bg-white text-slate-900 shadow-sm"
                        : "text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    {opt.l}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" aria-label="综合排名表">
                <caption className="sr-only">
                  按所选排序方式展示多份 offer 的综合排名
                </caption>
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs tracking-wider text-slate-500 uppercase">
                    <th className="py-2 pr-2 text-center">#</th>
                    <th className="py-2 pr-2">Offer</th>
                    <th className="py-2 pr-2">地区</th>
                    <th className="py-2 pr-2 text-right">总包(本币)</th>
                    <th className="py-2 pr-2 text-right">折合 CNY</th>
                    <th className="py-2 pr-2 text-right">月到手(本币)</th>
                    <th className="py-2 pr-2 text-right">综合分</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedRank.map((r, idx) => (
                    <tr
                      key={r.rank}
                      className={`border-b border-slate-100 last:border-0 ${
                        idx === 0
                          ? "bg-gradient-to-r from-amber-50/60 to-transparent"
                          : ""
                      }`}
                    >
                      <td className="py-2 pr-2 text-center font-mono text-slate-500">
                        {idx + 1}
                      </td>
                      <td className="py-2 pr-2 font-medium text-slate-800">
                        {r.title}
                        {idx === 0 && (
                          <Badge
                            variant="secondary"
                            className="ml-1 rounded-full bg-amber-100 text-amber-700"
                          >
                            推荐
                          </Badge>
                        )}
                      </td>
                      <td className="py-2 pr-2 text-slate-600">
                        {r.location} / {r.currency}
                      </td>
                      <td className="py-2 pr-2 text-right tabular-nums">
                        {Math.round(r.total_comp_local).toLocaleString()}
                      </td>
                      <td className="py-2 pr-2 text-right font-semibold text-slate-900 tabular-nums">
                        ¥{Math.round(r.total_comp_cny_equiv).toLocaleString()}
                      </td>
                      <td className="py-2 pr-2 text-right text-slate-700 tabular-nums">
                        {Math.round(r.monthly_net_local).toLocaleString()}
                      </td>
                      <td className="py-2 pr-2 text-right text-indigo-700 tabular-nums">
                        {Math.round(r.score_cny_equiv)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

// ---------- 小型组件 ----------
function Recommend({
  label,
  title,
  color,
  sub,
  icon,
}: {
  label: string;
  title: string;
  color: string;
  sub: string;
  icon: React.ReactNode;
}) {
  return (
    <div
      className={`rounded-2xl bg-gradient-to-r ${color} p-5 text-white shadow-sm`}
    >
      <div className="flex items-center gap-2 text-xs uppercase opacity-90">
        {icon} {label}
      </div>
      <div className="mt-1 text-xl font-semibold">{title}</div>
      <div className="mt-0.5 text-xs opacity-85">{sub}</div>
    </div>
  );
}

function Wallet2({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M21 12V7a2 2 0 0 0-2-2H5a2 2 0 0 0 0 4h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7" />
      <circle cx="17" cy="13" r="1.5" fill="currentColor" />
    </svg>
  );
}

// ---------- Suspense 包裹 ----------
export default function ComparePage() {
  return (
    <ErrorBoundary>(<Suspense fallback={<div className="p-8 text-slate-400">加载中…</div>}>
        <ComparePageInner />
      </Suspense>)</ErrorBoundary>
  );
}

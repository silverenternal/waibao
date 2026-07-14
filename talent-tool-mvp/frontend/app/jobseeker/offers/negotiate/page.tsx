"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — /jobseeker/offers/negotiate — AI 谈判脚本生成
 *
 * v9.1 改动:
 *  - 头部增加 5 场景切换 (ScenarioTabs) 切到对应的 openai script
 *  - 引入 PersonaSelector 风格的人格提示卡片,引导进入模拟
 *  - 关键数字改用 KPI Tile,新增「一键复制 / 一键模拟」按钮组
 *  - 邮件模板与反例应对支持 tab 切换复制
 *  - 全程埋点
 *
 * 数据接口保持不变
 */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Clipboard,
  Mail,
  MessageCircle,
  MessageSquare,
  RefreshCcw,
  Sparkles,
  Wand2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { NegotiationScript } from "@/components/NegotiationScript";
import { SalaryChart } from "@/components/SalaryChart";

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

// ---------- 常量 ----------
const SCENARIO_LABELS: Record<string, { label: string; hint: string }> = {
  scenario_a_below_p50: {
    label: "市场分位偏低",
    hint: "用 p50 / p75 校准数字,谈 base 与签字费",
  },
  scenario_b_competing_offer: {
    label: "多家 offer 互 match",
    hint: "用 leverage 逼加速,谈速度与 bonus",
  },
  scenario_c_signing_bonus: {
    label: "争取签字费",
    hint: "在 base 不动的前提下争取一次性补贴",
  },
  scenario_d_equity_vesting: {
    label: "调整股权 / Vesting",
    hint: "谈 refresh、cliff 缩短、加速 vesting",
  },
  scenario_e_walkaway: {
    label: "走人底线",
    hint: "把走人阈值定到可承受最低线",
  },
};

const SCENARIO_ORDER: { key: string; emoji: string }[] = [
  { key: "scenario_a_below_p50", emoji: "📉" },
  { key: "scenario_b_competing_offer", emoji: "🤝" },
  { key: "scenario_c_signing_bonus", emoji: "💵" },
  { key: "scenario_d_equity_vesting", emoji: "📈" },
  { key: "scenario_e_walkaway", emoji: "🚪" },
];

const MARKET_ROLES = [
  { value: "backend_engineer", label: "后端工程师" },
  { value: "frontend_engineer", label: "前端工程师" },
  { value: "fullstack_engineer", label: "全栈工程师" },
  { value: "data_scientist", label: "数据科学家" },
  { value: "product_manager", label: "产品经理" },
  { value: "data_engineer", label: "数据工程师" },
];

const PERSONA_HINTS = [
  { id: "warm", emoji: "🌸", label: "友好型 HR", desc: "氛围型" },
  { id: "data", emoji: "📊", label: "数据型 HR", desc: "市场派" },
  { id: "tough", emoji: "🧱", label: "强硬派 HR", desc: "预算派" },
];

// ---------- 主组件 ----------
interface NegotiationScriptPayload {
  offer_title?: string;
  region?: string;
  market_band?: number[];
  currency?: string;
  current_total?: number;
  target_total?: number;
  walkaway_threshold?: number;
  percent_in_market?: number;
  overall_advice?: string;
  talking_points?: string[];
  email_template?: string;
  counter_examples?: string[];
  tactics?: { title: string; rationale: string; expected_uplift_pct: number; risk: string }[];
  next_steps?: string[];
  provider?: string;
  recommendation?: string;
}

function NegotiatePageInner() {
  const params = useSearchParams();
  const offerId = params?.get("id") || "";

  const [marketRole, setMarketRole] = useState("backend_engineer");
  const [scenario, setScenario] = useState<string>("scenario_a_below_p50");
  const [loading, setLoading] = useState(true);
  const [script, setScript] = useState<NegotiationScriptPayload | null>(null);
  const [offer, setOffer] = useState<{ title?: string; base_salary?: number; currency?: string; location?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<null | "email" | "talking">(null);

  useEffect(() => {
    if (!offerId) return;
    const token = localStorage.getItem("sb_token") || "";
    track("negotiate_page_view", { offer_id: offerId });
    (async () => {
      try {
        const r = await fetch(`/api/offers/${offerId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!r.ok) throw new Error("未找到 Offer");
        const d = await r.json();
        setOffer(d.offer);
        await loadScript(marketRole, scenario);
      } catch (e) {
        setError((e as Error)?.message || "加载失败");
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offerId]);

  const loadScript = useCallback(
    async (role: string, sc: string) => {
      try {
        const token = localStorage.getItem("sb_token") || "";
        const r = await fetch(`/api/offers/${offerId}/negotiate`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            market_role: role,
            language: "zh",
            scenario: sc,
          }),
        });
        if (!r.ok) throw new Error(await r.text());
        const data = await r.json();
        setScript(data);
        track("negotiate_script_loaded", {
          offer_id: offerId,
          market_role: role,
          scenario: sc,
          recommendation: data?.recommendation || "unknown",
        });
      } catch (e) {
        setError((e as Error)?.message || "生成谈判脚本失败");
      }
    },
    [offerId]
  );

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    await loadScript(marketRole, scenario);
    setLoading(false);
  }, [loadScript, marketRole, scenario]);

  const copy = useCallback(async (text: string, kind: "email" | "talking") => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(kind);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      setCopied(null);
    }
  }, []);

  if (!offerId) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-6">
        <Card className="max-w-md">
          <CardContent className="space-y-3 p-6 text-center">
            <p className="text-rose-600">缺少 Offer ID</p>
            <Button asChild>
              <Link href="/jobseeker/offers">返回 Offer 列表</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-emerald-50/30">
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
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
              <span className="text-slate-700">谈判</span>
            </nav>
            <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold text-slate-900">
              <Wand2 className="size-5 text-emerald-600" aria-hidden /> 薪资谈判 ·
              <span className="font-normal text-slate-600">
                {offer?.title || "加载中…"}
              </span>
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              基于市场分位 + AI 的策略建议,可切换岗位与场景
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild>
              <Link href="/jobseeker/offers">
                <ArrowLeft className="mr-1.5 size-4" /> 返回
              </Link>
            </Button>
            <Button asChild data-testid="open-simulator">
              <Link
                href={`/jobseeker/offers/negotiate-simulate?id=${offerId}`}
                onClick={() =>
                  track("negotiate_to_simulate", { offer_id: offerId })
                }
              >
                <MessageCircle className="mr-1.5 size-4" /> 谈判模拟
              </Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
        {/* 岗位 + 场景 + 操作 */}
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-slate-600">岗位:</span>
              <div
                className="flex flex-wrap gap-2"
                role="radiogroup"
                aria-label="市场岗位"
              >
                {MARKET_ROLES.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    role="radio"
                    aria-checked={marketRole === r.value}
                    onClick={() => {
                      setMarketRole(r.value);
                      loadScript(r.value, scenario);
                    }}
                    className={`rounded-full border px-3 py-1.5 text-xs transition ${
                      marketRole === r.value
                        ? "border-sky-500 bg-sky-50 text-sky-700"
                        : "border-slate-200 hover:border-slate-400"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-sm text-slate-600">场景:</span>
                <Badge variant="secondary" className="rounded-full">
                  5 套策略可选
                </Badge>
              </div>
              <div
                className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5"
                role="radiogroup"
                aria-label="谈判场景"
              >
                {SCENARIO_ORDER.map(({ key, emoji }) => {
                  const meta = SCENARIO_LABELS[key];
                  const active = scenario === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      onClick={() => {
                        setScenario(key);
                        loadScript(marketRole, key);
                        track("negotiate_scenario_change", { scenario: key });
                      }}
                      data-testid={`scenario-${key}`}
                      className={`group rounded-2xl border p-3 text-left transition ${
                        active
                          ? "border-emerald-400 bg-emerald-50/60 shadow-sm"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-center gap-1.5 text-sm font-medium text-slate-800">
                        <span aria-hidden>{emoji}</span>
                        {meta.label}
                      </div>
                      <p className="mt-1 text-[11px] leading-snug text-slate-500">
                        {meta.hint}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-3">
              <span className="text-xs text-slate-400">
                重新生成将调用同一个 mock / LLM 端点
              </span>
              <Button
                variant="outline"
                onClick={reload}
                disabled={loading}
                data-testid="regenerate-script"
              >
                <RefreshCcw className="mr-1.5 size-4" /> 重新生成
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Persona 提示 */}
        <Card
          className="overflow-hidden border-emerald-200 bg-gradient-to-r from-emerald-50/80 via-white to-sky-50/60"
          data-testid="persona-hint-card"
        >
          <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-emerald-600" aria-hidden />
                <h2 className="text-base font-semibold text-slate-900">
                  把脚本变成对话
                </h2>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                选一位 HR 人格,在 Open WebUI 风格的对话里实地演练这份脚本。
              </p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {PERSONA_HINTS.map((p) => (
                  <li key={p.id}>
                    <Badge
                      variant="secondary"
                      className="rounded-full bg-white/80 px-2.5 py-1 text-xs font-normal"
                    >
                      <span className="mr-1" aria-hidden>
                        {p.emoji}
                      </span>
                      <span className="font-medium text-slate-700">{p.label}</span>
                      <span className="ml-1 text-slate-500">· {p.desc}</span>
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
            <Button asChild className="shrink-0 rounded-full">
              <Link href={`/jobseeker/offers/negotiate-simulate?id=${offerId}`}>
                <MessageSquare className="mr-2 size-4" /> 进入模拟器
              </Link>
            </Button>
          </CardContent>
        </Card>

        {error && (
          <div
            role="alert"
            className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
          >
            {error}
          </div>
        )}

        {script && (
          <>
            <SalaryChart
              band={script.market_band || []}
              yourValue={
                offer && script.currency === "CNY" && offer.base_salary
                  ? Number(offer.base_salary) / 10000
                  : offer && script.currency === "USD" && offer.base_salary
                  ? Number(offer.base_salary) / 1000
                  : undefined
              }
              unit={
                script.currency === "CNY"
                  ? "万"
                  : script.currency === "USD"
                    ? "k$"
                    : "k SGD"
              }
            />

            <Tabs defaultValue="script" className="space-y-4">
              <TabsList className="grid w-full grid-cols-2 sm:max-w-md">
                <TabsTrigger value="script">
                  <Wand2 className="mr-1.5 size-4" /> 谈判策略
                </TabsTrigger>
                <TabsTrigger value="messages">
                  <Mail className="mr-1.5 size-4" /> 话术 & 邮件
                </TabsTrigger>
              </TabsList>
              <TabsContent value="script">
                <NegotiationScript data={script as unknown as Parameters<typeof NegotiationScript>[0]["data"]} />
              </TabsContent>
              <TabsContent value="messages" className="space-y-4">
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base">邮件 / 微信话术</CardTitle>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => copy(script.email_template ?? "", "email")}
                        data-testid="copy-email"
                      >
                        <Clipboard className="mr-1.5 size-4" />
                        {copied === "email" ? "已复制 ✓" : "一键复制"}
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm text-slate-800">
                      {script.email_template}
                    </pre>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">通话要点</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                      {(script.talking_points || []).map((p: string, i: number) => (
                        <li key={i}>{p}</li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </>
        )}

        {loading && !script && (
          <div
            className="rounded-2xl border border-dashed border-slate-200 bg-white/60 p-12 text-center text-slate-400"
            aria-live="polite"
          >
            AI 正在为你准备谈判脚本…
          </div>
        )}
      </main>
    </div>
  );
}

// ---------- Suspense 包裹 ----------
export default function NegotiatePage() {
  return (
    <ErrorBoundary>(<Suspense fallback={<div className="p-8 text-slate-400">加载中…</div>}>
        <NegotiatePageInner />
      </Suspense>)</ErrorBoundary>
  );
}

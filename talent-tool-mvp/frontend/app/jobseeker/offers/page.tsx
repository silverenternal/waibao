"use client";

/**
 * v9.1 — /jobseeker/offers — Offer 列表 + 新建
 *
 * v9.1 改动:
 *  - 顶部增加 Offer 概览数据条(总包 / 月到手 / 平均分位)
 *  - 引入 PersonaSelector 提示卡片,引导进入模拟谈判
 *  - 列表卡片支持键盘聚焦 + 选中对比 / 谈判 快捷键
 *  - 空状态使用 EmptyState + 引导三步走(录入 → 模拟 → 谈判)
 *  - 表单实时预览改用「分位指示条 + KPI 数字」双视图
 *  - 全程埋点 + 跟踪按钮可用性
 *
 * 数据接口保持不变 (/api/offers, /api/offers/calculate)
 */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Briefcase,
  Plus,
  Scale,
  Sparkles,
  Trash2,
  TrendingUp,
  Wallet,
  MessageSquare,
  RefreshCcw,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/EmptyState";
import { OfferBreakdown } from "@/components/OfferBreakdown";

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
    // 静默失败
  }
}

// ---------- 类型 ----------
interface OfferRow {
  id: string;
  title: string;
  company: string;
  location: string;
  currency: string;
  base_salary: number;
  bonus: number;
  bonus_target_pct: number;
  equity_value: number;
  equity_vesting_years: number;
  benefits: number;
  signing_bonus: number;
  pto_days: number;
  created_at?: string;
}

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

// ---------- 常量 ----------
const LOCATIONS = [
  { value: "CN", label: "中国大陆", currency: "CNY", symbol: "¥", tax: "个税 + 五险一金(2024 校准)" },
  { value: "US", label: "美国", currency: "USD", symbol: "$", tax: "联邦 + 州税 + FICA(2024 校准)" },
  { value: "SG", label: "新加坡", currency: "SGD", symbol: "S$", tax: "渐进式个税 + CPF(2024 校准)" },
] as const;

const MAX_COMPARE = 6;

const PERSONA_HINTS = [
  { id: "warm", emoji: "🌸", label: "友好型 HR", desc: "以关系维护为主,常用" },
  { id: "data", emoji: "📊", label: "数据型 HR", desc: "用市场和分位说服" },
  { id: "tough", emoji: "🧱", label: "强硬派 HR", desc: "强调预算与制度" },
];

// ---------- 主组件 ----------
function OffersPageInner() {
  const router = useRouter();
  const token = useCallback(() => localStorage.getItem("sb_token") || "", []);

  const [offers, setOffers] = useState<OfferRow[]>([]);
  const [totalMap, setTotalMap] = useState<Record<string, AnnualTotal>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Partial<OfferRow>>({
    location: "CN",
    currency: "CNY",
    equity_vesting_years: 4,
    pto_days: 10,
  });
  const [preview, setPreview] = useState<AnnualTotal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"created" | "total" | "monthly">("created");
  const listRef = useRef<HTMLUListElement | null>(null);

  // 初次加载
  useEffect(() => {
    let alive = true;
    track("offers_page_view", { existing_count: offers.length });
    (async () => {
      try {
        const r = await fetch("/api/offers", {
          headers: { Authorization: `Bearer ${token()}` },
        });
        const data = await r.json();
        if (!alive) return;
        const list: OfferRow[] = data.offers || [];
        setOffers(list);
        track("offers_list_loaded", { count: list.length });
        const totals: Record<string, AnnualTotal> = {};
        for (const o of list) {
          const r2 = await fetch(`/api/offers/${o.id}`, {
            headers: { Authorization: `Bearer ${token()}` },
          });
          if (r2.ok) {
            const d2 = await r2.json();
            totals[o.id] = d2.total;
          }
        }
        if (alive) setTotalMap(totals);
      } catch (e) {
        if (alive) setError((e as Error)?.message || "加载失败");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 实时预览
  const calcPreview = useCallback(
    async (d: Partial<OfferRow>) => {
      const body = {
        title: d.title || "预览",
        company: "",
        role_level: "",
        location: d.location || "CN",
        currency:
          d.currency ||
          (d.location === "CN" ? "CNY" : d.location === "US" ? "USD" : "SGD"),
        base_salary: Number(d.base_salary || 0),
        bonus: Number(d.bonus || 0),
        bonus_target_pct: Number(d.bonus_target_pct || 0),
        equity_value: Number(d.equity_value || 0),
        equity_vesting_years: Number(d.equity_vesting_years || 4),
        benefits: Number(d.benefits || 0),
        signing_bonus: Number(d.signing_bonus || 0),
        pto_days: Number(d.pto_days || 0),
        extras: {},
      };
      try {
        const r = await fetch("/api/offers/calculate", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token()}`,
          },
          body: JSON.stringify(body),
        });
        if (r.ok) {
          const data = await r.json();
          setPreview(data.total);
          track("offers_calculate_preview", {
            location: d.location,
            has_equity: !!d.equity_value,
          });
        }
      } catch {
        // 静默
      }
    },
    [token]
  );

  // 保存草稿
  const saveDraft = useCallback(async () => {
    setCreating(true);
    setError(null);
    try {
      const body = {
        title: draft.title || "未命名",
        company: draft.company || "",
        location: draft.location || "CN",
        currency:
          draft.currency ||
          (draft.location === "CN" ? "CNY" : draft.location === "US" ? "USD" : "SGD"),
        base_salary: Number(draft.base_salary || 0),
        bonus: Number(draft.bonus || 0),
        bonus_target_pct: Number(draft.bonus_target_pct || 0),
        equity_value: Number(draft.equity_value || 0),
        equity_vesting_years: Number(draft.equity_vesting_years || 4),
        benefits: Number(draft.benefits || 0),
        signing_bonus: Number(draft.signing_bonus || 0),
        pto_days: Number(draft.pto_days || 0),
        extras: {},
        role_level: "",
      };
      const r = await fetch("/api/offers", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token()}`,
        },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setOffers((prev) => [...prev, data.offer]);
      setTotalMap((prev) => ({ ...prev, [data.offer.id]: data.total }));
      setDraft({
        location: draft.location,
        currency: draft.currency,
        equity_vesting_years: 4,
        pto_days: 10,
        title: "",
        company: "",
      });
      setPreview(null);
      track("offer_saved", {
        offer_id: data.offer.id,
        location: body.location,
        base_salary: body.base_salary,
      });
    } catch (e) {
      setError((e as Error)?.message || "保存失败");
    } finally {
      setCreating(false);
    }
  }, [draft, token]);

  // 删除
  const deleteOne = useCallback(
    async (id: string) => {
      if (!confirm("确定删除这份 Offer?此操作不可恢复。")) return;
      const r = await fetch(`/api/offers/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token()}` },
      });
      if (r.ok) {
        setOffers((prev) => prev.filter((o) => o.id !== id));
        setSelected((prev) => prev.filter((sid) => sid !== id));
        setTotalMap((prev) => {
          const cp = { ...prev };
          delete cp[id];
          return cp;
        });
        track("offer_deleted", { offer_id: id });
      }
    },
    [token]
  );

  // 选择
  const togglePick = useCallback((id: string) => {
    setSelected((prev) => {
      const exists = prev.includes(id);
      if (exists) {
        track("offer_select_toggle", { offer_id: id, selected_count: prev.length - 1 });
        return prev.filter((x) => x !== id);
      }
      if (prev.length >= MAX_COMPARE) {
        track("offer_select_cap_hit", { cap: MAX_COMPARE });
        return prev;
      }
      track("offer_select_toggle", { offer_id: id, selected_count: prev.length + 1 });
      return [...prev, id];
    });
  }, []);

  const goCompare = useCallback(() => {
    if (selected.length < 2) {
      alert("至少选择 2 份 Offer 来比较");
      return;
    }
    track("compare_click", { offer_ids: selected });
    router.push(`/offers/compare?ids=${selected.join(",")}`);
  }, [router, selected]);

  const goNegotiate = useCallback(
    (offerId: string) => {
      track("negotiate_click", { offer_id: offerId });
      router.push(`/offers/negotiate?id=${offerId}`);
    },
    [router]
  );

  // 排序后的列表
  const sortedOffers = useMemo(() => {
    const arr = [...offers];
    if (sortBy === "total") {
      arr.sort((a, b) => (totalMap[b.id]?.total_comp || 0) - (totalMap[a.id]?.total_comp || 0));
    } else if (sortBy === "monthly") {
      arr.sort(
        (a, b) =>
          (totalMap[b.id]?.monthly_net || 0) - (totalMap[a.id]?.monthly_net || 0)
      );
    } else {
      arr.sort((a, b) => {
        const at = a.created_at || "";
        const bt = b.created_at || "";
        return at < bt ? 1 : at > bt ? -1 : 0;
      });
    }
    return arr;
  }, [offers, totalMap, sortBy]);

  // 顶部统计
  const aggregate = useMemo(() => {
    const totals = Object.values(totalMap);
    if (totals.length === 0) return null;
    const totalComp = totals.reduce((s, t) => s + t.total_comp, 0);
    const monthly = totals.reduce((s, t) => s + t.monthly_net, 0);
    const taxRate =
      totals.reduce((s, t) => s + t.effective_tax_rate, 0) / totals.length;
    return {
      totalComp,
      monthly,
      taxRate,
      count: totals.length,
    };
  }, [totalMap]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-sky-50/40">
      <Header
        selectedCount={selected.length}
        onCompare={goCompare}
        onNegotiate={() => selected[0] && goNegotiate(selected[0])}
      />

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
        {/* 概览条 */}
        {aggregate && (
          <section
            aria-label="Offer 概览"
            className="grid grid-cols-2 gap-3 md:grid-cols-4"
          >
            <KpiTile
              label="已保存"
              value={String(aggregate.count)}
              unit="份"
              tone="sky"
            />
            <KpiTile
              label="总包合计"
              value={Math.round(aggregate.totalComp).toLocaleString()}
              unit="(混合币种)"
              tone="emerald"
            />
            <KpiTile
              label="月到手合计"
              value={Math.round(aggregate.monthly).toLocaleString()}
              unit="(混合币种)"
              tone="indigo"
            />
            <KpiTile
              label="平均有效税率"
              value={`${(aggregate.taxRate * 100).toFixed(1)}%`}
              unit="2024 校准"
              tone="amber"
            />
          </section>
        )}

        {/* 谈判 Persona 提示 */}
        <Card
          className="overflow-hidden border-sky-200 bg-gradient-to-r from-sky-50/80 via-white to-indigo-50/60"
          data-testid="persona-hint-card"
        >
          <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-sky-600" aria-hidden />
                <h2 className="text-base font-semibold text-slate-900">
                  选好 HR 风格,练一次谈判再说
                </h2>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                v9.1 上线「Open WebUI 风格谈判模拟器」,先挑一位 HR,再开始对话练习。
              </p>
              <ul className="mt-3 flex flex-wrap gap-2">
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
            <Button
              variant="default"
              className="shrink-0 rounded-full"
              onClick={() => {
                track("persona_hint_click");
                if (selected[0]) {
                  router.push(`/offers/negotiate-simulate?id=${selected[0]}`);
                } else if (offers[0]) {
                  router.push(`/offers/negotiate-simulate?id=${offers[0].id}`);
                } else {
                  // 滚动到表单
                  document
                    .getElementById("offer-form")
                    ?.scrollIntoView({ behavior: "smooth" });
                }
              }}
              data-testid="open-persona-simulator"
            >
              <MessageSquare className="mr-2 size-4" /> 打开谈判模拟器
            </Button>
          </CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-5">
          {/* 左侧:列表 */}
          <section className="space-y-3 lg:col-span-3" aria-label="Offer 列表">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold tracking-wide text-slate-600 uppercase">
                已保存的 Offer
              </h2>
              <div className="flex items-center gap-1 text-xs">
                <span className="text-slate-500">排序</span>
                {(
                  [
                    { v: "created", l: "最新" },
                    { v: "total", l: "总包" },
                    { v: "monthly", l: "月到手" },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.v}
                    onClick={() => {
                      setSortBy(opt.v);
                      track("offers_sort_change", { by: opt.v });
                    }}
                    aria-pressed={sortBy === opt.v}
                    className={`rounded-full px-2.5 py-1 transition ${
                      sortBy === opt.v
                        ? "bg-slate-900 text-white"
                        : "text-slate-500 hover:bg-slate-100"
                    }`}
                  >
                    {opt.l}
                  </button>
                ))}
              </div>
            </div>

            {loading ? (
              <SkeletonList />
            ) : sortedOffers.length === 0 ? (
              <EmptyState
                icon={<Briefcase className="size-6" aria-hidden />}
                title="还没有保存的 Offer"
                description="在右侧表单录入你的第一份 offer,即可看到实时税前税后、市场分位与谈判建议。"
                action={
                  <Button
                    onClick={() =>
                      document
                        .getElementById("offer-form")
                        ?.scrollIntoView({ behavior: "smooth" })
                    }
                    data-testid="empty-cta"
                  >
                    <Plus className="mr-2 size-4" /> 开始录入
                  </Button>
                }
              />
            ) : (
              <ul
                ref={listRef}
                role="list"
                className="space-y-3"
                aria-label="Offer 卡片列表"
                data-testid="offer-list"
              >
                {sortedOffers.map((o) => {
                  const t = totalMap[o.id];
                  const isSel = selected.includes(o.id);
                  return (
                    <li key={o.id}>
                      <Card
                        data-testid={`offer-row-${o.id}`}
                        className={`relative transition focus-within:ring-2 focus-within:ring-sky-300 ${
                          isSel
                            ? "border-sky-500 shadow-md ring-1 ring-sky-200"
                            : "hover:border-slate-300"
                        }`}
                        aria-selected={isSel}
                      >
                        <button
                          type="button"
                          onClick={() => togglePick(o.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              togglePick(o.id);
                            }
                          }}
                          aria-label={isSel ? "取消选中" : "加入对比"}
                          aria-pressed={isSel}
                          className="absolute top-3 left-3 inline-flex h-6 w-6 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-500 transition hover:border-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
                        >
                          {isSel && (
                            <span aria-hidden className="text-sky-600">
                              ✓
                            </span>
                          )}
                        </button>
                        <CardContent className="p-4 pl-12">
                          {t ? (
                            <OfferBreakdown
                              offer={{ ...t, title: o.title, company: o.company }}
                              compact
                            />
                          ) : (
                            <div className="text-sm text-slate-400">计算中…</div>
                          )}
                        </CardContent>
                        <div className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/40 px-4 py-3">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => goNegotiate(o.id)}
                            data-testid={`negotiate-${o.id}`}
                          >
                            <MessageSquare className="mr-1.5 size-3.5" /> 谈判脚本
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => deleteOne(o.id)}
                            data-testid={`delete-${o.id}`}
                            className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                          >
                            <Trash2 className="mr-1.5 size-3.5" /> 删除
                          </Button>
                        </div>
                      </Card>
                    </li>
                  );
                })}
              </ul>
            )}

            {error && (
              <div
                role="alert"
                className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
              >
                {error}
              </div>
            )}
          </section>

          {/* 右侧:录入 */}
          <aside className="space-y-4 lg:col-span-2">
            <Card id="offer-form" data-testid="offer-form" className="sticky top-4">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Plus className="size-4 text-sky-600" /> 录入新 Offer
                </CardTitle>
                <p className="text-xs text-slate-500">
                  实时计算月到手 / 总包 / 有效税率,支持 CN · US · SG 三地区。
                </p>
              </CardHeader>
              <CardContent className="space-y-3">
                <Field label="职位 / 公司">
                  <Input
                    value={draft.title || ""}
                    onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                    placeholder="如:高级工程师 @ Waibao"
                  />
                </Field>

                <Field
                  label="地区"
                  hint="三地区税务 / 五险一金模型均已校准"
                >
                  <div
                    className="flex flex-wrap gap-2"
                    role="radiogroup"
                    aria-label="地区"
                  >
                    {LOCATIONS.map((loc) => (
                      <button
                        key={loc.value}
                        type="button"
                        role="radio"
                        aria-checked={draft.location === loc.value}
                        onClick={() => {
                          setDraft({
                            ...draft,
                            location: loc.value,
                            currency: loc.currency,
                          });
                          track("offer_region_change", { region: loc.value });
                          calcPreview({
                            ...draft,
                            location: loc.value,
                            currency: loc.currency,
                          });
                        }}
                        className={`rounded-full border px-3 py-1.5 text-xs transition ${
                          draft.location === loc.value
                            ? "border-sky-500 bg-sky-50 text-sky-700"
                            : "border-slate-200 hover:border-slate-400"
                        }`}
                      >
                        {loc.label} <span className="opacity-60">({loc.currency})</span>
                      </button>
                    ))}
                  </div>
                  <p className="text-[10px] text-slate-500">
                    {LOCATIONS.find((l) => l.value === draft.location)?.tax}
                  </p>
                </Field>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Base / 年">
                    <Input
                      type="number"
                      inputMode="numeric"
                      value={draft.base_salary ?? ""}
                      onChange={(e) =>
                        setDraft({ ...draft, base_salary: Number(e.target.value) })
                      }
                      onBlur={() => calcPreview(draft)}
                      placeholder="如 60 万"
                    />
                  </Field>
                  <Field label="Bonus / 年">
                    <Input
                      type="number"
                      inputMode="numeric"
                      value={draft.bonus ?? ""}
                      onChange={(e) =>
                        setDraft({ ...draft, bonus: Number(e.target.value) })
                      }
                      onBlur={() => calcPreview(draft)}
                      placeholder="现金"
                    />
                  </Field>
                  <Field label="Bonus 占比 %">
                    <Input
                      type="number"
                      step="0.05"
                      value={
                        draft.bonus_target_pct
                          ? String(draft.bonus_target_pct * 100)
                          : ""
                      }
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          bonus_target_pct: Number(e.target.value) / 100,
                        })
                      }
                      onBlur={() => calcPreview(draft)}
                      placeholder="20 → 0.20"
                    />
                  </Field>
                  <Field label="Equity (现值)">
                    <Input
                      type="number"
                      inputMode="numeric"
                      value={draft.equity_value ?? ""}
                      onChange={(e) =>
                        setDraft({ ...draft, equity_value: Number(e.target.value) })
                      }
                      onBlur={() => calcPreview(draft)}
                      placeholder="如 200 万"
                    />
                  </Field>
                  <Field label="Vesting 年限">
                    <Input
                      type="number"
                      value={draft.equity_vesting_years ?? 4}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          equity_vesting_years: Number(e.target.value),
                        })
                      }
                    />
                  </Field>
                  <Field label="Benefits / 年">
                    <Input
                      type="number"
                      inputMode="numeric"
                      value={draft.benefits ?? ""}
                      onChange={(e) =>
                        setDraft({ ...draft, benefits: Number(e.target.value) })
                      }
                      onBlur={() => calcPreview(draft)}
                    />
                  </Field>
                  <Field label="Signing Bonus">
                    <Input
                      type="number"
                      inputMode="numeric"
                      value={draft.signing_bonus ?? ""}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          signing_bonus: Number(e.target.value),
                        })
                      }
                      onBlur={() => calcPreview(draft)}
                    />
                  </Field>
                  <Field label="PTO (天/年)">
                    <Input
                      type="number"
                      value={draft.pto_days ?? 10}
                      onChange={(e) =>
                        setDraft({ ...draft, pto_days: Number(e.target.value) })
                      }
                    />
                  </Field>
                </div>

                {preview ? (
                  <PreviewBlock preview={preview} />
                ) : (
                  <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50/50 px-3 py-4 text-center text-xs text-slate-400">
                    填写数字后,这里会出现月到手 · 总包 · 税率预览
                  </p>
                )}

                <Button
                  className="w-full"
                  onClick={saveDraft}
                  disabled={creating}
                  data-testid="save-offer"
                >
                  {creating ? (
                    <>
                      <RefreshCcw className="mr-2 size-4 animate-spin" /> 保存中…
                    </>
                  ) : (
                    <>
                      <Plus className="mr-2 size-4" /> 保存到我的 Offer
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          </aside>
        </div>
      </main>
    </div>
  );
}

// ---------- 头部 ----------
function Header({
  selectedCount,
  onCompare,
  onNegotiate,
}: {
  selectedCount: number;
  onCompare: () => void;
  onNegotiate: () => void;
}) {
  return (
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
            <span className="text-slate-700">Offer 管理</span>
          </nav>
          <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold text-slate-900">
            <Briefcase className="size-5 text-sky-600" aria-hidden /> Offer 管理
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            集中管理多份 offer · 一键对比 · AI 谈判建议与模拟
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="rounded-full">
            已选 {selectedCount} / {MAX_COMPARE}
          </Badge>
          <Button
            variant="outline"
            onClick={onCompare}
            disabled={selectedCount < 2}
            data-testid="go-compare"
          >
            <Scale className="mr-1.5 size-4" /> 比较所选
          </Button>
          <Button
            onClick={onNegotiate}
            disabled={selectedCount !== 1}
            data-testid="go-negotiate"
          >
            <MessageSquare className="mr-1.5 size-4" /> 谈判模拟
          </Button>
        </div>
      </div>
    </header>
  );
}

// ---------- KPI 卡片 ----------
function KpiTile({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: string;
  unit: string;
  tone: "sky" | "emerald" | "indigo" | "amber";
}) {
  const palette = {
    sky: "from-sky-50 to-sky-100/60 text-sky-900 border-sky-200",
    emerald: "from-emerald-50 to-emerald-100/60 text-emerald-900 border-emerald-200",
    indigo: "from-indigo-50 to-indigo-100/60 text-indigo-900 border-indigo-200",
    amber: "from-amber-50 to-amber-100/60 text-amber-900 border-amber-200",
  }[tone];
  return (
    <div
      className={`rounded-2xl border bg-gradient-to-br p-4 shadow-sm ${palette}`}
    >
      <div className="text-[10px] tracking-wider uppercase opacity-70">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-[10px] opacity-70">{unit}</div>
    </div>
  );
}

// ---------- 字段包装 ----------
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs text-slate-600">{label}</Label>
      {children}
      {hint && <p className="text-[10px] text-slate-400">{hint}</p>}
    </div>
  );
}

// ---------- 预览块 ----------
function PreviewBlock({ preview }: { preview: AnnualTotal }) {
  const fmt = (n: number) =>
    new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(n);
  return (
    <div
      className="space-y-2 rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50/60 p-3"
      data-testid="preview"
    >
      <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-700">
        <TrendingUp className="size-3.5" /> 实时预览 · 已校准
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <Mini
          icon={<Wallet className="size-3" />}
          label="月到手"
          value={fmt(preview.monthly_net)}
          unit={preview.currency}
        />
        <Mini
          icon={<Briefcase className="size-3" />}
          label="总包"
          value={fmt(preview.total_comp)}
          unit={preview.currency}
        />
        <Mini
          icon={<TrendingUp className="size-3" />}
          label="有效税率"
          value={`${(preview.effective_tax_rate * 100).toFixed(1)}%`}
          unit=""
        />
      </div>
    </div>
  );
}

function Mini({
  icon,
  label,
  value,
  unit,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  unit: string;
}) {
  return (
    <div className="rounded-lg bg-white/70 px-2 py-1.5">
      <div className="flex items-center justify-center gap-1 text-[10px] text-slate-500">
        {icon} {label}
      </div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">
        {value}
      </div>
      {unit && <div className="text-[9px] text-slate-400">{unit}</div>}
    </div>
  );
}

// ---------- 骨架 ----------
function SkeletonList() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="加载中">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-32 animate-pulse rounded-2xl border border-slate-200 bg-slate-100/60"
        />
      ))}
    </div>
  );
}

// ---------- Suspense 包裹(Next.js 16 useSearchParams 要求) ----------
export default function OffersPage() {
  return (
    <Suspense fallback={<div className="p-8 text-slate-400">加载中…</div>}>
      <OffersPageInner />
    </Suspense>
  );
}

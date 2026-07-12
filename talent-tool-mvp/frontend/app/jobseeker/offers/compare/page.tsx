"use client";

/**
 * /offers/compare — 多 Offer 横向比较 (T1302).
 *
 * 读 ?ids=... 选择 offer,展示 OfferComparisonTable + OfferBreakdown 列表 + 排名。
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

// T1802 - 埋点 helper
function track(event: string, props?: Record<string, any>) {
  if (typeof window === "undefined") return;
  try {
    (window as any).dataLayer = (window as any).dataLayer || [];
    (window as any).dataLayer.push({ event, ts: Date.now(), ...(props || {}) });
    fetch("/api/signals/track", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("sb_token") || ""}` },
      body: JSON.stringify({ event, props: props || {} }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // ignore
  }
}
import { useEffect, useState } from "react";
import { OfferBreakdown } from "@/components/OfferBreakdown";
import { OfferComparisonTable } from "@/components/OfferComparisonTable";

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
  radar: { base: number[]; net_monthly: number[]; equity_pv: number[]; benefits: number[]; total_comp: number[] };
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

export default function ComparePage() {
  const params = useSearchParams();
  const router = useRouter();
  const token = () => localStorage.getItem("sb_token") || "";
  const [result, setResult] = useState<CompareResult | null>(null);
  const [titles, setTitles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ids = (params?.get("ids") || "").split(",").filter(Boolean);
    if (ids.length < 2) {
      router.push("/offers");
      return;
    }
    track("compare_page_view", { offer_ids: ids, count: ids.length });
    (async () => {
      try {
        // 先拉取每个 offer 的标题(因 compare 只返回 total)
        const fetched: OfferRow[] = [];
        for (const id of ids) {
          const r = await fetch(`/api/offers/${id}`, {
            headers: { Authorization: `Bearer ${token()}` },
          });
          if (r.ok) {
            const d = await r.json();
            fetched.push(d.offer);
          }
        }
        setTitles(fetched.map((o) => o.title || o.company || "Offer"));

        // 调用 compare
        const r2 = await fetch("/api/offers/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
          body: JSON.stringify({ offer_ids: ids }),
        });
        if (!r2.ok) throw new Error(await r2.text());
        const data: CompareResult = await r2.json();
        setResult(data);
      } catch (e: any) {
        setError(e?.message || "比较失败");
      } finally {
        setLoading(false);
      }
    })();
  }, [params, router]);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-400">计算中…</div>;
  }
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center text-rose-600">{error}</div>
    );
  }
  if (!result) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span aria-hidden>⚖️</span> Offer 横向对比
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            比较 {titles.length} 份 · 按 CNY 等价衡量总包
          </p>
        </div>
        <Link href="/offers" className="px-4 py-1.5 text-sm rounded bg-slate-200 hover:bg-slate-300">
          返回管理
        </Link>
      </div>

      <div className="max-w-6xl mx-auto p-6 space-y-6">
        {/* 推荐 */}
        <div className="grid md:grid-cols-2 gap-4">
          <Recommend label="总包最佳" title={result.best_by_total} color="from-sky-500 to-indigo-600" />
          <Recommend label="月到手最佳" title={result.best_by_monthly_net} color="from-emerald-500 to-teal-600" />
        </div>

        {/* 雷达 */}
        <div className="bg-white rounded-2xl p-6 shadow-sm">
          <h2 className="text-base font-semibold text-slate-800 mb-3">五维雷达</h2>
          <OfferComparisonTable titles={titles} radar={result.radar} />
        </div>

        {/* 明细卡片 */}
        <div>
          <h2 className="text-base font-semibold text-slate-800 mb-3">各项明细</h2>
          <div className="grid md:grid-cols-2 gap-4">
            {result.offers.map((ot, idx) => (
              <OfferBreakdown
                key={idx}
                offer={{
                  ...ot,
                  title: titles[idx] || "Offer",
                  company: "",
                }}
              />
            ))}
          </div>
        </div>

        {/* 排名 */}
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h2 className="text-base font-semibold text-slate-800 mb-3">综合排名(CNY 等价)</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-2">#</th>
                <th>Offer</th>
                <th>地区</th>
                <th className="text-right">总包(本币)</th>
                <th className="text-right">折合 CNY</th>
                <th className="text-right">月到手</th>
              </tr>
            </thead>
            <tbody>
              {result.rank.map((r) => (
                <tr key={r.rank} className="border-t border-slate-100">
                  <td className="py-2 font-mono text-slate-500">{r.rank}</td>
                  <td className="text-slate-800 font-medium">{r.title}</td>
                  <td className="text-slate-600">{r.location}/{r.currency}</td>
                  <td className="text-right tabular-nums">
                    {Math.round(r.total_comp_local).toLocaleString()}
                  </td>
                  <td className="text-right tabular-nums font-semibold text-slate-900">
                    ¥{Math.round(r.total_comp_cny_equiv).toLocaleString()}
                  </td>
                  <td className="text-right tabular-nums text-slate-700">
                    {Math.round(r.monthly_net_local).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Recommend({ label, title, color }: { label: string; title: string; color: string }) {
  return (
    <div className={`rounded-2xl bg-gradient-to-r ${color} p-5 text-white shadow-sm`}>
      <div className="text-xs uppercase opacity-90">{label}</div>
      <div className="text-lg font-semibold mt-1">{title}</div>
    </div>
  );
}

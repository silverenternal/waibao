"use client";

/**
 * /offers/negotiate — 谈判策略生成 (T1302).
 *
 * 读 ?id= 后调用 /api/offers/{id}/negotiate,展示 NegotiationScript。
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { NegotiationScript } from "@/components/NegotiationScript";
import { SalaryChart } from "@/components/SalaryChart";

// T1802 - 埋点 helper + 5 场景标签
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

const NEGOTIATION_SCENARIO_LABELS: Record<string, string> = {
  scenario_a_below_p50: "Below p50 — 市场分位偏低",
  scenario_b_competing_offer: "Compete — 多家 offer 互 match",
  scenario_c_signing_bonus: "Signing — 争取签字费",
  scenario_d_equity_vesting: "Equity — 调整 vesting/refresh",
  scenario_e_walkaway: "Walkaway — 走人底线",
};

const MARKET_ROLES = [
  { value: "backend_engineer", label: "后端工程师", unit: "CNY 万 / USD 千 / SGD 千" },
  { value: "frontend_engineer", label: "前端工程师" },
  { value: "fullstack_engineer", label: "全栈工程师" },
  { value: "data_scientist", label: "数据科学家" },
  { value: "product_manager", label: "产品经理" },
  { value: "data_engineer", label: "数据工程师" },
];

export default function NegotiatePage() {
  const params = useSearchParams();
  const offerId = params?.get("id") || "";
  const token = () => localStorage.getItem("sb_token") || "";

  const [marketRole, setMarketRole] = useState("backend_engineer");
  const [loading, setLoading] = useState(true);
  const [script, setScript] = useState<any>(null);
  const [offer, setOffer] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!offerId) return;
    track("negotiate_page_view", { offer_id: offerId });
    (async () => {
      try {
        // 拉取 offer 主体
        const r = await fetch(`/api/offers/${offerId}`, {
          headers: { Authorization: `Bearer ${token()}` },
        });
        if (!r.ok) throw new Error("未找到 Offer");
        const d = await r.json();
        setOffer(d.offer);
        // 调 negotiate
        await loadScript(marketRole);
      } catch (e: any) {
        setError(e?.message || "加载失败");
      } finally {
        setLoading(false);
      }
    })();
  }, [offerId]);

  async function loadScript(role: string) {
    try {
      const r = await fetch(`/api/offers/${offerId}/negotiate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ market_role: role, language: "zh" }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setScript(data);
      track("negotiate_script_loaded", { offer_id: offerId, market_role: role, recommendation: data?.recommendation || "unknown" });
    } catch (e: any) {
      setError(e?.message || "生成谈判脚本失败");
    }
  }

  async function reload() {
    setLoading(true);
    setError(null);
    await loadScript(marketRole);
    setLoading(false);
  }

  if (!offerId) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="max-w-md text-center">
          <p className="text-rose-600">缺少 Offer ID</p>
          <Link href="/offers" className="mt-3 inline-block px-4 py-2 bg-sky-600 text-white rounded">
            返回 Offer 列表
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span aria-hidden>💬</span> 薪资谈判 ·{" "}
            <span className="text-slate-600 font-normal">{offer?.title || "..."}</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            基于市场分位 + LLM 的策略建议(可切换岗位)
          </p>
        </div>
        <Link href="/offers" className="px-4 py-1.5 text-sm rounded bg-slate-200 hover:bg-slate-300">
          ← 返回
        </Link>
      </div>

      <div className="max-w-5xl mx-auto p-6 space-y-6">
        <div className="bg-white rounded-2xl shadow-sm p-5 flex flex-wrap gap-2 items-center">
          <label className="text-sm text-slate-600">市场角色:</label>
          <div className="flex flex-wrap gap-2">
            {MARKET_ROLES.map((r) => (
              <button
                key={r.value}
                onClick={() => {
                  setMarketRole(r.value);
                  loadScript(r.value);
                }}
                aria-pressed={marketRole === r.value}
                className={`px-3 py-1.5 text-xs rounded border ${
                  marketRole === r.value
                    ? "border-sky-500 bg-sky-50 text-sky-700"
                    : "border-slate-200 hover:border-slate-400"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <button
            onClick={reload}
            disabled={loading}
            className="ml-auto px-4 py-1.5 text-sm rounded bg-sky-600 text-white disabled:opacity-50"
          >
            重新生成
          </button>
        </div>

        {error && (
          <div className="bg-rose-50 border border-rose-200 rounded p-3 text-sm text-rose-700">
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
                script.currency === "CNY" ? "万" : script.currency === "USD" ? "k$" : "k SGD"
              }
            />
            <NegotiationScript data={script} />
          </>
        )}

        {loading && !script && (
          <div className="text-center text-slate-400 py-12">AI 正在为你准备谈判脚本...</div>
        )}
      </div>
    </div>
  );
}

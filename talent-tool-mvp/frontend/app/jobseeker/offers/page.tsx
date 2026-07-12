"use client";

/**
 * /offers — Offer 列表 + 新建 (T1302).
 *
 * 列出当前用户保存的全部 offer + 实时预览税前税后 + 跳转到 compare/negotiate。
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { OfferBreakdown } from "@/components/OfferBreakdown";

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

const LOCATIONS = [
  { value: "CN", label: "中国大陆", currency: "CNY", symbol: "¥" },
  { value: "US", label: "美国", currency: "USD", symbol: "$" },
  { value: "SG", label: "新加坡", currency: "SGD", symbol: "S$" },
];

export default function OffersPage() {
  const router = useRouter();
  const token = () => localStorage.getItem("sb_token") || "";

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

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/api/offers", { headers: { Authorization: `Bearer ${token()}` } });
        const data = await r.json();
        const list: OfferRow[] = data.offers || [];
        setOffers(list);
        // 拉取每个的 total
        const totals: Record<string, AnnualTotal> = {};
        for (const o of list) {
          const r2 = await fetch(`/api/offers/${o.id}`, { headers: { Authorization: `Bearer ${token()}` } });
          if (r2.ok) {
            const d2 = await r2.json();
            totals[o.id] = d2.total;
          }
        }
        setTotalMap(totals);
      } catch (e: any) {
        setError(e?.message || "加载失败");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function calcPreview(d: Partial<OfferRow>): Promise<void> {
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
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        const data = await r.json();
        setPreview(data.total);
      }
    } catch {
      // ignore
    }
  }

  async function saveDraft() {
    setCreating(true);
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
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setOffers((prev) => [...prev, data.offer]);
      setTotalMap((prev) => ({ ...prev, [data.offer.id]: data.total }));
      setDraft({
        location: "CN",
        currency: "CNY",
        equity_vesting_years: 4,
        pto_days: 10,
      });
      setPreview(null);
    } catch (e: any) {
      setError(e?.message || "保存失败");
    } finally {
      setCreating(false);
    }
  }

  async function deleteOne(id: string) {
    if (!confirm("确定删除这份 Offer?")) return;
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
    }
  }

  function togglePick(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= 6 ? prev : [...prev, id]
    );
  }

  function goCompare() {
    if (selected.length < 2) {
      alert("至少选择 2 份 Offer 来比较");
      return;
    }
    router.push(`/offers/compare?ids=${selected.join(",")}`);
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <span aria-hidden>💼</span> Offer 管理
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            已保存 {offers.length} 份 offer · 选中 {selected.length} 份
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={goCompare}
            disabled={selected.length < 2}
            data-testid="go-compare"
            className="px-4 py-1.5 text-sm rounded bg-sky-600 text-white disabled:opacity-40"
          >
            ⚖️ 比较 ({selected.length})
          </button>
          {selected.length === 1 && (
            <Link
              href={`/offers/negotiate?id=${selected[0]}`}
              className="px-4 py-1.5 text-sm rounded bg-emerald-600 text-white"
            >
              💬 谈判
            </Link>
          )}
        </div>
      </div>

      <div className="max-w-6xl mx-auto p-6 grid lg:grid-cols-5 gap-6">
        {/* 左侧:已存 offer */}
        <div className="lg:col-span-3 space-y-4">
          <h2 className="text-sm font-semibold text-slate-600">已保存的 Offer</h2>
          {loading ? (
            <div className="text-sm text-slate-400">加载中...</div>
          ) : offers.length === 0 ? (
            <div className="bg-white rounded-2xl p-10 text-center text-slate-400 border">
              👉 在右侧表单填一份,即可保存
            </div>
          ) : (
            offers.map((o) => (
              <div
                key={o.id}
                data-testid={`offer-row-${o.id}`}
                className={`relative bg-white rounded-2xl shadow-sm border-2 transition ${
                  selected.includes(o.id) ? "border-sky-500" : "border-transparent"
                }`}
              >
                <button
                  onClick={() => togglePick(o.id)}
                  aria-label="select"
                  className="absolute top-3 left-3 w-5 h-5 rounded border border-slate-300 flex items-center justify-center"
                  style={{ background: selected.includes(o.id) ? "#0ea5e9" : "transparent" }}
                >
                  {selected.includes(o.id) && <span className="text-white text-xs">✓</span>}
                </button>
                <div className="p-4 pl-10">
                  {totalMap[o.id] && (
                    <OfferBreakdown offer={{ ...totalMap[o.id], title: o.title, company: o.company }} compact />
                  )}
                </div>
                <div className="px-4 pb-4 pl-10 flex gap-2 justify-end">
                  <Link
                    href={`/offers/negotiate?id=${o.id}`}
                    className="px-3 py-1.5 text-xs rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                  >
                    谈判
                  </Link>
                  <button
                    onClick={() => deleteOne(o.id)}
                    className="px-3 py-1.5 text-xs rounded bg-rose-50 text-rose-700 hover:bg-rose-100"
                  >
                    删除
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* 右侧:新建 + 实时预览 */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white rounded-2xl shadow-sm p-5 space-y-3" data-testid="offer-form">
            <h2 className="text-sm font-semibold text-slate-800">新建 / 编辑 Offer</h2>

            <Field label="职位 / 公司">
              <input
                value={draft.title || ""}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                placeholder="如:高级工程师 @ Waibao"
                className="border rounded p-2 text-sm w-full"
              />
            </Field>

            <Field label="地区">
              <div className="flex gap-2">
                {LOCATIONS.map((loc) => (
                  <button
                    key={loc.value}
                    onClick={() =>
                      setDraft({ ...draft, location: loc.value, currency: loc.currency })
                    }
                    aria-pressed={draft.location === loc.value}
                    className={`px-3 py-1.5 text-xs rounded border ${
                      draft.location === loc.value
                        ? "border-sky-500 bg-sky-50 text-sky-700"
                        : "border-slate-200"
                    }`}
                  >
                    {loc.label} ({loc.currency})
                  </button>
                ))}
              </div>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Base / 年">
                <input
                  type="number"
                  value={draft.base_salary ?? ""}
                  onChange={(e) => setDraft({ ...draft, base_salary: Number(e.target.value) })}
                  onBlur={() => calcPreview(draft)}
                  className="border rounded p-2 text-sm w-full"
                  placeholder="如 60万"
                />
              </Field>
              <Field label="Bonus / 年">
                <input
                  type="number"
                  value={draft.bonus ?? ""}
                  onChange={(e) => setDraft({ ...draft, bonus: Number(e.target.value) })}
                  onBlur={() => calcPreview(draft)}
                  className="border rounded p-2 text-sm w-full"
                  placeholder="现金"
                />
              </Field>
              <Field label="Bonus 占比 % (可选)">
                <input
                  type="number"
                  step="0.05"
                  value={draft.bonus_target_pct ? draft.bonus_target_pct * 100 : ""}
                  onChange={(e) =>
                    setDraft({ ...draft, bonus_target_pct: Number(e.target.value) / 100 })
                  }
                  onBlur={() => calcPreview(draft)}
                  className="border rounded p-2 text-sm w-full"
                  placeholder="20 → 0.20"
                />
              </Field>
              <Field label="Equity (现值)">
                <input
                  type="number"
                  value={draft.equity_value ?? ""}
                  onChange={(e) => setDraft({ ...draft, equity_value: Number(e.target.value) })}
                  onBlur={() => calcPreview(draft)}
                  className="border rounded p-2 text-sm w-full"
                  placeholder="如 200万"
                />
              </Field>
              <Field label="Vesting 年限">
                <input
                  type="number"
                  value={draft.equity_vesting_years ?? 4}
                  onChange={(e) =>
                    setDraft({ ...draft, equity_vesting_years: Number(e.target.value) })
                  }
                  className="border rounded p-2 text-sm w-full"
                />
              </Field>
              <Field label="Benefits (年)">
                <input
                  type="number"
                  value={draft.benefits ?? ""}
                  onChange={(e) => setDraft({ ...draft, benefits: Number(e.target.value) })}
                  onBlur={() => calcPreview(draft)}
                  className="border rounded p-2 text-sm w-full"
                />
              </Field>
              <Field label="Signing Bonus">
                <input
                  type="number"
                  value={draft.signing_bonus ?? ""}
                  onChange={(e) => setDraft({ ...draft, signing_bonus: Number(e.target.value) })}
                  onBlur={() => calcPreview(draft)}
                  className="border rounded p-2 text-sm w-full"
                />
              </Field>
              <Field label="PTO (天/年)">
                <input
                  type="number"
                  value={draft.pto_days ?? 10}
                  onChange={(e) => setDraft({ ...draft, pto_days: Number(e.target.value) })}
                  className="border rounded p-2 text-sm w-full"
                />
              </Field>
            </div>

            {preview && (
              <div className="bg-emerald-50 rounded p-3 text-sm space-y-1">
                <div className="font-semibold text-emerald-700">实时预览</div>
                <div className="text-emerald-900">
                  月到手 <span className="font-semibold tabular-nums">{preview.monthly_net.toFixed(0)}</span>{" "}
                  {preview.currency}
                </div>
                <div className="text-emerald-900">
                  总包 <span className="font-semibold tabular-nums">{preview.total_comp.toFixed(0)}</span>{" "}
                  {preview.currency}
                </div>
                <div className="text-emerald-900">
                  有效税率 <span className="font-semibold tabular-nums">{(preview.effective_tax_rate * 100).toFixed(1)}%</span>
                </div>
              </div>
            )}

            {error && (
              <div className="text-xs text-rose-700 bg-rose-50 rounded p-2">{error}</div>
            )}

            <button
              onClick={saveDraft}
              disabled={creating}
              data-testid="save-offer"
              className="w-full px-4 py-2 rounded bg-gradient-to-r from-sky-500 to-indigo-600 text-white text-sm disabled:opacity-50"
            >
              {creating ? "保存中..." : "保存到我的 Offer"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-slate-600 font-medium">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

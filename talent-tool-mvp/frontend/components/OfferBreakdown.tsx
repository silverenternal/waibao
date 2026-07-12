"use client";

/**
 * OfferBreakdown — 单 offer 各项明细 (T1302).
 *
 * 展示:
 *   - 顶部关键数字(总包 / 月到手 / 有效税率)
 *   - StackedBar 显示 base + bonus + equity + benefits + signing 的占比
 *   - 简单明细表
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

export interface OfferBreakdownProps {
  offer: {
    title?: string;
    company?: string;
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
    notes?: string[];
  };
  compact?: boolean;
}

const COLOR_MAP: Record<string, string> = {
  base: "#0ea5e9",
  bonus: "#10b981",
  equity_pv: "#a855f7",
  benefits: "#f97316",
  signing: "#e11d48",
};

export function OfferBreakdown({ offer, compact = false }: OfferBreakdownProps) {
  // base = gross - bonus
  const baseSalary = Math.max(0, offer.gross - offer.bonus);
  const data = [
    { name: "Base", value: baseSalary, fill: COLOR_MAP.base },
    { name: "Bonus", value: offer.bonus, fill: COLOR_MAP.bonus },
    { name: "Equity/年化", value: offer.equity_pv, fill: COLOR_MAP.equity_pv },
    { name: "Benefits", value: offer.benefits, fill: COLOR_MAP.benefits },
    { name: "Signing", value: offer.signing_bonus, fill: COLOR_MAP.signing },
  ];

  const fmt = (n: number) =>
    new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(n);

  return (
    <div className="border rounded-2xl bg-white p-5 shadow-sm space-y-3" data-testid="offer-breakdown">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-sm font-semibold text-slate-800">{offer.title || "Offer"}</div>
          {offer.company && <div className="text-xs text-slate-500">{offer.company}</div>}
          <div className="mt-1 text-[10px] inline-block px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
            {offer.location} · {offer.currency}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-500">总包</div>
          <div className="text-2xl font-bold text-slate-900">
            {fmt(offer.total_comp)}
          </div>
          <div className="text-[10px] text-slate-500">含权益 / 福利 / 年终</div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="rounded-lg bg-sky-50 p-2">
          <div className="text-[10px] text-sky-600">月到手</div>
          <div className="text-base font-semibold text-sky-900">{fmt(offer.monthly_net)}</div>
        </div>
        <div className="rounded-lg bg-emerald-50 p-2">
          <div className="text-[10px] text-emerald-600">净收入(年)</div>
          <div className="text-base font-semibold text-emerald-900">{fmt(offer.net)}</div>
        </div>
        <div className="rounded-lg bg-amber-50 p-2">
          <div className="text-[10px] text-amber-600">有效税率</div>
          <div className="text-base font-semibold text-amber-900">
            {(offer.effective_tax_rate * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      {!compact && (
        <div className="h-32 w-full" data-testid="offer-bar">
          <ResponsiveContainer>
            <BarChart data={data} layout="vertical" margin={{ left: 60, right: 8 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={56} />
              <Tooltip
                formatter={(value) =>
                  new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(Number(value) || 0)
                }
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {data.map((entry, idx) => (
                  <Cell key={idx} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 简单明细 */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
        <Row label="Base (年)" value={fmt(baseSalary)} accent={COLOR_MAP.base} />
        <Row label="Bonus (年)" value={fmt(offer.bonus)} accent={COLOR_MAP.bonus} />
        <Row label="Equity / 年化" value={fmt(offer.equity_pv)} accent={COLOR_MAP.equity_pv} />
        <Row label="Benefits" value={fmt(offer.benefits)} accent={COLOR_MAP.benefits} />
        <Row label="Signing" value={fmt(offer.signing_bonus)} accent={COLOR_MAP.signing} />
        <Row label="五险一金/社保" value={fmt(offer.social)} accent="#94a3b8" />
      </div>

      {offer.notes && offer.notes.length > 0 && (
        <div className="bg-slate-50 rounded p-2 text-xs text-slate-500">{offer.notes.join("; ")}</div>
      )}
    </div>
  );
}

function Row({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-1">
      <span className="flex items-center gap-1.5 text-slate-600">
        <span className="w-2 h-2 rounded" style={{ background: accent }} />
        {label}
      </span>
      <span className="text-slate-800 tabular-nums">{value}</span>
    </div>
  );
}

export default OfferBreakdown;

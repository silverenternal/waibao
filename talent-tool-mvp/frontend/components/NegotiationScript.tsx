"use client";

/**
 * NegotiationScript — AI 谈判脚本展示 (T1302).
 *
 * 包含:
 *   - 整体建议 + 关键数字
 *   - 论点列表
 *   - 邮件 / 微信话术 + 复制按钮
 *   - 反例应对话术
 *   - 下一步行动
 */

import { useState } from "react";

export interface NegotiationScriptData {
  offer_title: string;
  region: string;
  currency: string;
  current_total: number;
  target_total: number;
  walkaway_threshold: number;
  percent_in_market: number;
  market_band: number[];
  overall_advice: string;
  talking_points: string[];
  email_template: string;
  counter_examples: string[];
  tactics: Array<{
    title: string;
    rationale: string;
    expected_uplift_pct: number;
    risk: string;
  }>;
  next_steps: string[];
  provider: string;
}

const RISK_COLOR: Record<string, string> = {
  low: "bg-emerald-100 text-emerald-700",
  medium: "bg-amber-100 text-amber-700",
  high: "bg-rose-100 text-rose-700",
};

export function NegotiationScript({ data }: { data: NegotiationScriptData }) {
  const [copied, setCopied] = useState(false);
  const fmt = (n: number) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(n);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.email_template);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="negotiation-script">
      {/* 顶部摘要 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500">{data.region} · {data.currency}</div>
            <div className="text-lg font-semibold text-slate-900 mt-1">{data.offer_title}</div>
          </div>
          <div className="text-xs px-2 py-1 rounded bg-emerald-50 text-emerald-700">
            {data.provider === "mock" ? "Mock 模板" : "AI 生成"}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3 mt-4">
          <KPI label="当前总包" value={fmt(data.current_total)} unit={data.currency} color="sky" />
          <KPI label="目标总包" value={fmt(data.target_total)} unit={data.currency} color="indigo" />
          <KPI label="走人底线" value={fmt(data.walkaway_threshold)} unit={data.currency} color="rose" />
        </div>

        <div className="mt-4 text-sm text-slate-700 leading-relaxed" data-testid="overall-advice">
          {data.overall_advice}
        </div>
      </div>

      {/* 市场分位 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <h3 className="text-base font-semibold text-slate-800 mb-3">市场分位</h3>
        <PercentileBar percent={data.percent_in_market} band={data.market_band} />
        <div className="grid grid-cols-5 gap-2 mt-3 text-center text-xs">
          {["p10", "p25", "p50", "p75", "p90"].map((p, idx) => (
            <div key={p} className="text-slate-500">
              <div>{p}</div>
              <div className="font-semibold text-slate-800 mt-1">
                {data.market_band[idx] ? Math.round(data.market_band[idx]) : "—"}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 论点 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <h3 className="text-base font-semibold text-slate-800 mb-3">谈判策略</h3>
        <ul className="space-y-3">
          {data.tactics.map((t, idx) => (
            <li key={idx} className="border border-slate-100 rounded-lg p-3 bg-slate-50">
              <div className="flex items-center justify-between">
                <div className="font-medium text-slate-800">{t.title}</div>
                <span className={`text-[10px] px-2 py-0.5 rounded ${RISK_COLOR[t.risk] || RISK_COLOR.low}`}>
                  风险 {t.risk}
                </span>
              </div>
              <p className="text-sm text-slate-600 mt-1">{t.rationale}</p>
              {t.expected_uplift_pct > 0 && (
                <div className="mt-1 text-xs text-emerald-700">
                  期望涨幅 +{(t.expected_uplift_pct * 100).toFixed(1)}%
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>

      {/* 通话要点 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <h3 className="text-base font-semibold text-slate-800 mb-3">通话要点</h3>
        <ul className="list-disc pl-5 space-y-1 text-sm text-slate-700">
          {data.talking_points.map((p, idx) => (
            <li key={idx}>{p}</li>
          ))}
        </ul>
      </div>

      {/* 邮件模板 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold text-slate-800">邮件 / 微信话术</h3>
          <button
            data-testid="copy-email"
            onClick={copy}
            className="text-xs px-3 py-1.5 rounded bg-sky-600 hover:bg-sky-700 text-white"
          >
            {copied ? "已复制 ✓" : "一键复制"}
          </button>
        </div>
        <pre className="bg-slate-50 rounded-lg p-3 text-sm whitespace-pre-wrap text-slate-800">
          {data.email_template}
        </pre>
      </div>

      {/* 反例应对 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <h3 className="text-base font-semibold text-slate-800 mb-3">HR 异议应对</h3>
        <div className="space-y-3">
          {data.counter_examples.map((ex, idx) => (
            <div key={idx} className="bg-amber-50 rounded p-3 text-sm whitespace-pre-wrap">
              {ex}
            </div>
          ))}
        </div>
      </div>

      {/* 下一步 */}
      <div className="border rounded-2xl bg-white p-6 shadow-sm">
        <h3 className="text-base font-semibold text-slate-800 mb-3">下一步行动</h3>
        <ol className="list-decimal pl-5 space-y-1 text-sm text-slate-700">
          {data.next_steps.map((s, idx) => (
            <li key={idx}>{s}</li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function KPI({
  label,
  value,
  unit,
  color,
}: {
  label: string;
  value: string;
  unit: string;
  color: "sky" | "indigo" | "rose";
}) {
  const CLS = {
    sky: "bg-sky-50 text-sky-900",
    indigo: "bg-indigo-50 text-indigo-900",
    rose: "bg-rose-50 text-rose-900",
  }[color];
  return (
    <div className={`rounded-lg p-3 text-center ${CLS}`}>
      <div className="text-[10px] uppercase opacity-70">{label}</div>
      <div className="text-base font-semibold mt-1 tabular-nums">{value}</div>
      <div className="text-[9px] opacity-60">{unit}</div>
    </div>
  );
}

function PercentileBar({ percent, band }: { percent: number; band: number[] }) {
  // 把 0-100 映射到百分比
  return (
    <div className="space-y-1">
      <div className="h-2 bg-slate-200 rounded overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-amber-400 to-emerald-500"
          style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
        />
      </div>
      <div className="text-xs text-slate-500">
        当前位于市场分位 p{percent}
      </div>
    </div>
  );
}

export default NegotiationScript;

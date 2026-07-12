"use client";

/**
 * InterviewReport — T2202.
 *
 * Renders the final report: 5-dimension radar + per-dim commentary
 * + strengths / improvements + summary + recommendation.
 */

import { useEffect, useState } from "react";

export interface ReportData {
  interview_id: string;
  persona_id: string;
  role: string;
  overall_score: number;
  recommendation: string;
  dimensions: { name: string; score: number; band: string; comment: string }[];
  radar: Record<string, number>;
  summary: string;
  strengths: string[];
  improvements: string[];
  stage_breakdown: Record<string, { label: string; count: number; avg_score: number; depth: number }>;
  provider?: string;
}

const RECOMMENDATION_LABEL: Record<string, { text: string; color: string }> = {
  strong_yes: { text: "强烈推荐", color: "bg-emerald-500" },
  yes: { text: "推荐", color: "bg-sky-500" },
  consider: { text: "待定", color: "bg-amber-500" },
  no: { text: "不推荐", color: "bg-rose-500" },
};

interface Props {
  report: ReportData;
}

const DIM_KEYS = ["technical", "communication", "thinking", "potential", "culture"];
const DIM_LABELS: Record<string, string> = {
  technical: "技术",
  communication: "沟通",
  thinking: "思维",
  potential: "潜力",
  culture: "文化",
};

export default function InterviewReport({ report }: Props) {
  const radar = report.radar || {};
  const rec = RECOMMENDATION_LABEL[report.recommendation] || RECOMMENDATION_LABEL.consider;
  return (
    <div className="space-y-5" data-testid="interview-report">
      <header className="bg-white rounded-2xl shadow-sm p-5">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-semibold">面试报告</h2>
          <span className="text-sm text-slate-500">
            人格: {report.persona_id} · 岗位: {report.role}
          </span>
          <span className={`ml-auto px-3 py-1 rounded-full text-white text-sm ${rec.color}`}>
            {rec.text}
          </span>
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="rounded-xl bg-slate-50 p-4 text-center">
            <div className="text-3xl font-bold text-slate-800">
              {report.overall_score.toFixed(1)}
            </div>
            <div className="text-xs text-slate-500 mt-1">综合评分</div>
          </div>
          <div className="rounded-xl bg-slate-50 p-4 text-center">
            <div className="text-3xl font-bold text-slate-800">
              {Object.values(report.stage_breakdown || {}).reduce((s, v) => s + v.count, 0)}
            </div>
            <div className="text-xs text-slate-500 mt-1">答题数</div>
          </div>
          <div className="rounded-xl bg-slate-50 p-4 text-center">
            <div className="text-3xl font-bold text-slate-800">
              {report.provider === "mock" || !report.provider ? "离线" : "GPT"}
            </div>
            <div className="text-xs text-slate-500 mt-1">生成引擎</div>
          </div>
        </div>
        <p className="mt-4 text-sm text-slate-700 leading-relaxed">{report.summary}</p>
      </header>

      <section className="bg-white rounded-2xl shadow-sm p-5">
        <h3 className="text-sm font-semibold text-slate-800 mb-3">五维评分</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <RadarChart data={radar} />
          <div className="space-y-2">
            {DIM_KEYS.map((d) => {
              const dim = report.dimensions.find((x) => x.name === DIM_LABELS[d]) || {
                name: DIM_LABELS[d],
                score: radar[d] ?? 0,
                band: "fair",
                comment: "",
              };
              return (
                <div key={d} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-700">{dim.name}</span>
                    <span className="text-sm font-bold text-slate-900">
                      {dim.score.toFixed(1)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        dim.score >= 85
                          ? "bg-emerald-500"
                          : dim.score >= 70
                          ? "bg-sky-500"
                          : dim.score >= 55
                          ? "bg-amber-500"
                          : "bg-rose-500"
                      }`}
                      style={{ width: `${Math.min(100, dim.score)}%` }}
                    />
                  </div>
                  {dim.comment && (
                    <p className="mt-1.5 text-xs text-slate-600 leading-relaxed">{dim.comment}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl shadow-sm p-5">
          <h3 className="text-sm font-semibold text-emerald-700 mb-2">亮点</h3>
          <ul className="space-y-1 text-sm text-slate-700">
            {(report.strengths || []).map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-emerald-500">✓</span>
                <span>{s}</span>
              </li>
            ))}
            {(!report.strengths || report.strengths.length === 0) && (
              <li className="text-slate-400 text-xs">暂无</li>
            )}
          </ul>
        </div>
        <div className="bg-white rounded-2xl shadow-sm p-5">
          <h3 className="text-sm font-semibold text-amber-700 mb-2">待提升</h3>
          <ul className="space-y-1 text-sm text-slate-700">
            {(report.improvements || []).map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-amber-500">→</span>
                <span>{s}</span>
              </li>
            ))}
            {(!report.improvements || report.improvements.length === 0) && (
              <li className="text-slate-400 text-xs">暂无</li>
            )}
          </ul>
        </div>
      </section>

      {Object.keys(report.stage_breakdown || {}).length > 0 && (
        <section className="bg-white rounded-2xl shadow-sm p-5">
          <h3 className="text-sm font-semibold text-slate-800 mb-3">分阶段表现</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Object.entries(report.stage_breakdown).map(([key, v]) => (
              <div
                key={key}
                className="rounded-lg border border-slate-200 p-3 text-center"
                data-testid={`stage-${key}`}
              >
                <div className="text-xs text-slate-500 mb-1">{v.label}</div>
                <div className="text-2xl font-bold text-slate-800">
                  {v.avg_score ? v.avg_score.toFixed(1) : "—"}
                </div>
                <div className="text-[10px] text-slate-400 mt-1">
                  {v.count} 题 · 深度 {(v.depth * 100).toFixed(0)}%
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function RadarChart({ data }: { data: Record<string, number> }) {
  const size = 220;
  const cx = size / 2;
  const cy = size / 2;
  const r = 85;
  const keys = DIM_KEYS;
  const angleStep = (Math.PI * 2) / keys.length;
  const points = keys.map((k, i) => {
    const v = Math.max(0, Math.min(100, data[k] ?? 0)) / 100;
    const a = -Math.PI / 2 + i * angleStep;
    return [cx + Math.cos(a) * r * v, cy + Math.sin(a) * r * v] as const;
  });
  const polygon = points.map((p) => p.join(",")).join(" ");
  const grid = [0.25, 0.5, 0.75, 1].map((scale) => {
    return keys
      .map((_, i) => {
        const a = -Math.PI / 2 + i * angleStep;
        return [cx + Math.cos(a) * r * scale, cy + Math.sin(a) * r * scale].join(",");
      })
      .join(" ");
  });
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[260px] mx-auto" aria-label="雷达图">
      <defs>
        <radialGradient id="radar-fill" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#6366f1" stopOpacity="0.3" />
        </radialGradient>
      </defs>
      {grid.map((g, idx) => (
        <polygon key={idx} points={g} fill="none" stroke="#e2e8f0" strokeWidth="1" />
      ))}
      {keys.map((k, i) => {
        const a = -Math.PI / 2 + i * angleStep;
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r;
        return (
          <line key={k} x1={cx} y1={cy} x2={x} y2={y} stroke="#e2e8f0" strokeWidth="1" />
        );
      })}
      <polygon points={polygon} fill="url(#radar-fill)" stroke="#0284c7" strokeWidth="2" />
      {keys.map((k, i) => {
        const v = data[k] ?? 0;
        const a = -Math.PI / 2 + i * angleStep;
        const lx = cx + Math.cos(a) * (r + 18);
        const ly = cy + Math.sin(a) * (r + 18);
        return (
          <g key={k}>
            <text
              x={lx}
              y={ly}
              fontSize="11"
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-slate-700"
            >
              {DIM_LABELS[k]}
            </text>
            <text
              x={lx}
              y={ly + 12}
              fontSize="10"
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-slate-500"
            >
              {v.toFixed(0)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

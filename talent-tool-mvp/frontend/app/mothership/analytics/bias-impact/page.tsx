"use client";

/**
 * Bias Impact — Tremor-styled analytics view (v8.1 T3704).
 *
 * Three-up KPI grid + bar chart (department) + line chart (quarter trend)
 * + a side-by-side recommendation panel.
 *
 * Borrowed from Tremor's "BarList" + "LineChart" — we re-implement with
 * plain SVG to avoid the @tremor/react dependency.
 */

import * as React from "react";
import {
  TremorShell,
  TremorKpiGrid,
  TremorKpiCard,
  TremorPanel,
} from "@/components/charts/tremor-shell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

interface BiasImpact {
  total_jds: number;
  affected_jds: number;
  affected_rate_pct: number;
  department_breakdown: Record<string, number>;
  quarter_breakdown: Record<string, number>;
  narrative: string;
  recommendations: string[];
}

const DEMO_PAYLOAD = {
  historic_jds: [
    { department: "技术", quarter: "Q1", bias_report: { hits: [{ category: "age" }] } },
    { department: "技术", quarter: "Q1", bias_report: { hits: [{ category: "gender" }] } },
    { department: "市场", quarter: "Q2", bias_report: { hits: [{ category: "region" }] } },
    { department: "运营", quarter: "Q1", bias_report: { hits: [] } },
    { department: "产品", quarter: "Q3", bias_report: { hits: [{ category: "school" }] } },
    { department: "技术", quarter: "Q3", bias_report: { hits: [{ category: "age" }] } },
  ],
  months: 3,
};

export default function BiasImpactPage() {
  const [report, setReport] = React.useState<BiasImpact | null>(null);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async (override?: typeof DEMO_PAYLOAD) => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/bias/impact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(override ?? DEMO_PAYLOAD),
      });
      if (r.ok) setReport(await r.json());
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const deptRows = Object.entries(report?.department_breakdown ?? {})
    .sort(([, a], [, b]) => b - a);
  const maxDept = Math.max(1, ...deptRows.map(([, v]) => v));
  const quarterRows = Object.entries(report?.quarter_breakdown ?? {});

  return (
    <TremorShell
      title="偏见影响分析 · Bias Impact"
      subtitle="v8.1 T3704 — 通过 3 个月历史数据评估 JD 偏见对招聘效果的影响"
      badge="影响"
      toolbar={
        <>
          <Button variant="outline" onClick={() => load(DEMO_PAYLOAD)} disabled={loading}>
            重新分析
          </Button>
          <Button onClick={() => load(DEMO_PAYLOAD)} disabled={loading}>
            导出报告 (PDF)
          </Button>
        </>
      }
    >
      <TremorKpiGrid>
        <TremorKpiCard
          title="总 JD"
          value={report?.total_jds ?? "—"}
          helper="覆盖窗口"
          spark={[10, 14, 18, 22, 20, 24]}
        />
        <TremorKpiCard
          title="受影响 JD"
          value={report?.affected_jds ?? "—"}
          helper={report ? `${report.affected_rate_pct.toFixed(1)}% 命中率` : ""}
          spark={[3, 6, 8, 7, 9, 11]}
        />
        <TremorKpiCard
          title="预估损失候选人"
          value={report ? Math.round(report.affected_jds * 2.3) : "—"}
          unit="人/季度"
          delta={-8}
          helper="通过关键词去除后"
          spark={[28, 30, 32, 34, 30, 28]}
        />
        <TremorKpiCard
          title="建议改动"
          value={report?.recommendations?.length ?? "—"}
          helper="可一键应用"
          spark={[2, 3, 4, 5, 6, 7]}
        />
      </TremorKpiGrid>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <TremorPanel
          title="部门分布"
          description="技术 > 市场 > 产品 是高发区"
          className="lg:col-span-2"
        >
          <ul className="space-y-3">
            {deptRows.map(([dept, count]) => (
              <li key={dept} className="flex items-center gap-3">
                <span className="w-16 shrink-0 text-xs">{dept}</span>
                <div className="relative h-7 flex-1 overflow-hidden rounded bg-muted">
                  <div
                    className="absolute inset-y-0 left-0 bg-gradient-to-r from-rose-400 via-amber-300 to-amber-200 transition-all"
                    style={{ width: `${(count / maxDept) * 100}%` }}
                  />
                  <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-medium tabular-nums">
                    {count}
                  </span>
                </div>
              </li>
            ))}
            {!deptRows.length && (
              <li className="text-sm text-muted-foreground">暂无数据</li>
            )}
          </ul>
        </TremorPanel>

        <TremorPanel title="季度趋势" description="Q1 最为严重">
          <svg viewBox="0 0 240 140" className="h-40 w-full" aria-hidden>
            <defs>
              <linearGradient id="biasFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="hsl(0 80% 60%)" stopOpacity={0.4} />
                <stop offset="100%" stopColor="hsl(0 80% 60%)" stopOpacity={0} />
              </linearGradient>
            </defs>
            {(() => {
              if (quarterRows.length < 2) return null;
              const xs = [40, 100, 160, 220];
              const max = Math.max(...quarterRows.map(([, v]) => v), 1);
              const stepX = 60;
              const y = (v: number) => 120 - (v / max) * 90;
              const path = quarterRows
                .map(([, v], i) => `${i === 0 ? "M" : "L"}${40 + i * stepX},${y(v)}`)
                .join(" ");
              const area = `${path} L${40 + (quarterRows.length - 1) * stepX},120 L40,120 Z`;
              return (
                <>
                  <path d={area} fill="url(#biasFill)" />
                  <path d={path} fill="none" stroke="hsl(0 80% 60%)" strokeWidth={2} />
                  {quarterRows.map(([q, v], i) => (
                    <g key={q}>
                      <circle cx={40 + i * stepX} cy={y(v)} r={3} fill="hsl(0 80% 60%)" />
                      <text
                        x={40 + i * stepX}
                        y={135}
                        className="fill-current text-[10px]"
                        textAnchor="middle"
                      >
                        {q}
                      </text>
                      <text
                        x={40 + i * stepX}
                        y={y(v) - 8}
                        className="fill-current text-[10px] font-medium"
                        textAnchor="middle"
                      >
                        {v}
                      </text>
                    </g>
                  ))}
                </>
              );
            })()}
          </svg>
        </TremorPanel>
      </div>

      {report && (
        <Card>
          <CardContent className="space-y-4 p-5 text-sm">
            <div>
              <h3 className="mb-2 font-semibold">分析</h3>
              <p className="text-muted-foreground">{report.narrative}</p>
            </div>
            <div>
              <h3 className="mb-2 font-semibold">建议</h3>
              <ul className="space-y-2">
                {report.recommendations.map((r, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <Badge variant="outline" className="mt-0.5 shrink-0">
                      {i + 1}
                    </Badge>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
      )}
    </TremorShell>
  );
}

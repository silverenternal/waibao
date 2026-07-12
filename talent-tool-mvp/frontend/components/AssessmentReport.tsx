"use client";

/**
 * AssessmentReport (T1306)
 * 雷达图 (Radar Chart) 渲染测评分数;展示 confidence + 整体分 + 报告链接.
 * 不引入额外依赖,使用 SVG 手动绘制雷达.
 */
import * as React from "react";
import { ExternalLink, AlertCircle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AssessmentResult } from "@/lib/api-assessment";

interface Props {
  result: AssessmentResult;
}

const CONFIDENCE_LABEL: Record<string, string> = {
  very_high: "Very strong",
  high: "Strong",
  medium: "Moderate",
  low: "Weak",
  very_low: "Very weak",
};

const CONFIDENCE_COLOR: Record<string, string> = {
  very_high: "text-emerald-600 bg-emerald-50",
  high: "text-emerald-600 bg-emerald-50",
  medium: "text-amber-600 bg-amber-50",
  low: "text-orange-600 bg-orange-50",
  very_low: "text-red-600 bg-red-50",
};

export function AssessmentReport({ result }: Props) {
  const overall = result.overall_score ?? 0;
  const conf = result.confidence || _confidence(overall);
  const confLabel = CONFIDENCE_LABEL[conf] || "Unknown";
  const confClass = CONFIDENCE_COLOR[conf] || "text-gray-600 bg-gray-50";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Assessment report</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-3xl font-semibold">{overall.toFixed(1)}</p>
            <p className="text-xs text-gray-500">Overall score (0-100)</p>
          </div>
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${confClass}`}
          >
            Confidence: {confLabel}
          </span>
        </div>

        {result.scores?.length ? (
          <RadarChart scores={result.scores} />
        ) : (
          <p className="text-sm text-gray-500">No dimension breakdown.</p>
        )}

        {result.percentile !== undefined && result.percentile !== null && (
          <p className="text-sm text-gray-600">
            Percentile: <strong>P{result.percentile.toFixed(0)}</strong>
          </p>
        )}

        {result.passed !== undefined && result.passed !== null && (
          <p className="text-sm">
            Status:{" "}
            <strong className={result.passed ? "text-emerald-600" : "text-red-600"}>
              {result.passed ? "Passed" : "Failed"}
            </strong>
          </p>
        )}

        {result.status === "pending" && (
          <p className="flex items-center gap-1 text-sm text-amber-600">
            <AlertCircle className="h-4 w-4" /> Candidate has not completed the
            assessment yet.
          </p>
        )}

        {result.report_url && (
          <a
            href={result.report_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
          >
            Open full report <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </CardContent>
    </Card>
  );
}

function _confidence(score: number): string {
  if (score >= 85) return "very_high";
  if (score >= 70) return "high";
  if (score >= 55) return "medium";
  if (score >= 40) return "low";
  return "very_low";
}

// ---------------------------------------------------------------------------
// SVG Radar
// ---------------------------------------------------------------------------
function RadarChart({ scores }: { scores: { name: string; value: number; max: number }[] }) {
  // normalize to 0-100
  const dims = scores.map((s) => ({
    name: s.name,
    pct: Math.max(0, Math.min(100, (s.value / (s.max || 100)) * 100)),
  }));
  const radius = 80;
  const cx = 130;
  const cy = 130;
  const n = dims.length;
  const angle = (2 * Math.PI) / Math.max(1, n);

  const points = dims
    .map((d, i) => {
      const r = (radius * d.pct) / 100;
      const x = cx + r * Math.cos(angle * i - Math.PI / 2);
      const y = cy + r * Math.sin(angle * i - Math.PI / 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const rings = [25, 50, 75, 100].map((pct) => {
    const r = (radius * pct) / 100;
    return (
      <circle
        key={pct}
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="#e5e7eb"
        strokeDasharray="2,2"
      />
    );
  });

  const axes = dims.map((d, i) => {
    const x2 = cx + radius * Math.cos(angle * i - Math.PI / 2);
    const y2 = cy + radius * Math.sin(angle * i - Math.PI / 2);
    const labelX = cx + (radius + 18) * Math.cos(angle * i - Math.PI / 2);
    const labelY = cy + (radius + 18) * Math.sin(angle * i - Math.PI / 2);
    return (
      <g key={d.name}>
        <line x1={cx} y1={cy} x2={x2} y2={y2} stroke="#e5e7eb" />
        <text
          x={labelX}
          y={labelY}
          fontSize="11"
          fill="#374151"
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {d.name}
        </text>
      </g>
    );
  });

  return (
    <div className="flex justify-center">
      <svg viewBox="0 0 260 260" width="260" height="260">
        {rings}
        {axes}
        <polygon
          points={points}
          fill="rgba(99,102,241,0.35)"
          stroke="rgb(99,102,241)"
          strokeWidth="1.5"
        />
      </svg>
    </div>
  );
}

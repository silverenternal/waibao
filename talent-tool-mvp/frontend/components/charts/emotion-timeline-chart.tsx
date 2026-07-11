"use client";

/**
 * EmotionTimelineChart (T605)
 *
 * Recharts-based multi-line view that overlays:
 *   - sentiment (smoothed, primary y-axis)            · blue line
 *   - intensity (secondary y-axis)                    · rose line
 *   - emotion "needs_attention" markers               · red dots w/ tooltip
 *   - one-time events (journal entries with rating)   · light dots
 *
 * Designed to feel calm — gradients, soft tick marks, no harsh grid.
 */

import * as React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Scatter,
  ComposedChart,
  Legend,
} from "recharts";

import { cn } from "@/lib/utils";

export interface EmotionPoint {
  date: string;
  /** -1..1 (sentiment). null when missing. */
  sentiment: number | null;
  /** 0..1 (intensity). null when missing. */
  intensity: number | null;
  /** True when this row should pop an attention marker. */
  needs_attention?: boolean;
  primary_emotion?: string;
  trigger_text?: string | null;
  journal_rating?: "excellent" | "good" | "warning" | null;
  journal_content?: string | null;
}

export interface EmotionTimelineChartProps {
  data: EmotionPoint[];
  height?: number;
  /** Compact variant — omits the secondary axis and event scatter. */
  compact?: boolean;
  className?: string;
  /** Tap a non-null point to drill into its detail. */
  onPointClick?: (point: EmotionPoint) => void;
}

export function EmotionTimelineChart({
  data,
  height = 320,
  compact,
  className,
  onPointClick,
}: EmotionTimelineChartProps) {
  const enriched = React.useMemo(() => {
    return data
      .slice()
      .sort((a, b) => (a.date < b.date ? -1 : 1))
      .map((d) => ({
        ...d,
        sentimentValue: d.sentiment ?? null,
        intensityValue: d.intensity != null ? d.intensity * 100 : null,
        alert: d.needs_attention ? d.sentiment ?? 0 : null,
      }));
  }, [data]);

  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={enriched} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#eef2f7" strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "#475569" }}
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
          />
          <YAxis
            yAxisId="sentiment"
            domain={[-1.05, 1.05]}
            tick={{ fontSize: 11, fill: "#475569" }}
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
            width={48}
          />
          {!compact && (
            <YAxis
              yAxisId="intensity"
              orientation="right"
              domain={[0, 100]}
              tick={{ fontSize: 11, fill: "#475569" }}
              tickLine={false}
              axisLine={{ stroke: "#e2e8f0" }}
              width={40}
            />
          )}

          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine yAxisId="sentiment" y={0} stroke="#cbd5e1" strokeDasharray="2 4" />

          {/* Sentiment line — main channel. */}
          <Line
            yAxisId="sentiment"
            type="monotone"
            dataKey="sentimentValue"
            stroke="#6366f1"
            strokeWidth={2.5}
            dot={(dotProps: { cx?: number; cy?: number; payload?: EmotionPoint; index?: number }) => (
              <ClickableDot
                cx={dotProps.cx ?? 0}
                cy={dotProps.cy ?? 0}
                payload={dotProps.payload}
                index={dotProps.index ?? 0}
                onPointClick={onPointClick}
              />
            )}
            activeDot={{ r: 5, onClick: (_e: unknown) => undefined }}
            isAnimationActive={false}
            name="情绪倾向"
          />

          {!compact && (
            <Line
              yAxisId="intensity"
              type="monotone"
              dataKey="intensityValue"
              stroke="#f97316"
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
              name="强度"
            />
          )}

          {!compact && (
            <Scatter
              yAxisId="sentiment"
              dataKey="alert"
              fill="#f43f5e"
              shape={(props: { cx?: number; cy?: number; index?: number; payload?: EmotionPoint }) => (
                <AlertDot
                  cx={props.cx ?? 0}
                  cy={props.cy ?? 0}
                  payload={props.payload}
                />
              )}
              isAnimationActive={false}
              name="告警事件"
            />
          )}

          {!compact && <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip — bridges to per-point metadata so users can drill down.
// ---------------------------------------------------------------------------

function CustomTooltip(props: { active?: boolean; payload?: any[]; label?: string }) {
  const { active, payload, label } = props;
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0]?.payload as EmotionPoint | undefined;
  if (!datum) return null;
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-slate-700">{label}</p>
      <ul className="space-y-0.5 text-slate-600">
        {datum.primary_emotion && (
          <li>
            主情绪:<span className="ml-1 font-medium">{datum.primary_emotion}</span>
          </li>
        )}
        {datum.sentiment != null && (
          <li>
            情绪倾向:
            <span className="ml-1 tabular-nums">
              {datum.sentiment.toFixed(2)}
            </span>
          </li>
        )}
        {datum.intensity != null && (
          <li>
            强度:
            <span className="ml-1 tabular-nums">
              {Math.round(datum.intensity * 100)}%
            </span>
          </li>
        )}
        {datum.trigger_text && (
          <li className="mt-1 line-clamp-2 text-[11px] text-slate-500">
            “{datum.trigger_text}”
          </li>
        )}
        {datum.journal_rating && (
          <li className="text-[11px]">
            日记评级:
            <span className="ml-1 font-medium">{ratingLabel(datum.journal_rating)}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

function ratingLabel(rating: "excellent" | "good" | "warning"): string {
  switch (rating) {
    case "excellent":
      return "极佳";
    case "good":
      return "稳定";
    case "warning":
      return "需关注";
    default:
      return rating;
  }
}

// ---------------------------------------------------------------------------
// Custom scatter dot — red ring around needs_attention events
// ---------------------------------------------------------------------------

function AlertDot({
  cx,
  cy,
  payload,
}: {
  cx: number;
  cy: number;
  payload?: EmotionPoint;
}) {
  if (!payload?.needs_attention || cx == null || cy == null) return null;
  return (
    <g>
      <circle cx={cx} cy={cy} r={9} fill="#f43f5e22" />
      <circle cx={cx} cy={cy} r={5} fill="#f43f5e" />
    </g>
  );
}

// ---------------------------------------------------------------------------
// Clickable dot — small invisible-by-default hitbox so users can drill in
// ---------------------------------------------------------------------------

function ClickableDot({
  cx,
  cy,
  payload,
  index,
  onPointClick,
}: {
  cx: number;
  cy: number;
  payload?: EmotionPoint;
  index: number;
  onPointClick?: (point: EmotionPoint) => void;
}) {
  if (cx == null || cy == null || !payload) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={3}
      fill="#6366f1"
      onClick={() => onPointClick?.(payload)}
      style={{ cursor: onPointClick ? "pointer" : "default" }}
      data-index={index}
    />
  );
}

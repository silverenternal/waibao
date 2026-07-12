"use client";

/**
 * T2304 — 静默时间拖动选择器.
 *
 * 设计:
 * - 24 小时滑块 (00:00 - 24:00), 圆点可拖
 * - 区间 [start, end) 显示为高亮条带; 跨午夜 (例: 22:00-08:00) 自动从 24 折回到 0
 * - start > end 表示跨午夜; start === end 表示无静默
 *
 * Props:
 *  - start, end: "HH:MM" 字符串
 *  - onChange: (start, end) => void
 */

import * as React from "react";
import { Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

export interface QuietHoursPickerProps {
  start: string | null;
  end: string | null;
  onChange: (start: string | null, end: string | null) => void;
  disabled?: boolean;
}

const HOURS = 24;
const HOUR_PCT = 100 / HOURS;

function toMinutes(hhmm: string | null): number | null {
  if (!hhmm) return null;
  const m = /^(\d{1,2}):(\d{2})$/.exec(hhmm);
  if (!m) return null;
  const h = parseInt(m[1], 10);
  const mm = parseInt(m[2], 10);
  if (h < 0 || h > 24 || mm < 0 || mm >= 60) return null;
  return h * 60 + mm;
}

function toHHMM(minutes: number): string {
  const m = Math.max(0, Math.min(24 * 60, Math.round(minutes)));
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function pct(minutes: number | null): number {
  if (minutes == null) return 0;
  return (minutes / (24 * 60)) * 100;
}

export function QuietHoursPicker(props: QuietHoursPickerProps) {
  const { start, end, onChange, disabled } = props;

  const startMin = toMinutes(start) ?? 22 * 60;
  const endMin = toMinutes(end) ?? 8 * 60;
  const isCrossMidnight = startMin >= endMin;

  const trackRef = React.useRef<HTMLDivElement | null>(null);
  const draggingRef = React.useRef<"start" | "end" | null>(null);

  const handlePos = React.useCallback(
    (clientX: number) => {
      const el = trackRef.current;
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      return Math.round(ratio * 24 * 60);
    },
    [],
  );

  const commit = React.useCallback(
    (which: "start" | "end", minutes: number) => {
      const newStart = which === "start" ? minutes : startMin;
      const newEnd = which === "end" ? minutes : endMin;
      onChange(toHHMM(newStart), toHHMM(newEnd));
    },
    [startMin, endMin, onChange],
  );

  const onPointerDown = (which: "start" | "end") => (e: React.PointerEvent) => {
    if (disabled) return;
    draggingRef.current = which;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!draggingRef.current) return;
    const m = handlePos(e.clientX);
    if (m == null) return;
    commit(draggingRef.current, m);
  };
  const onPointerUp = (e: React.PointerEvent) => {
    draggingRef.current = null;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* noop */
    }
  };

  const onStartInput = (v: string) => onChange(v || null, end);
  const onEndInput = (v: string) => onChange(start, v || null);

  const clear = () => onChange(null, null);

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950"
      data-testid="quiet-hours-picker"
    >
      <div className="mb-3 flex items-center justify-between">
        <Label className="flex items-center gap-2 text-sm font-semibold">
          <Moon className="h-4 w-4 text-indigo-500" aria-hidden="true" />
          静默时间
        </Label>
        <button
          type="button"
          onClick={clear}
          disabled={disabled || (!start && !end)}
          className="text-xs text-slate-500 underline-offset-2 hover:underline disabled:opacity-50"
        >
          清除
        </button>
      </div>

      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        在该时间段内通知将被静默 (不发送); 支持跨午夜 (例如 22:00 - 08:00).
      </p>

      {/* 滑块 */}
      <div className="select-none">
        <div
          ref={trackRef}
          className="relative h-12 w-full rounded-md bg-gradient-to-r from-indigo-100 via-amber-50 to-indigo-100 dark:from-indigo-950 dark:via-amber-950/30 dark:to-indigo-950"
          role="slider"
          aria-label="静默时间段"
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          {/* 高亮区段 */}
          {start && end && (
            <>
              {/* 起始 -> 24 (若跨午夜) */}
              {isCrossMidnight && (
                <div
                  className="absolute top-0 h-full bg-indigo-500/40 dark:bg-indigo-400/40"
                  style={{
                    left: `${pct(startMin)}%`,
                    width: `${100 - pct(startMin)}%`,
                  }}
                />
              )}
              {/* 0 -> 结束 */}
              <div
                className={cn(
                  "absolute top-0 h-full bg-indigo-500/40 dark:bg-indigo-400/40",
                  !isCrossMidnight && "rounded-md",
                )}
                style={
                  isCrossMidnight
                    ? { left: 0, width: `${pct(endMin)}%` }
                    : {
                        left: `${pct(startMin)}%`,
                        width: `${pct(endMin) - pct(startMin)}%`,
                      }
                }
              />
            </>
          )}

          {/* 起始 handle */}
          {start && (
            <button
              type="button"
              disabled={disabled}
              onPointerDown={onPointerDown("start")}
              aria-label="开始时间"
              className="absolute top-0 h-full w-3 -translate-x-1/2 cursor-grab touch-none rounded-full bg-indigo-600 ring-2 ring-white shadow"
              style={{ left: `${pct(startMin)}%` }}
            />
          )}

          {/* 结束 handle */}
          {end && (
            <button
              type="button"
              disabled={disabled}
              onPointerDown={onPointerDown("end")}
              aria-label="结束时间"
              className="absolute top-0 h-full w-3 -translate-x-1/2 cursor-grab touch-none rounded-full bg-indigo-600 ring-2 ring-white shadow"
              style={{ left: `${pct(endMin)}%` }}
            />
          )}

          {/* 时刻刻度 */}
          {[0, 6, 12, 18, 24].map((h) => (
            <span
              key={h}
              className="absolute -bottom-4 -translate-x-1/2 text-[10px] text-slate-400"
              style={{ left: `${(h / 24) * 100}%` }}
            >
              {String(h).padStart(2, "0")}
            </span>
          ))}
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs text-slate-500">开始</Label>
            <Input
              type="time"
              value={start ?? ""}
              disabled={disabled}
              onChange={(e) => onStartInput(e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-slate-500">结束</Label>
            <Input
              type="time"
              value={end ?? ""}
              disabled={disabled}
              onChange={(e) => onEndInput(e.target.value)}
              className="mt-1"
            />
          </div>
        </div>

        <p className="mt-3 flex items-center gap-1 text-xs text-slate-500">
          <Sun className="h-3 w-3" aria-hidden="true" />
          {isCrossMidnight
            ? `跨午夜: ${start} → 次日 ${end}`
            : `同日: ${start ?? "--:--"} → ${end ?? "--:--"}`}
        </p>
      </div>
    </div>
  );
}

export default QuietHoursPicker;
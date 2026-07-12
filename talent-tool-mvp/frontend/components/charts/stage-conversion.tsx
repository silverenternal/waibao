"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface StageConversionProps {
  conversionRates: Record<string, number>;
  className?: string;
}

const STAGE_LABELS: Record<string, string> = {
  sourced: "Sourced",
  applied: "Applied",
  screened: "Screened",
  interviewed: "Interviewed",
  offered: "Offered",
  hired: "Hired",
};

/** 把 ``sourced_to_applied`` 这样的 key 翻译成 "Sourced → Applied". */
function prettyKey(k: string): { from: string; to: string } {
  const [from, to] = k.split("_to_");
  return {
    from: STAGE_LABELS[from] ?? from,
    to: STAGE_LABELS[to] ?? to,
  };
}

export function StageConversion({
  conversionRates,
  className,
}: StageConversionProps) {
  const rows = useMemo(
    () =>
      Object.entries(conversionRates).map(([k, v]) => ({
        key: k,
        value: v,
        ...prettyKey(k),
      })),
    [conversionRates],
  );

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No stage transitions recorded yet.
      </p>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      {rows.map((row) => {
        const tone =
          row.value >= 50
            ? "bg-emerald-500"
            : row.value >= 25
              ? "bg-amber-500"
              : "bg-red-500";
        return (
          <div key={row.key} className="text-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-muted-foreground">
                {row.from} → {row.to}
              </span>
              <span className="font-medium">{row.value.toFixed(1)}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={cn("h-full transition-all duration-300", tone)}
                style={{ width: `${Math.min(100, row.value)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
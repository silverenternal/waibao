"use client";

/**
 * T2301 — CompareDiff
 * 差异点高亮卡片 — 自动列出 top-3 差异维度及说明.
 */

import { CompareRadar, type RadarSeries } from "./CompareRadar";
import { cn } from "@/lib/utils";

export interface DiffDimension {
  dimension: string;
  label: string;
  spread: number;
  stddev: number;
  values: number[];
  items: string[];
  rank: number;
}

export interface CompareItemLite {
  id: string;
  name: string;
  values: Record<string, number>;
}

interface CompareDiffProps {
  items: CompareItemLite[];
  highlights: DiffDimension[];
  className?: string;
}

export function CompareDiff({
  items,
  highlights,
  className,
}: CompareDiffProps) {
  const dimensions = highlights.map((h) => ({
    key: h.dimension,
    label: h.label,
  }));

  const series: RadarSeries[] = items.map((it) => ({
    id: it.id,
    name: it.name,
    values: it.values,
  }));

  return (
    <div className={cn("space-y-6", className)}>
      <div>
        <h3 className="text-sm font-semibold mb-2">差异最大的 3 个维度</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {highlights.map((h) => (
            <DiffCard key={h.dimension} dim={h} items={items} />
          ))}
        </div>
      </div>
      <div>
        <h3 className="text-sm font-semibold mb-2">差异维度雷达图</h3>
        {dimensions.length > 0 ? (
          <CompareRadar series={series} dimensions={dimensions} />
        ) : (
          <div className="text-sm text-muted-foreground">无差异数据</div>
        )}
      </div>
    </div>
  );
}

function DiffCard({
  dim,
  items,
}: {
  dim: DiffDimension;
  items: CompareItemLite[];
}) {
  const winnerIdx = dim.values.indexOf(Math.max(...dim.values));
  const loserIdx = dim.values.indexOf(Math.min(...dim.values));
  const winner = items[winnerIdx];
  const loser = items[loserIdx];

  return (
    <div
      className={cn(
        "rounded-lg border p-4 bg-gradient-to-br",
        "from-amber-50 to-white dark:from-amber-950/30 dark:to-background"
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-200 dark:bg-amber-800 text-amber-900 dark:text-amber-100">
          #{dim.rank}
        </span>
        <span className="text-xs text-muted-foreground">
          stddev {dim.stddev.toFixed(1)}
        </span>
      </div>
      <h4 className="font-semibold text-base mb-3">{dim.label}</h4>
      <div className="text-xs text-muted-foreground mb-2">
        差异 {dim.spread.toFixed(1)} 分
      </div>
      {winner && loser && winner.id !== loser.id && (
        <div className="space-y-1 text-xs">
          <div className="flex justify-between">
            <span className="text-emerald-600 font-medium">{winner.name}</span>
            <span className="font-semibold">
              {dim.values[winnerIdx].toFixed(1)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-red-500 font-medium">{loser.name}</span>
            <span className="font-semibold">
              {dim.values[loserIdx].toFixed(1)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
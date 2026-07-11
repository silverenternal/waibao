/**
 * CacheHitRateGauge (T806) — 圆环进度条显示 LLM cache 命中率.
 */
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { CacheStats } from "@/lib/api-cost";

interface CacheHitRateGaugeProps {
  stats: CacheStats;
}

export function CacheHitRateGauge({ stats }: CacheHitRateGaugeProps) {
  const rate = Math.max(0, Math.min(1, stats.hit_rate));
  const pct = (rate * 100).toFixed(1);
  const radius = 70;
  const circ = 2 * Math.PI * radius;
  const dash = circ * rate;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">LLM Cache</CardTitle>
        <Badge variant={stats.redis_healthy ? "default" : "outline"}>
          {stats.redis_healthy ? "Redis OK" : "Memory fallback"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-center">
          <svg width="180" height="180" viewBox="0 0 180 180" aria-label={`Hit rate ${pct}%`}>
            <circle
              cx="90"
              cy="90"
              r={radius}
              fill="none"
              stroke="hsl(var(--muted))"
              strokeWidth="14"
            />
            <circle
              cx="90"
              cy="90"
              r={radius}
              fill="none"
              stroke="hsl(var(--primary))"
              strokeWidth="14"
              strokeDasharray={`${dash} ${circ}`}
              strokeLinecap="round"
              transform="rotate(-90 90 90)"
            />
            <text
              x="90"
              y="86"
              textAnchor="middle"
              fontSize="24"
              fontWeight="600"
              fill="hsl(var(--foreground))"
            >
              {pct}%
            </text>
            <text
              x="90"
              y="106"
              textAnchor="middle"
              fontSize="11"
              fill="hsl(var(--muted-foreground))"
            >
              hit rate
            </text>
          </svg>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          <Stat label="Hits" value={stats.hits.toLocaleString()} />
          <Stat label="Misses" value={stats.misses.toLocaleString()} />
          <Stat label="Writes" value={stats.writes.toLocaleString()} />
        </div>
        <div className="grid grid-cols-3 gap-3 text-xs text-muted-foreground text-center">
          <Stat label="Memory size" value={`${stats.memory_size}`} />
          <Stat label="TTL" value={`${stats.ttl_seconds}s`} />
          <Stat label="Write fails" value={`${stats.write_failures}`} />
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border py-2">
      <div className="text-base font-mono">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
    </div>
  );
}

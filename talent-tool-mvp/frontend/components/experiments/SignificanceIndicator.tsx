/**
 * SignificanceIndicator (T805): 显著性徽标 + p-value 可视化.
 */
"use client";

import { Badge } from "@/components/ui/badge";

interface SignificanceIndicatorProps {
  confidence: number;
  pValue: number;
  significant: boolean;
  className?: string;
}

export function SignificanceIndicator({
  confidence,
  pValue,
  significant,
  className,
}: SignificanceIndicatorProps) {
  const pct = Math.max(0, Math.min(1, confidence));
  const pDisplay = pValue < 0.001 ? "<0.001" : pValue.toFixed(3);
  return (
    <div className={`flex items-center gap-3 ${className ?? ""}`}>
      <Badge variant={significant ? "default" : "secondary"}>
        {significant ? "Significant" : "Not significant"}
      </Badge>
      <div className="text-xs text-muted-foreground">
        confidence{" "}
        <span className="font-mono">{(pct * 100).toFixed(1)}%</span>, p{" "}
        <span className="font-mono">{pDisplay}</span>
      </div>
      <div className="h-2 w-24 rounded-full bg-muted overflow-hidden" aria-hidden="true">
        <div
          className={`h-full ${significant ? "bg-emerald-500" : "bg-amber-400"}`}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
    </div>
  );
}

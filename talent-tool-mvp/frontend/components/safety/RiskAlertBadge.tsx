"use client";

/**
 * v11.0 T6110 — Compact risk-alert badge for HR / admin surfaces.
 *
 * Shows only the redacted risk_level + rule label (no verbatim conversation).
 * Critical (self-harm) renders as a pulsing red badge; high (labour dispute)
 * as amber.  Clicking it optionally calls back (e.g. to open the alert row).
 */
import * as React from "react";
import { AlertTriangle, Heart } from "lucide-react";

import { cn } from "@/lib/utils";
import type { EscalationRule, RiskLevel } from "@/lib/api-safety";

export interface RiskAlertBadgeProps {
  rule: EscalationRule;
  risk_level: RiskLevel;
  /** Show the reason tooltip (already PII-free on the backend). */
  reason?: string;
  size?: "sm" | "md";
  className?: string;
  onClick?: () => void;
}

const LABELS: Record<EscalationRule, string> = {
  self_harm: "自伤风险",
  labour_dispute: "劳动争议",
};

export function RiskAlertBadge({
  rule,
  risk_level,
  reason,
  size = "md",
  className,
  onClick,
}: RiskAlertBadgeProps) {
  const critical = risk_level === "critical";
  const Icon = critical ? Heart : AlertTriangle;

  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      title={reason || `${LABELS[rule]} · ${risk_level}`}
      aria-label={`${LABELS[rule]} 风险等级 ${risk_level}`}
      className={cn(
        "inline-flex w-fit items-center gap-1 rounded-full border font-medium",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
        critical
          ? "border-rose-300 bg-rose-100 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"
          : "border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200",
        onClick && "cursor-pointer hover:opacity-80",
        critical && "animate-pulse",
        className
      )}
    >
      <Icon className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} />
      <span>{LABELS[rule]}</span>
      <span className="opacity-70">· {risk_level}</span>
    </button>
  );
}

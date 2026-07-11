"use client";

/**
 * LegalRiskBadge (T601)
 *
 * Small badge used by `PolicyList` and `PolicyDetail` to communicate the
 * crude risk score attached to a clause / policy. Three tones:
 *   low (emerald) · medium (amber) · high (rose).
 *
 * Pure presentation; data flows in via props.
 */

import * as React from "react";
import { ShieldAlert, ShieldCheck, Shield } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  RISK_BADGE,
  type LegalRiskLevel,
  riskLevelFromScore,
} from "@/lib/api-policy";

export interface LegalRiskBadgeProps {
  /** Either pass the level directly, or a 0..1 score for the helper. */
  level?: LegalRiskLevel | null;
  score?: number | null;
  /** Override the displayed label. */
  label?: string;
  /** Show the icon (default true). */
  showIcon?: boolean;
  size?: "sm" | "md";
  className?: string;
}

export function LegalRiskBadge({
  level,
  score,
  label,
  showIcon = true,
  size = "md",
  className,
}: LegalRiskBadgeProps) {
  const resolved: LegalRiskLevel =
    level ?? riskLevelFromScore(score);
  const cfg = RISK_BADGE[resolved];
  const Icon =
    resolved === "high" ? ShieldAlert : resolved === "medium" ? Shield : ShieldCheck;

  return (
    <span
      title={
        score != null
          ? `风险分 ${(score * 100).toFixed(0)} / 100`
          : cfg.label
      }
      className={cn(
        "inline-flex items-center gap-1 rounded-full border font-medium",
        cfg.wrap,
        size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs",
        className,
      )}
    >
      {showIcon && <Icon className={size === "sm" ? "size-3" : "size-3.5"} />}
      {label ?? cfg.label}
    </span>
  );
}

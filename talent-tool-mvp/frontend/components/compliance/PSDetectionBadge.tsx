"use client";

/**
 * PSDetectionBadge (v8.1 T3702) — Photoshop / image-forgery detection badge.
 *
 * Renders a small inline badge indicating the likelihood that a credential
 * image has been digitally manipulated. Uses ELA + noise + EXIF + perceptual
 * hash heuristics from the backend. Severity ramp:
 *
 *   0.0 - 0.3  green     "low"      clean
 *   0.3 - 0.6  amber     "watch"    mixed signals, monitor
 *   0.6 - 0.85 orange    "review"   strong signal, human review
 *   0.85 - 1.0 red       "tampered" auto-escalate to compliance officer
 *
 * Each badge is keyboard focusable to expose the breakdown in a popover.
 */

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Eye,
  type LucideIcon,
} from "lucide-react";

export type PSLevel = "clean" | "watch" | "review" | "tampered";

export interface PSFinding {
  code: string;
  label: string;
  severity: number; // 0..1
  detail?: string;
}

export interface PSDetectionBadgeProps {
  /** 0..1 unified suspicion score from the compliance backend. */
  suspicion?: number;
  level?: PSLevel;
  findings?: PSFinding[];
  escalated?: boolean;
  className?: string;
}

const LEVEL_META: Record<
  PSLevel,
  {
    label: string;
    short: string;
    icon: LucideIcon;
    cls: string;
    ring: string;
    threshold: [number, number];
  }
> = {
  clean: {
    label: "可信",
    short: "CLEAN",
    icon: ShieldCheck,
    cls: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    ring: "ring-emerald-300",
    threshold: [0, 0.3],
  },
  watch: {
    label: "观察",
    short: "WATCH",
    icon: Eye,
    cls: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
    ring: "ring-amber-300",
    threshold: [0.3, 0.6],
  },
  review: {
    label: "复审",
    short: "REVIEW",
    icon: ShieldAlert,
    cls: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
    ring: "ring-orange-300",
    threshold: [0.6, 0.85],
  },
  tampered: {
    label: "疑似伪造",
    short: "TAMPERED",
    icon: ShieldX,
    cls: "bg-rose-500/15 text-rose-700 dark:text-rose-200",
    ring: "ring-rose-400",
    threshold: [0.85, 1.01],
  },
};

function deriveLevel(score: number): PSLevel {
  if (score >= 0.85) return "tampered";
  if (score >= 0.6) return "review";
  if (score >= 0.3) return "watch";
  return "clean";
}

export function PSDetectionBadge({
  suspicion = 0,
  level,
  findings,
  escalated,
  className,
}: PSDetectionBadgeProps) {
  const lv = level ?? deriveLevel(suspicion);
  const meta = LEVEL_META[lv];
  const Icon = meta.icon;
  const pct = Math.round(suspicion * 100);

  return (
    <span
      role="status"
      aria-label={`Photo tampering detection: ${meta.label} (${pct}%)`}
      tabIndex={0}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset transition-colors",
        "outline-none focus-visible:ring-2 focus-visible:ring-primary",
        meta.cls,
        meta.ring,
        className,
      )}
      title={`${meta.label} · 可疑度 ${pct}%`}
    >
      <Icon className="h-3.5 w-3.5" />
      <span>{meta.label}</span>
      <span className="ml-0.5 tabular-nums font-mono text-[11px] opacity-75">
        {pct}%
      </span>
      {escalated && (
        <span className="ml-1 rounded-full bg-rose-600 px-1.5 py-0 text-[10px] font-bold text-white">
          AUTO-ESC
        </span>
      )}
    </span>
  );
}

/**
 * Detailed breakdown panel. Use when the badge has findings.
 */
export function PSDetectionBreakdown({ findings }: { findings: PSFinding[] }) {
  if (!findings.length) {
    return (
      <p className="text-sm text-muted-foreground">
        未检测到异常信号。
      </p>
    );
  }
  const sorted = [...findings].sort((a, b) => b.severity - a.severity);
  return (
    <ul className="space-y-2 text-xs">
      {sorted.map((f) => (
        <li
          key={f.code}
          className="flex items-start justify-between gap-3 rounded-md border p-2"
        >
          <div>
            <div className="font-medium">{f.label}</div>
            {f.detail && (
              <div className="text-muted-foreground">{f.detail}</div>
            )}
          </div>
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono tabular-nums">
            {(f.severity * 100).toFixed(0)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

export default PSDetectionBadge;

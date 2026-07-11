"use client";

/**
 * LegalHint (T603)
 *
 * Persistent disclaimer card reminding the user that the bias alerts
 * above are advisory only — not legal advice. Picks one of three tones
 * based on the highest severity in the supplied list:
 *
 *   high   → rose-red banner
 *   medium → amber banner
 *   low    → emerald banner
 *
 * Optionally renders a list of relevant Chinese / UK laws if supplied.
 */

import * as React from "react";
import { Scale, Gavel, ExternalLink } from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

import type { BiasSeverity } from "./BiasAlert";

export interface LegalHintProps {
  /** Highest severity found in the current analysis — drives the tone. */
  severity?: BiasSeverity | null;
  /** Names of relevant laws / regulations. */
  references?: string[];
  /** Free-form explanation text (defaults to boilerplate). */
  description?: string;
  /** Optional callback when the user clicks "咨询合规顾问". */
  onConsult?: () => void;
  className?: string;
}

const TONE: Record<
  BiasSeverity,
  { wrap: string; icon: string; pill: string }
> = {
  low: {
    wrap: "border-emerald-200 bg-emerald-50/60",
    icon: "text-emerald-500",
    pill: "border-emerald-300 bg-emerald-100 text-emerald-700",
  },
  medium: {
    wrap: "border-amber-200 bg-amber-50/60",
    icon: "text-amber-500",
    pill: "border-amber-300 bg-amber-100 text-amber-700",
  },
  high: {
    wrap: "border-rose-200 bg-rose-50/60",
    icon: "text-rose-500",
    pill: "border-rose-300 bg-rose-100 text-rose-700",
  },
};

export function LegalHint({
  severity,
  references,
  description,
  onConsult,
  className,
}: LegalHintProps) {
  const sev = (severity ?? "low") as BiasSeverity;
  const cfg = TONE[sev];

  return (
    <Card className={cn("overflow-hidden", cfg.wrap, className)}>
      <CardContent className="space-y-2 py-4">
        <header className="flex items-start gap-2">
          <span
            className={cn(
              "grid size-8 shrink-0 place-items-center rounded-full bg-white shadow-sm ring-1 ring-black/5",
              cfg.icon,
            )}
          >
            <Gavel className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Scale className="size-3.5 text-slate-500" />
              合规提示
              <Badge variant="outline" className={cn("ml-auto text-[10px]", cfg.pill)}>
                {sev === "high"
                  ? "可能违反劳动法"
                  : sev === "medium"
                    ? "建议复核"
                    : "风险较低"}
              </Badge>
            </h3>
            <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-slate-700">
              {description ??
                "以上偏见提示仅供参考,不构成法律意见。建议在发布前由合规或法务同事复核,并保留修订记录。"}
            </p>
          </div>
        </header>

        {references && references.length > 0 && (
          <details className="rounded-md border border-slate-200 bg-white/70 px-3 py-2 text-xs">
            <summary className="flex cursor-pointer items-center gap-1 font-medium text-slate-700">
              <ExternalLink className="size-3.5" />
              适用法规 (供参考)
            </summary>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[11px] text-slate-600">
              {references.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </details>
        )}

        {onConsult && (
          <button
            type="button"
            onClick={onConsult}
            className="block w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 transition hover:border-blue-300 hover:text-blue-700"
          >
            咨询合规顾问 →
          </button>
        )}
      </CardContent>
    </Card>
  );
}

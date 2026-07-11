"use client";

/**
 * AlternativeWording (T603)
 *
 * Side-by-side rewrite: original phrasing vs. suggested alternative
 * supplied by the talent_brief agent. Renders an inline swap with a
 * single-click "use this" interaction that fires `onApply(original, alt)`.
 *
 * Designed to be slotted into the talent brief response area below
 * `BiasAlert`. The page can also stack several of these — one per
 * suggestion — without configuration.
 */

import * as React from "react";
import { ArrowRight, Wand2, Check } from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export interface AlternativeWordingProps {
  original: string;
  alternative: string;
  /** Why we suggest this rewrite — derived from the bias explanation. */
  rationale?: string;
  /** A free-form category label ("年龄", "学历", …). */
  category?: string;
  /** Apply handler — page reuses this to mutate the textarea. */
  onApply?: (original: string, alternative: string) => void;
  /** Whether this alternative is already applied (UI marks it). */
  applied?: boolean;
  className?: string;
}

export function AlternativeWording({
  original,
  alternative,
  rationale,
  category,
  onApply,
  applied,
  className,
}: AlternativeWordingProps) {
  return (
    <Card
      className={cn(
        "overflow-hidden",
        applied ? "border-emerald-200 bg-emerald-50/40" : "border-slate-200",
        className,
      )}
    >
      <CardContent className="space-y-3 py-3">
        <header className="flex items-center gap-2 text-[11px] text-slate-500">
          <Wand2 className="size-3.5 text-violet-500" />
          <span>替代话术</span>
          {category && (
            <Badge variant="outline" className="ml-auto text-[10px]">
              {category}
            </Badge>
          )}
        </header>

        <ol className="space-y-2 text-xs">
          <li className="flex items-start gap-2">
            <span className="mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-700">
              原
            </span>
            <p className="line-through text-slate-500">{original}</p>
          </li>
          <li className="flex items-center gap-2 text-[10px] text-slate-400">
            <ArrowRight className="size-3" />
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-semibold text-white">
              替
            </span>
            <p className="font-medium text-slate-800">{alternative}</p>
          </li>
        </ol>

        {rationale && (
          <p className="rounded-md border border-blue-200 bg-blue-50/40 px-2 py-1 text-[11px] text-blue-700">
            <span className="font-semibold">理由:</span> {rationale}
          </p>
        )}

        {onApply && (
          <Button
            size="sm"
            variant={applied ? "secondary" : "default"}
            className="w-full"
            disabled={applied}
            onClick={() => onApply(original, alternative)}
          >
            {applied ? (
              <>
                <Check className="mr-1 size-3.5" />
                已应用
              </>
            ) : (
              <>
                <Wand2 className="mr-1 size-3.5" />
                用这一版替换原文
              </>
            )}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

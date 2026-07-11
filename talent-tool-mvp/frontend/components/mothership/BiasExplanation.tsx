"use client";

/**
 * BiasExplanation (T603)
 *
 * Compact, single-row explanation card that names the bias and explains
 * *why* it matters. Used inside `AlternativeWording` and as a smaller
 * alternative to `BiasAlert` for narrow surfaces.
 *
 * Two-line layout:
 *   🏷  类型 · 数据 / 法律依据  ①
 *   解释文案 + 可选法律依据链接
 */

import * as React from "react";
import { Info, Scale } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export type BiasKind =
  | "age"
  | "gender"
  | "education"
  | "marriage"
  | "region"
  | "appearance"
  | "language"
  | "other";

const KIND_LABEL: Record<BiasKind, string> = {
  age: "年龄",
  gender: "性别",
  education: "学历",
  marriage: "婚育",
  region: "地域",
  appearance: "形象 / 颜值",
  language: "语言偏好",
  other: "其他",
};

export interface BiasExplanationProps {
  type: string | BiasKind;
  /** "why this matters" — drawn from the agent's explanation. */
  explanation: string;
  /** Optional legal framework reference shown as a footnote. */
  legalReference?: string;
  /** Optional click handler to expand more detail. */
  onLearnMore?: () => void;
  className?: string;
}

export function BiasExplanation({
  type,
  explanation,
  legalReference,
  onLearnMore,
  className,
}: BiasExplanationProps) {
  const label = lookupLabel(type);
  return (
    <div
      className={cn(
        "rounded-lg border border-blue-200 bg-blue-50/40 p-3 text-xs",
        className,
      )}
    >
      <header className="mb-1 flex items-center gap-2">
        <Badge
          variant="outline"
          className="border-blue-300 bg-blue-100 text-[10px] text-blue-700"
        >
          {label}
        </Badge>
        <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-blue-700">
          <Info className="size-3" />
          为什么这是问题?
        </span>
      </header>
      <p className="leading-relaxed text-slate-700">{explanation}</p>
      {legalReference && (
        <p className="mt-1 inline-flex items-center gap-1 text-[10px] text-slate-500">
          <Scale className="size-3" />
          法律依据 · {legalReference}
        </p>
      )}
      {onLearnMore && (
        <button
          type="button"
          onClick={onLearnMore}
          className="mt-1 block text-[10px] text-blue-700 underline-offset-2 hover:underline"
        >
          了解更多 →
        </button>
      )}
    </div>
  );
}

function lookupLabel(type: string | BiasKind): string {
  if (type in KIND_LABEL) return KIND_LABEL[type as BiasKind];
  return type;
}

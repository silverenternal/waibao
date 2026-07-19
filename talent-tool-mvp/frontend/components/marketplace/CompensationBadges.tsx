"use client";

/**
 * v11.2 (T6302) — CompensationBadges.
 *
 * Renders the 五险一金 / 公积金 / 出差 compensation tags for a marketplace card.
 * These are HIGH-priority match factors (soft scoring, never eliminate per
 * 甲方 rule "没有淘汰只做增量"). They appear on both talent cards (the
 * candidate's expectations) and job cards (the role's offers).
 *
 * Two shapes share one component:
 *   - <CompensationBadges variant="talent" travelTolerance socialInsuranceExpectation />
 *   - <CompensationBadges variant="job"    travelRequired offersSocialInsurance offersHousingFund />
 *
 * Purely presentational; tolerant of missing fields (masked/anonymous cards).
 * Compact, mobile-friendly, accessible (badges are decorative; a wrapping
 * <ul role="list"> keeps SR order deterministic).
 */
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  travelRequiredLabel,
  travelToleranceLabel,
  type TravelRequirement,
  type TravelTolerance,
} from "@/lib/api-talent-market";

export interface CompensationBadgesTalentProps {
  variant: "talent";
  socialInsuranceExpectation?: boolean | null;
  travelTolerance?: TravelTolerance | null;
  className?: string;
}

export interface CompensationBadgesJobProps {
  variant: "job";
  offersSocialInsurance?: boolean | null;
  offersHousingFund?: boolean | null;
  travelRequired?: TravelRequirement | null;
  className?: string;
}

export type CompensationBadgesProps =
  | CompensationBadgesTalentProps
  | CompensationBadgesJobProps;

export function CompensationBadges(props: CompensationBadgesProps) {
  const items: { key: string; label: string; tone: "emerald" | "amber" | "slate" }[] = [];

  if (props.variant === "talent") {
    const wants = props.socialInsuranceExpectation;
    if (wants === true) {
      items.push({ key: "si", label: "期望五险一金", tone: "emerald" });
    } else if (wants === false) {
      items.push({ key: "si", label: "五险一金非必须", tone: "slate" });
    }
    const travel = travelToleranceLabel(props.travelTolerance);
    if (travel) {
      items.push({
        key: "travel",
        label: travel,
        tone:
          props.travelTolerance === "willing"
            ? "emerald"
            : props.travelTolerance === "unwilling"
              ? "amber"
              : "slate",
      });
    }
  } else {
    const offers = props.offersSocialInsurance;
    if (offers !== false && offers !== undefined && offers !== null) {
      items.push({ key: "si", label: "五险一金", tone: "emerald" });
    }
    if (props.offersHousingFund) {
      items.push({ key: "hf", label: "含公积金", tone: "emerald" });
    }
    const travel = travelRequiredLabel(props.travelRequired);
    if (travel) {
      items.push({
        key: "travel",
        label: travel,
        tone:
          props.travelRequired === "frequent"
            ? "amber"
            : "slate",
      });
    }
  }

  if (items.length === 0) return null;

  return (
    <ul
      role="list"
      className={cn("flex flex-wrap gap-1.5", props.className)}
      aria-label="薪酬与出差"
    >
      {items.map((it) => (
        <li key={it.key}>
          <Badge
            variant="outline"
            className={cn(
              "h-6 px-2 text-[11px] font-normal",
              it.tone === "emerald" &&
                "border-emerald-300 text-emerald-700",
              it.tone === "amber" && "border-amber-300 text-amber-700",
              it.tone === "slate" && "text-slate-600",
            )}
          >
            {it.label}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

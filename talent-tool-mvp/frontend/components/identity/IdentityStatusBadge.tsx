"use client";

/**
 * v11.2 T6303 — Identity verification status badge.
 *
 * Renders 待上传 (pending, amber) / 待审核 (submitted, blue) / 已认证 (verified,
 * green) for either a single doc type or the overall roll-up.
 *
 * Used by:
 *   - DocumentUploader (per-doc badge next to each upload slot)
 *   - the identity page (overall badge)
 *   - profile/_client.tsx (overall badge in the 身份与版本 card)
 */

import { cn } from "@/lib/utils";
import {
  identityBadgeTone,
  identityStatusLabel,
  type IdentityBadgeTone,
} from "@/lib/api-identity";

export interface IdentityStatusBadgeProps {
  /** Raw backend status: 'pending' | 'submitted' | 'verified' (or null). */
  status?: string | null;
  /**
   * Optional pre-resolved Chinese label. Falls back to IDENTITY_DISPLAY_MAP.
   * Pass this when the backend already returned ``*_display`` fields.
   */
  label?: string;
  /** Size variant. */
  size?: "sm" | "md";
  /** Extra classes. */
  className?: string;
}

const TONE_CLASSES: Record<IdentityBadgeTone, string> = {
  amber:
    "bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-800",
  blue: "bg-blue-50 text-blue-700 ring-1 ring-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-800",
  green:
    "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-800",
};

const DOT_CLASSES: Record<IdentityBadgeTone, string> = {
  amber: "bg-amber-500",
  blue: "bg-blue-500",
  green: "bg-emerald-500",
};

export function IdentityStatusBadge({
  status,
  label,
  size = "sm",
  className,
}: IdentityStatusBadgeProps) {
  const tone = identityBadgeTone(status);
  const text = label ?? identityStatusLabel(status);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        TONE_CLASSES[tone],
        className,
      )}
      // The role+label make the tone (color) accessible to screen readers.
      role="status"
      aria-label={`身份状态：${text}`}
    >
      <span
        className={cn("inline-block rounded-full", DOT_CLASSES[tone])}
        style={{ height: 6, width: 6 }}
        aria-hidden
      />
      {text}
    </span>
  );
}

export default IdentityStatusBadge;

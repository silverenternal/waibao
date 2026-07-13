"use client";

/**
 * v8.0 T3501 — ServiceBadge.
 *
 * Renders a single service as either:
 *   - a colored badge (status dot + plan + role icons + deps count)
 *   - nothing (when children should be hidden because the service is
 *     disabled for the current org/plan/role)
 *
 * Usage:
 *   <ServiceBadge name="api.ai_interview">
 *     <Link href="/employer/ai-interview">AI Interview</Link>
 *   </ServiceBadge>
 */

import * as React from "react";
import { useServiceToggle } from "@/hooks/use-service-toggle";
import { cn } from "@/lib/utils";

export interface ServiceBadgeProps {
  name: string;
  displayName?: string;
  plan?: string;
  role?: string;
  orgId?: string;
  /** When true, always render children — show the badge alongside them. */
  showAlways?: boolean;
  className?: string;
  children?: React.ReactNode;
}

const STATUS_COLORS: Record<string, string> = {
  enabled: "bg-green-500",
  disabled: "bg-red-500",
  maintenance: "bg-amber-500",
  beta: "bg-blue-500",
};

const PLAN_LABELS: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  enterprise: "Enterprise",
  internal: "Internal",
};

const PLAN_COLORS: Record<string, string> = {
  free: "bg-slate-100 text-slate-700",
  pro: "bg-indigo-100 text-indigo-700",
  enterprise: "bg-purple-100 text-purple-700",
  internal: "bg-amber-100 text-amber-800",
};

export function ServiceBadge({
  name,
  displayName,
  plan = "free",
  role = "",
  orgId,
  showAlways = true,
  className,
  children,
}: ServiceBadgeProps): React.ReactElement | null {
  const enabled = useServiceToggle(name, { plan, role, orgId });

  if (!enabled && !showAlways) {
    return null;
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-md border border-slate-200 px-2 py-1 text-xs",
        className,
      )}
      data-service={name}
      data-enabled={enabled ? "true" : "false"}
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          enabled ? STATUS_COLORS.enabled : STATUS_COLORS.disabled,
        )}
        aria-hidden
      />
      <span className="font-medium text-slate-700">
        {displayName ?? name}
      </span>
      <span
        className={cn(
          "rounded px-1 text-[10px] font-semibold uppercase",
          PLAN_COLORS[plan] ?? PLAN_COLORS.free,
        )}
      >
        {PLAN_LABELS[plan] ?? plan}
      </span>
      {role ? (
        <span className="rounded bg-slate-100 px-1 text-[10px] text-slate-600">
          {role}
        </span>
      ) : null}
      {children}
    </span>
  );
}

export default ServiceBadge;

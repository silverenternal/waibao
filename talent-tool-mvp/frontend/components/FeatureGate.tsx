"use client";

/**
 * v8.0 T3503 — FeatureGate.
 *
 * Unified wrapper that hides / upgrades children based on the 3-layer
 * feature-access stack (Service Toggle + Feature Flag + Config Center).
 *
 *   <FeatureGate name="api.ai_interview" plan="pro" role="employer">
 *     <AILiveButton />
 *   </FeatureGate>
 *
 * Behaviour:
 *   * When the service is enabled  -> render children
 *   * When disabled and `fallback` provided -> render fallback
 *   * Otherwise                    -> render a compact "upgrade plan" hint
 *
 * The hook `useFeatureGate` is exported for callers that prefer the
 * imperative API.
 */

import * as React from "react";
import Link from "next/link";
import { useServiceToggle } from "@/hooks/use-service-toggle";
import { cn } from "@/lib/utils";

export type GateState = "loading" | "enabled" | "disabled" | "missing";

export interface FeatureGateProps {
  /** Service name registered in `service_registry`. */
  name: string;
  /** Customer plan; falls back to "free". */
  plan?: string;
  /** Active role; optional. */
  role?: string;
  /** Active org_id; optional. */
  orgId?: string;
  /** Optional fallback content for the disabled state. */
  fallback?: React.ReactNode;
  /** When true, always render children (no hiding) — wraps a hint badge. */
  showHint?: boolean;
  /** Class name applied to the wrapper element. */
  className?: string;
  children: React.ReactNode;
}

const HINT_LABELS: Record<string, string> = {
  free: "Free 计划已包含",
  pro: "Pro 计划",
  enterprise: "Enterprise 计划",
};

export function FeatureGate({
  name,
  plan = "free",
  role = "",
  orgId,
  fallback,
  showHint = false,
  className,
  children,
}: FeatureGateProps): React.ReactElement | null {
  const state = useFeatureGate(name, { plan, role, orgId });

  if (state === "enabled") {
    if (showHint) {
      return (
        <span
          data-feature-gate={name}
          data-enabled="true"
          className={cn("inline-flex items-center gap-2", className)}
        >
          {children}
          <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-semibold text-green-700">
            enabled
          </span>
        </span>
      );
    }
    return <>{children}</>;
  }

  if (state === "loading") {
    return (
      <span
        aria-busy
        data-feature-gate={name}
        className={cn("inline-flex items-center gap-2 text-slate-400", className)}
      >
        {children}
        <span className="text-xs">…</span>
      </span>
    );
  }

  if (fallback !== undefined) {
    return <>{fallback}</>;
  }

  // Default disabled UI
  return (
    <span
      data-feature-gate={name}
      data-enabled="false"
      className={cn(
        "inline-flex flex-col items-start gap-1 rounded-md border border-dashed border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900",
        className,
      )}
    >
      <span className="font-semibold">服务未启用：{name}</span>
      <span>
        当前 plan = <strong>{plan}</strong> · 建议升级到{" "}
        <strong>{HINT_LABELS[plan] ?? plan}</strong>
      </span>
      <Link href="/pricing" className="text-blue-600 underline">
        查看套餐 →
      </Link>
    </span>
  );
}

export interface UseFeatureGateOptions {
  plan?: string;
  role?: string;
  orgId?: string;
}

/**
 * Imperative hook. Returns one of:
 *   - "loading" while the decision is being fetched
 *   - "enabled" when the 3-layer stack says yes
 *   - "disabled" when any layer says no
 *   - "missing" when the service is not in the catalog
 */
export function useFeatureGate(
  name: string,
  options: UseFeatureGateOptions = {}
): GateState {
  const { plan = "free", role = "", orgId } = options;
  const enabled = useServiceToggle(name, { plan, role, orgId });
  // useServiceToggle does not expose "missing" distinctly — treat null as missing.
  if (enabled === null) return "missing";
  if (enabled === undefined) return "loading";
  return enabled ? "enabled" : "disabled";
}

export default FeatureGate;
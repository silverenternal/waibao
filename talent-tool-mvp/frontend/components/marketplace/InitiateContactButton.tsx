"use client";

/**
 * v11.2 (T6304) — InitiateContactButton.
 *
 * Threshold-aware "发起沟通" control for marketplace cards.
 *
 * 甲方 rule: 只有匹配度 ≥ 70% 双方才可见且可发起沟通. Backend enforces the
 * threshold; the employer talent list is already server-side filtered to
 * ≥ threshold. This component mirrors that server state on the client:
 *
 *   - Anonymous / below-threshold (can_contact === false):
 *       → locked overlay "登录后查看匹配度并发起沟通" (name masked upstream).
 *   - Channel already open (comm_channel_open === true):
 *       → "沟通中" (disabled, non-interactive).
 *   - Eligible (can_contact === true && !comm_channel_open):
 *       → "发起沟通" → POST initiate-contact → "已发起，对方可见" (disabled).
 *
 * Reusable on both sides: pass `initiator="employer"` (needs talentId +
 * roleId) or `initiator="candidate"` (roleId only, candidate inferred from
 * session). roleId normally comes from the card's `best_role_id`.
 *
 * Accessibility: 44px min touch target, aria-live status region, loading
 * state announced, error recoverable.
 */
import * as React from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { initiateContact } from "@/lib/api-talent-market";

type State = "locked" | "open" | "idle" | "submitting" | "done" | "error";

export interface InitiateContactButtonProps {
  /** Who is initiating. */
  initiator: "employer" | "candidate";
  /** Employer side: the talent (candidate) id to contact. */
  talentId?: string;
  /** Best-matching role id (from card.best_role_id). Required. */
  roleId?: string | null;
  /** Viewer may contact (≥ threshold + authenticated). */
  canContact?: boolean;
  /** A channel is already open between the two parties. */
  commChannelOpen?: boolean;
  /** Login href for the locked CTA. */
  loginHref?: string;
  className?: string;
  /** Optional callback after a channel is successfully opened. */
  onOpened?: () => void;
}

export function InitiateContactButton({
  initiator,
  talentId,
  roleId,
  canContact,
  commChannelOpen,
  loginHref = "/login",
  className,
  onOpened,
}: InitiateContactButtonProps) {
  const initial: State = commChannelOpen
    ? "open"
    : canContact
      ? "idle"
      : "locked";
  const [state, setState] = React.useState<State>(initial);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  // Re-sync if upstream card state changes (e.g. after a refetch).
  React.useEffect(() => {
    setState(commChannelOpen ? "open" : canContact ? "idle" : "locked");
  }, [commChannelOpen, canContact]);

  async function handleInitiate() {
    if (!roleId) {
      setErrorMsg("缺少匹配岗位，无法发起沟通。");
      setState("error");
      return;
    }
    setState("submitting");
    setErrorMsg(null);
    try {
      await initiateContact(
        initiator === "employer"
          ? { talentId, roleId }
          : { roleId },
      );
      setState("done");
      onOpened?.();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "发起失败，请稍后重试。");
      setState("error");
    }
  }

  const touchTarget = "min-h-[44px] w-full sm:w-auto";

  if (state === "locked") {
    return (
      <div className={cn("flex flex-col gap-1.5", className)}>
        <div className="flex min-h-[44px] items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 text-center text-xs text-slate-500">
          <span aria-live="polite">🔒 登录后查看匹配度并发起沟通</span>
        </div>
        <Button asChild variant="outline" size="sm" className={touchTarget}>
          <Link href={loginHref}>企业登录</Link>
        </Button>
      </div>
    );
  }

  if (state === "open") {
    return (
      <div
        className={cn(
          "flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg bg-emerald-50 px-3 text-sm font-medium text-emerald-700",
          className,
        )}
        aria-live="polite"
      >
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
        沟通中
      </div>
    );
  }

  if (state === "done") {
    return (
      <div
        className={cn(
          "flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg bg-sky-50 px-3 text-sm font-medium text-sky-700",
          className,
        )}
        aria-live="polite"
      >
        ✓ 已发起，对方可见
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Button
        type="button"
        onClick={handleInitiate}
        disabled={state === "submitting"}
        className={touchTarget}
        aria-busy={state === "submitting"}
      >
        {state === "submitting" ? "发起中…" : "发起沟通"}
      </Button>
      {state === "error" && (
        <p
          role="alert"
          aria-live="assertive"
          className="text-xs text-rose-600"
        >
          {errorMsg}
        </p>
      )}
    </div>
  );
}

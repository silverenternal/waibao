"use client";

/**
 * v6.0 T2103 — RealtimeVoiceWrapper.
 *
 * Gates the real-time voice UI behind the `realtime_voice` feature flag.
 * When the flag is off, the children render as an <UpgradeHint/> instead of
 * the actual voice client (so users get a polite "coming soon" CTA instead
 * of a 404 / blank screen).
 *
 * Usage:
 *   <RealtimeVoiceWrapper userId={me.id} orgId={me.orgId}>
 *     <RealtimeVoiceClient roomId={roomId} />
 *   </RealtimeVoiceWrapper>
 */

import * as React from "react";
import { useFeatureFlag } from "@/hooks/use-feature-flag";

export interface RealtimeVoiceWrapperProps {
  userId?: string;
  orgId?: string;
  fallbackTitle?: string;
  fallbackBody?: string;
  children: React.ReactNode;
}

export function RealtimeVoiceWrapper(props: RealtimeVoiceWrapperProps): React.JSX.Element {
  const {
    userId,
    orgId,
    fallbackTitle = "Realtime voice is rolling out gradually",
    fallbackBody = "Your account isn't in the current rollout cohort yet. We'll notify you when it's available — or contact your admin to request access.",
    children,
  } = props;

  const enabled = useFeatureFlag("realtime_voice", { userId, orgId });

  if (enabled) {
    return <>{children}</>;
  }

  return (
    <div
      role="status"
      data-testid="realtime-voice-disabled"
      className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center"
    >
      <span className="mb-2 inline-flex h-10 w-10 items-center justify-center rounded-full bg-slate-200 text-slate-500">
        {/* speaker icon — keeps the placeholder visual */}
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M11 5 6 9H2v6h4l5 4z" />
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
        </svg>
      </span>
      <h3 className="text-base font-semibold text-slate-700">{fallbackTitle}</h3>
      <p className="mt-1 max-w-md text-sm text-slate-500">{fallbackBody}</p>
    </div>
  );
}
"use client";

/**
 * LiveKitVideoStage — T2204.
 *
 * 改造 AI 面试 UI 用 LiveKit 替代 mock 视频.
 *
 * 用法:
 *   <LiveKitVideoStage
 *     interviewId={id}
 *     livekit={startResp.livekit}
 *     onLeave={() => router.back()}
 *   />
 */

import { useEffect, useState } from "react";
import LiveKitRoom from "@/components/livekit/Room";

interface LiveKitConfig {
  room_name: string;
  livekit_url?: string;
  host_token?: string;
  host_url?: string;
  join_url?: string;
  token_expires_at?: string;
}

interface Props {
  interviewId: string;
  livekit?: LiveKitConfig | null;
  onLeave?: () => void;
  className?: string;
}

interface StartResp {
  livekit?: LiveKitConfig | null;
}

export default function LiveKitVideoStage({
  interviewId,
  livekit,
  onLeave,
  className = "",
}: Props) {
  const [resolved, setResolved] = useState<LiveKitConfig | null>(livekit ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (resolved) return;
    if (!interviewId) return;
    const token = localStorage.getItem("sb_token") || "";
    let alive = true;
    fetch(`/api/ai-interview-v2/${interviewId}/livekit`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        const data = (await r.json()) as StartResp;
        if (alive) setResolved(data.livekit || null);
      })
      .catch((e) => {
        if (alive) setError(typeof e === "string" ? e : "获取 LiveKit 信息失败");
      });
    return () => {
      alive = false;
    };
  }, [interviewId, resolved]);

  if (error) {
    return (
      <div className={`rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 ${className}`}>
        {error}
      </div>
    );
  }

  if (!resolved) {
    return (
      <div className={`rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500 ${className}`}>
        准备视频面试…
      </div>
    );
  }

  return (
    <LiveKitRoom
      roomName={resolved.room_name}
      identity={localStorage.getItem("sb_user_email") || `user_${interviewId}`}
      authToken={localStorage.getItem("sb_token") || undefined}
      onLeave={onLeave}
    />
  );
}
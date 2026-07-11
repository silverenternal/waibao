"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { MessageSquarePlus } from "lucide-react";

export interface EvalDiscussProps {
  matchId: string;
  existingRoomId?: string | null;
  onDiscussed?: (roomId: string) => void;
}

/**
 * 发起讨论按钮 — 创建协同房间.
 */
export function EvalDiscuss({
  matchId,
  existingRoomId,
  onDiscussed,
}: EvalDiscussProps) {
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const handleClick = async () => {
    setLoading(true);
    setErr(null);
    try {
      const { matchEvalApi } = await import("@/lib/api-match-eval");
      const r = await matchEvalApi.startDiscussion(matchId, {
        topic: "互评讨论:候选人 vs 雇主视角差异",
      });
      onDiscussed?.(r.room_id);
    } catch (e: any) {
      setErr(e?.message ?? "发起讨论失败");
    } finally {
      setLoading(false);
    }
  };

  if (existingRoomId) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-500">
          讨论房间已创建: <span className="font-mono">{existingRoomId.slice(0, 8)}…</span>
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            window.location.href = `/rooms/${existingRoomId}`;
          }}
        >
          进入房间
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Button onClick={handleClick} disabled={loading}>
        <MessageSquarePlus className="mr-1.5" size={16} aria-hidden />
        {loading ? "创建中…" : "发起讨论"}
      </Button>
      {err && <span className="text-xs text-red-600">{err}</span>}
    </div>
  );
}
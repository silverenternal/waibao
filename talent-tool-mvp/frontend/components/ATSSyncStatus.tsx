"use client";
/**
 * T1501 - 同步状态指标
 */
import { Badge } from "@/components/ui/badge";

interface Props {
  status: string;
  lastSyncedAt: string | null;
  lastError: string | null;
}

export default function ATSSyncStatus({ status, lastSyncedAt, lastError }: Props) {
  const variant =
    status === "ok"
      ? "default"
      : status === "partial"
      ? "secondary"
      : status === "failed" || status === "error"
      ? "destructive"
      : "outline";

  const ageMin = lastSyncedAt
    ? Math.max(0, Math.round((Date.now() - new Date(lastSyncedAt).getTime()) / 60000))
    : null;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Badge variant={variant}>{status}</Badge>
        {ageMin !== null && (
          <span className="text-xs text-muted-foreground">{ageMin} 分钟前</span>
        )}
      </div>
      {lastError && (
        <pre className="text-xs bg-red-50 text-red-700 p-2 rounded">{lastError}</pre>
      )}
    </div>
  );
}

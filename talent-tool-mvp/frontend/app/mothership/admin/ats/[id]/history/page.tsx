"use client";
/**
 * T1501 - ATS 同步历史
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface SyncLog {
  id: string;
  sync_type: string;
  direction: string;
  triggered_by: string;
  status: string;
  total: number;
  succeeded: number;
  failed: number;
  conflicts: number;
  diff: any[];
  error: string | null;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
}

export default function ATSSyncHistoryPage({ params }: { params: { id: string } }) {
  const [logs, setLogs] = useState<SyncLog[]>([]);

  useEffect(() => {
    fetch(`/api/ats/integrations/${params.id}/sync-history?limit=50`)
      .then((r) => r.json())
      .then(setLogs)
      .catch((err) => console.error(err));
  }, [params.id]);

  return (
    <div className="space-y-4 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">同步历史</h1>
        <Link href={`/mothership/admin/ats/${params.id}`}>
          <button className="text-sm text-blue-600 underline">← 返回</button>
        </Link>
      </header>

      {logs.length === 0 ? (
        <p className="text-sm text-muted-foreground">暂无同步日志</p>
      ) : (
        logs.map((log) => (
          <Card key={log.id}>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant={log.status === "ok" ? "default" : "destructive"}>{log.status}</Badge>
                <Badge variant="outline">{log.sync_type}</Badge>
                <Badge variant="outline">{log.direction}</Badge>
                <span className="text-xs text-muted-foreground">{log.triggered_by}</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {new Date(log.started_at).toLocaleString()}
                </span>
              </div>
              <div className="grid grid-cols-5 gap-2 text-xs">
                <div>total: {log.total}</div>
                <div>succeeded: {log.succeeded}</div>
                <div>failed: {log.failed}</div>
                <div>conflicts: {log.conflicts}</div>
                <div>duration: {log.duration_ms || 0}ms</div>
              </div>
              {log.error && (
                <pre className="text-xs bg-red-50 text-red-800 p-2 rounded">{log.error}</pre>
              )}
              {log.diff && log.diff.length > 0 && (
                <details>
                  <summary className="text-xs cursor-pointer">Diff ({log.diff.length})</summary>
                  <pre className="text-xs bg-muted p-2 rounded overflow-auto">
                    {JSON.stringify(log.diff.slice(0, 20), null, 2)}
                  </pre>
                </details>
              )}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

"use client";
/**
 * T1501 - 冲突解决器:列表展示差异并提供三种决议:
 *   1. local_wins  (本地覆盖)
 *   2. remote_wins (远端覆盖)
 *   3. auto_merged (已合并)
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

interface Conflict {
  id: string;
  entity_type: string;
  external_id: string;
  field_diffs: { field: string; local: any; remote: any }[];
  resolution: string | null;
  created_at: string;
}

interface Props {
  integrationId: string;
  conflicts: Conflict[];
  onResolved?: () => void;
}

export default function ATSConflictResolver({ integrationId, conflicts, onResolved }: Props) {
  const [busy, setBusy] = useState<string | null>(null);

  async function resolve(conflictId: string, resolution: string) {
    setBusy(conflictId);
    try {
      const res = await fetch(
        `/api/ats/integrations/${integrationId}/conflicts/${conflictId}/resolve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ resolution }),
        }
      );
      if (res.ok) onResolved?.();
    } finally {
      setBusy(null);
    }
  }

  if (conflicts.length === 0) {
    return <p className="text-sm text-muted-foreground">无未解决冲突</p>;
  }

  return (
    <div className="space-y-3">
      {conflicts.map((c) => (
        <Card key={c.id} className="p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-medium">
              {c.entity_type}: {c.external_id}
            </div>
            <span className="text-xs text-muted-foreground">{new Date(c.created_at).toLocaleString()}</span>
          </div>
          <table className="w-full text-xs mb-2">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1">字段</th>
                <th className="py-1">本地</th>
                <th className="py-1">远端</th>
              </tr>
            </thead>
            <tbody>
              {c.field_diffs.map((d, i) => (
                <tr key={i} className="border-t">
                  <td className="py-1 font-mono">{d.field}</td>
                  <td className="py-1">{String(d.local ?? "(空)")}</td>
                  <td className="py-1">{String(d.remote ?? "(空)")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={busy === c.id}
              onClick={() => resolve(c.id, "local_wins")}
            >
              用本地
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy === c.id}
              onClick={() => resolve(c.id, "remote_wins")}
            >
              用远端
            </Button>
            <Button
              size="sm"
              variant="default"
              disabled={busy === c.id}
              onClick={() => resolve(c.id, "auto_merged")}
            >
              标记合并
            </Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

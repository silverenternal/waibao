"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { useEffect, useState } from "react";
import { AuditFilterBar, AuditFilterValue } from "@/components/audit/AuditFilterBar";
import { AuditLogTable } from "@/components/audit/AuditLogTable";
import { AuditEntry, exportAuditUrl, listAudit } from "@/lib/api-audit";
import { Card, CardContent } from "@/components/ui/card";
import { ShieldCheck } from "lucide-react";

const DEFAULT_FILTER: AuditFilterValue = {
  user_id: "",
  actor_user_id: "",
  resource_type: "",
  action: "",
  since_days: 7,
};

export default function AuditAdminPage() {
  const [filter, setFilter] = useState<AuditFilterValue>(DEFAULT_FILTER);
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (f: AuditFilterValue) => {
    setLoading(true);
    setError(null);
    try {
      const res = await listAudit({
        user_id: f.user_id || undefined,
        actor_user_id: f.actor_user_id || undefined,
        resource_type: f.resource_type || undefined,
        action: f.action || undefined,
        since_days: f.since_days,
        limit: 200,
        offset: 0,
      });
      setEntries(res.data || []);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load audit log";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(DEFAULT_FILTER);
  }, []);

  const handleExport = () => {
    if (typeof window === "undefined") return;
    const url = exportAuditUrl({
      user_id: filter.user_id || undefined,
      since_days: filter.since_days,
    });
    window.open(url, "_blank");
  };

  return (
    <ErrorBoundary>(<div className="space-y-6 p-6">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-semibold">Audit Log</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Admin-only view of all PII access and GDPR operations. Entries are
          append-only and cannot be modified.
        </p>
        <AuditFilterBar
          value={filter}
          onChange={setFilter}
          onApply={() => load(filter)}
          onExport={handleExport}
        />
        <Card>
          <CardContent className="p-0">
            {error ? (
              <div className="p-8 text-sm text-destructive">{error}</div>
            ) : (
              <AuditLogTable entries={entries} loading={loading} />
            )}
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}
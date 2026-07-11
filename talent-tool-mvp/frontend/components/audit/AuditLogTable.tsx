"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { AuditEntry } from "@/lib/api-audit";

export interface AuditLogTableProps {
  entries: AuditEntry[];
  loading?: boolean;
  emptyHint?: string;
}

export function AuditLogTable({ entries, loading, emptyHint }: AuditLogTableProps) {
  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }
  if (!entries.length) {
    return (
      <div className="p-8 text-center text-muted-foreground text-sm">
        {emptyHint ?? "No audit entries."}
      </div>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>When</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Resource</TableHead>
          <TableHead>Actor</TableHead>
          <TableHead>Subject</TableHead>
          <TableHead>IP</TableHead>
          <TableHead>Metadata</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((e) => (
          <TableRow key={e.id}>
            <TableCell className="whitespace-nowrap text-xs">
              {new Date(e.created_at).toLocaleString()}
            </TableCell>
            <TableCell className="font-mono text-xs">{e.action}</TableCell>
            <TableCell>
              <div className="text-xs">{e.resource_type}</div>
              <div className="text-[10px] text-muted-foreground">{e.resource_id ?? "—"}</div>
            </TableCell>
            <TableCell className="text-xs font-mono">
              {e.actor_user_id?.slice(0, 8) ?? "—"}
            </TableCell>
            <TableCell className="text-xs font-mono">
              {e.user_id?.slice(0, 8) ?? "—"}
            </TableCell>
            <TableCell className="text-xs">{e.ip_address ?? "—"}</TableCell>
            <TableCell className="text-xs max-w-[280px] truncate">
              <code>{JSON.stringify(e.metadata)}</code>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
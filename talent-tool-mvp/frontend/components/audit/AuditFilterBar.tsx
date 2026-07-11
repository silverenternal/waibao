"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Download } from "lucide-react";

export interface AuditFilterValue {
  user_id: string;
  actor_user_id: string;
  resource_type: string;
  action: string;
  since_days: number;
}

export interface AuditFilterBarProps {
  value: AuditFilterValue;
  onChange: (next: AuditFilterValue) => void;
  onApply: () => void;
  onExport: () => void;
}

export function AuditFilterBar({ value, onChange, onApply, onExport }: AuditFilterBarProps) {
  return (
    <div className="flex flex-wrap items-end gap-3 p-4 bg-card rounded-lg border">
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">PII subject user_id</label>
        <Input
          placeholder="uuid"
          value={value.user_id}
          onChange={(e) => onChange({ ...value, user_id: e.target.value })}
          className="w-56"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Actor user_id</label>
        <Input
          placeholder="uuid"
          value={value.actor_user_id}
          onChange={(e) => onChange({ ...value, actor_user_id: e.target.value })}
          className="w-56"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Resource type</label>
        <Input
          placeholder="candidate / role / journal ..."
          value={value.resource_type}
          onChange={(e) => onChange({ ...value, resource_type: e.target.value })}
          className="w-56"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Action</label>
        <Input
          placeholder="read / update / forget ..."
          value={value.action}
          onChange={(e) => onChange({ ...value, action: e.target.value })}
          className="w-56"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs text-muted-foreground">Since (days)</label>
        <Input
          type="number"
          min={1}
          max={365}
          value={value.since_days}
          onChange={(e) => onChange({ ...value, since_days: Number(e.target.value) || 7 })}
          className="w-24"
        />
      </div>
      <div className="flex gap-2 ml-auto">
        <Button onClick={onApply} variant="default">
          <Search className="h-4 w-4 mr-1" /> Apply
        </Button>
        <Button onClick={onExport} variant="outline">
          <Download className="h-4 w-4 mr-1" /> Export CSV
        </Button>
      </div>
    </div>
  );
}
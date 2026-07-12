"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface FunnelFilterValue {
  days: number;
  source: string;
  department: string;
}

interface FunnelFilterProps {
  value: FunnelFilterValue;
  onChange: (next: FunnelFilterValue) => void;
  sources?: string[];
  departments?: string[];
  className?: string;
}

const DAY_OPTIONS = [
  { value: 7, label: "Last 7 days" },
  { value: 30, label: "Last 30 days" },
  { value: 90, label: "Last 90 days" },
  { value: 180, label: "Last 6 months" },
  { value: 365, label: "Last 12 months" },
];

export function FunnelFilter({
  value,
  onChange,
  sources = [],
  departments = [],
  className,
}: FunnelFilterProps) {
  const set = (patch: Partial<FunnelFilterValue>) =>
    onChange({ ...value, ...patch });

  return (
    <div className={`flex flex-wrap items-end gap-3 ${className ?? ""}`}>
      <div className="space-y-1">
        <Label htmlFor="funnel-days" className="text-xs">
          Period
        </Label>
        <Select
          value={String(value.days)}
          onValueChange={(v) => set({ days: Number(v) })}
        >
          <SelectTrigger id="funnel-days" className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DAY_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={String(o.value)}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="funnel-source" className="text-xs">
          Channel
        </Label>
        <Select
          value={value.source || "all"}
          onValueChange={(v: unknown) => {
            const s = (v as string | null) ?? "all";
            set({ source: s === "all" ? "" : s });
          }}
        >
          <SelectTrigger id="funnel-source" className="w-[160px]">
            <SelectValue placeholder="All channels">
              {value.source ? value.source : "All channels"}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All channels</SelectItem>
            {sources.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="funnel-dept" className="text-xs">
          Department
        </Label>
        <Input
          id="funnel-dept"
          placeholder="All departments"
          value={value.department}
          onChange={(e) => set({ department: e.target.value })}
          className="w-[180px]"
        />
      </div>

      <Button
        variant="ghost"
        size="sm"
        onClick={() =>
          onChange({ days: 30, source: "", department: "" })
        }
      >
        Reset
      </Button>
    </div>
  );
}
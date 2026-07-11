"use client";

/**
 * CategoryFilter (T601)
 *
 * Pill-style multi/single select used by `PolicyList`. Emits the chosen
 * category (or empty string for "全部") through `onChange`.
 *
 * Defaults to single-select (clearable) so the request to
 * GET /api/policy/list stays simple — backend only takes one `category`.
 */

import * as React from "react";
import { Filter, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  POLICY_CATEGORIES,
  POLICY_CATEGORY_LABEL,
  type PolicyCategory,
} from "@/lib/api-policy";

export interface CategoryFilterProps {
  value: PolicyCategory | "" | null;
  onChange: (value: PolicyCategory | "" | null) => void;
  className?: string;
  /** Hide the "全部" entry (default true — always shown). */
  showAll?: boolean;
}

export function CategoryFilter({
  value,
  onChange,
  className,
  showAll = true,
}: CategoryFilterProps) {
  return (
    <div
      role="radiogroup"
      aria-label="按类别筛选"
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white p-2",
        className,
      )}
    >
      <span className="inline-flex items-center gap-1 px-2 text-xs text-slate-500">
        <Filter className="size-3.5" />
        类别
      </span>
      {showAll && (
        <Pill
          active={!value}
          onClick={() => onChange("")}
          label="全部"
        />
      )}
      {POLICY_CATEGORIES.map((c) => (
        <Pill
          key={c}
          active={value === c}
          onClick={() => onChange(value === c ? "" : c)}
          label={POLICY_CATEGORY_LABEL[c]}
        />
      ))}
      {value && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange("")}
          className="ml-1 h-7 gap-1 px-2 text-xs"
        >
          <X className="size-3" />
          清空
        </Button>
      )}
    </div>
  );
}

function Pill({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-xs transition",
        active
          ? "border-blue-500 bg-blue-500 text-white shadow-sm"
          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50",
      )}
    >
      {label}
    </button>
  );
}

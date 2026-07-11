"use client";

import * as React from "react";
import { ThumbsUp } from "lucide-react";

export interface StrengthsListProps {
  items: string[];
  loading?: boolean;
}

/**
 * 双方一致认可的优势列表.
 */
export function StrengthsList({ items, loading }: StrengthsListProps) {
  if (loading) return <div className="text-sm text-slate-400">加载中…</div>;
  if (!items || items.length === 0) {
    return (
      <div className="text-sm text-slate-500 italic">
        暂无双方一致认可的优势
      </div>
    );
  }
  const labelMap: Record<string, string> = {
    skill: "技能",
    communication: "沟通",
    culture: "文化契合",
    potential: "潜力",
  };
  return (
    <ul className="space-y-2">
      {items.map((s, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
          <ThumbsUp
            className="mt-0.5 shrink-0 text-emerald-600"
            size={16}
            aria-hidden
          />
          <span>{labelMap[s] ?? s}</span>
        </li>
      ))}
    </ul>
  );
}
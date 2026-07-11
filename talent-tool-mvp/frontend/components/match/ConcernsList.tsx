"use client";

import * as React from "react";
import { ThumbsDown } from "lucide-react";

export interface ConcernsListProps {
  items: string[];
  loading?: boolean;
}

/**
 * 双方一致关注的顾虑列表.
 */
export function ConcernsList({ items, loading }: ConcernsListProps) {
  if (loading) return <div className="text-sm text-slate-400">加载中…</div>;
  if (!items || items.length === 0) {
    return (
      <div className="text-sm text-slate-500 italic">
        暂无双方一致关注的顾虑
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
      {items.map((c, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
          <ThumbsDown
            className="mt-0.5 shrink-0 text-rose-600"
            size={16}
            aria-hidden
          />
          <span>{labelMap[c] ?? c}</span>
        </li>
      ))}
    </ul>
  );
}
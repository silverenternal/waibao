"use client";

import * as React from "react";
import { User, Briefcase, Ticket, BookOpen, ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";
import type { SearchResult } from "@/hooks/use-global-search";

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  user: User,
  briefcase: Briefcase,
  ticket: Ticket,
  book: BookOpen,
};

export interface SearchResultItemProps {
  result: SearchResult;
  active?: boolean;
  onSelect?: (result: SearchResult) => void;
}

export function SearchResultItem({
  result,
  active = false,
  onSelect,
}: SearchResultItemProps) {
  const Icon = ICON_MAP[result.icon || ""] ?? Briefcase;
  return (
    <a
      href={result.url}
      onClick={(e) => {
        if (onSelect) {
          e.preventDefault();
          onSelect(result);
        }
      }}
      className={cn(
        "flex items-start gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
        active ? "bg-accent text-accent-foreground" : "hover:bg-muted",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
      role="option"
      aria-selected={active}
      data-search-result-type={result.type}
      data-search-result-id={result.id}
    >
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{result.title}</span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {result.type}
          </span>
        </div>
        {result.snippet && (
          <p className="line-clamp-2 text-xs text-muted-foreground">
            {result.snippet}
          </p>
        )}
      </div>
      <ArrowRight className="mt-1 size-3.5 shrink-0 text-muted-foreground" />
    </a>
  );
}

export default SearchResultItem;

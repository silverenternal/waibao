"use client";

/**
 * PolicySearch (T601)
 *
 * Debounced full-text search box. Drives either:
 *   - local filter  (set `mode="local"`, default)  — calls `onResults`
 *     with a precomputed subset of the supplied `corpus`.
 *   - semantic query (set `mode="remote"`)         — calls the backend
 *     `/api/policy/query` endpoint and surfaces the LLM answer
 *     alongside matched chunks.
 *
 * Both modes share the same UI so the page can swap without rewiring.
 */

import * as React from "react";
import {
  Search,
  Sparkles,
  Loader2,
  FileText,
  ChevronRight,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

import {
  policyApi,
  highlightTerms,
  POLICY_CATEGORY_LABEL,
  type PolicyDoc,
  type PolicyQueryResponse,
  type PolicySearchResult,
} from "@/lib/api-policy";

export type PolicySearchMode = "local" | "remote";

export interface PolicySearchProps {
  /** Used by both modes (local corpus + remote organisation id). */
  corpus?: PolicyDoc[];
  organisationId?: string;
  mode?: PolicySearchMode;
  /** Submit a result row — page routes to detail. */
  onSelect?: (item: { id: string; title: string }) => void;
  className?: string;
  placeholder?: string;
  /** Auto-focus on mount (default false). */
  autoFocus?: boolean;
}

const LOCAL_DEBOUNCE_MS = 150;

export function PolicySearch({
  corpus = [],
  organisationId,
  mode = "local",
  onSelect,
  className,
  placeholder = "搜索制度关键词…",
  autoFocus = false,
}: PolicySearchProps) {
  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [localResults, setLocalResults] = React.useState<PolicySearchResult[]>(
    [],
  );
  const [remoteResult, setRemoteResult] =
    React.useState<PolicyQueryResponse | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  // Debounce query → debounced.
  React.useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), LOCAL_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [query]);

  // Local search effect.
  React.useEffect(() => {
    if (mode !== "local") return;
    if (!debounced) {
      setLocalResults([]);
      setError(null);
      return;
    }
    const terms = debounced
      .split(/\s+/)
      .map((t) => t.trim())
      .filter(Boolean);
    if (terms.length === 0) {
      setLocalResults([]);
      return;
    }
    const lowered = terms.map((t) => t.toLowerCase());
    const matches: PolicySearchResult[] = [];
    for (const doc of corpus) {
      const title = doc.title || "";
      const content = doc.content || "";
      const haystack = `${title}\n${content}`;
      let count = 0;
      for (const term of lowered) {
        let idx = haystack.toLowerCase().indexOf(term);
        while (idx !== -1) {
          count += 1;
          idx = haystack.toLowerCase().indexOf(term, idx + term.length);
        }
      }
      if (count > 0) {
        // Find first match position for snippet.
        const firstIdx = lowered
          .map((t) => haystack.toLowerCase().indexOf(t))
          .filter((n) => n >= 0)
          .sort((a, b) => a - b)[0];
        const start = Math.max(0, (firstIdx ?? 0) - 60);
        const end = Math.min(haystack.length, (firstIdx ?? 0) + 140);
        matches.push({
          id: doc.id,
          title,
          category: doc.category,
          snippet: `${start > 0 ? "…" : ""}${haystack.slice(start, end)}${
            end < haystack.length ? "…" : ""
          }`.replace(/\s+/g, " "),
          matchCount: count,
          effective_from: doc.effective_from ?? null,
          created_at: doc.created_at,
          matchedTerm: debounced,
        });
      }
    }
    matches.sort((a, b) => b.matchCount - a.matchCount);
    setLocalResults(matches.slice(0, 25));
  }, [debounced, corpus, mode]);

  // Remote (semantic) search effect.
  React.useEffect(() => {
    if (mode !== "remote") return;
    if (!debounced || debounced.length < 2) {
      setRemoteResult(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setSearching(true);
    setError(null);
    policyApi
      .query({ question: debounced, organisationId })
      .then((resp) => {
        if (cancelled) return;
        setRemoteResult(resp);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "查询失败");
        setRemoteResult(null);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debounced, mode, organisationId]);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
        <Input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          className="h-10 pl-9 pr-9"
          aria-label="搜索制度"
        />
        {searching && (
          <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-blue-500" />
        )}
      </div>

      {error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {error}
        </div>
      )}

      {mode === "local" ? (
        <LocalResults results={localResults} query={debounced} onSelect={onSelect} />
      ) : (
        <RemoteResults
          result={remoteResult}
          searching={searching}
          onSelect={onSelect}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function LocalResults({
  results,
  query,
  onSelect,
}: {
  results: PolicySearchResult[];
  query: string;
  onSelect?: (item: { id: string; title: string }) => void;
}) {
  if (!query) return null;
  if (results.length === 0) {
    return (
      <p className="rounded-md border border-dashed bg-slate-50 px-3 py-4 text-center text-xs text-slate-500">
        没有匹配的制度
      </p>
    );
  }
  const terms = query.split(/\s+/).filter(Boolean);
  return (
    <ul className="space-y-2">
      {results.map((r) => (
        <li key={r.id}>
          <button
            type="button"
            onClick={() => onSelect?.({ id: r.id, title: r.title })}
            className="group flex w-full items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 text-left transition hover:border-blue-300 hover:bg-blue-50/30"
          >
            <FileText className="mt-0.5 size-4 text-blue-500" />
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <h4 className="truncate text-sm font-medium text-slate-900">
                  {renderHighlighted(r.title, terms)}
                </h4>
                <Badge variant="outline" className="shrink-0 text-[10px]">
                  {POLICY_CATEGORY_LABEL[
                    r.category as keyof typeof POLICY_CATEGORY_LABEL
                  ] ?? r.category}
                </Badge>
              </div>
              <p className="line-clamp-2 text-xs text-slate-600">
                {renderHighlighted(r.snippet, terms)}
              </p>
              <p className="text-[10px] text-slate-400">
                命中 {r.matchCount} 处 ·{" "}
                {new Date(r.created_at).toLocaleDateString("en-GB", {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                })}
              </p>
            </div>
            <ChevronRight className="mt-1 size-4 shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-blue-500" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function RemoteResults({
  result,
  searching,
  onSelect,
}: {
  result: PolicyQueryResponse | null;
  searching: boolean;
  onSelect?: (item: { id: string; title: string }) => void;
}) {
  if (searching && !result) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-8 text-sm text-slate-500">
          <Loader2 className="size-4 animate-spin text-blue-500" />
          智能体查询中…
        </CardContent>
      </Card>
    );
  }
  if (!result) return null;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Sparkles className="size-4 text-violet-500" />
          智能体回答
        </CardTitle>
        <CardDescription>
          基于制度语义的命中 · 共 {result.matched?.length ?? 0} 条相关条款
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-sm text-slate-800">
          {result.answer || "未找到答案"}
        </div>
        <ul className="space-y-1.5">
          {(result.matched ?? []).map((m, i) => (
            <li
              key={i}
              className="rounded-md border border-slate-200 bg-white p-2"
            >
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {POLICY_CATEGORY_LABEL[
                    (m.category ?? "other") as keyof typeof POLICY_CATEGORY_LABEL
                  ] ?? m.category}
                </Badge>
                <span className="truncate text-xs font-medium text-slate-700">
                  {m.title ?? "相关条款"}
                </span>
                {m.relevance != null && (
                  <span className="ml-auto text-[10px] tabular-nums text-slate-400">
                    相关 {(m.relevance * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              {m.text && (
                <p className="mt-1 line-clamp-3 text-xs text-slate-600">{m.text}</p>
              )}
              {m.policy_id && (
                <Button
                  variant="link"
                  size="sm"
                  onClick={() =>
                    onSelect?.({
                      id: m.policy_id!,
                      title: m.title ?? "制度详情",
                    })
                  }
                  className="mt-1 h-auto px-0 text-xs text-blue-600"
                >
                  查看完整制度
                </Button>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function renderHighlighted(text: string, terms: string[]) {
  const parts = highlightTerms(text, terms);
  return parts.map((seg, i) =>
    seg.highlight ? (
      <mark
        key={i}
        className="rounded bg-amber-100 px-0.5 text-amber-900"
      >
        {seg.text}
      </mark>
    ) : (
      <React.Fragment key={i}>{seg.text}</React.Fragment>
    ),
  );
}

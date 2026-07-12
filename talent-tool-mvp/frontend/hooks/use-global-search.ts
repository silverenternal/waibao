"use client";

/**
 * useGlobalSearch — debounced global search hook.
 *
 * Talks to GET /api/search?q=... and exposes typed results plus cache.
 * Designed for use by GlobalSearchPalette via the ⌘K shortcut.
 */
import * as React from "react";

export type SearchEntityType =
  | "candidates"
  | "roles"
  | "tickets"
  | "policies";

export interface SearchResult {
  type: SearchEntityType | string;
  id: string;
  title: string;
  snippet: string;
  url: string;
  score: number;
  icon?: string | null;
}

export interface SearchResponse {
  query: string;
  type: string;
  took_ms: number;
  total: number;
  items: SearchResult[];
}

export interface UseGlobalSearchInput {
  /** Initial type filter, defaults to "all". */
  type?: SearchEntityType | "all";
  /** Debounce delay in ms, defaults to 200. */
  debounceMs?: number;
  /** Per-request limit, defaults to 20. */
  limit?: number;
  /** Disable fetching (e.g. when palette is closed). */
  enabled?: boolean;
}

export interface UseGlobalSearchReturn {
  query: string;
  setQuery: (q: string) => void;
  type: SearchEntityType | "all";
  setType: (t: SearchEntityType | "all") => void;
  results: SearchResult[];
  loading: boolean;
  error: string | null;
  tookMs: number | null;
  total: number;
}

const CACHE_LIMIT = 32;

export function useGlobalSearch(
  input: UseGlobalSearchInput = {}
): UseGlobalSearchReturn {
  const {
    type: initialType = "all",
    debounceMs = 200,
    limit = 20,
    enabled = true,
  } = input;

  const [query, setQuery] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [type, setType] = React.useState<SearchEntityType | "all">(initialType);
  const [results, setResults] = React.useState<SearchResult[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [tookMs, setTookMs] = React.useState<number | null>(null);
  const [total, setTotal] = React.useState(0);

  // Cache: query+type -> SearchResponse
  const cacheRef = React.useRef<Map<string, SearchResponse>>(new Map());

  // Debounce query updates
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), debounceMs);
    return () => clearTimeout(t);
  }, [query, debounceMs]);

  // Fetch when query, type, or enabled changes
  React.useEffect(() => {
    if (!enabled || !debounced) {
      setResults([]);
      setTotal(0);
      setError(null);
      return;
    }

    const key = `${type}:${debounced}`;
    const cached = cacheRef.current.get(key);
    if (cached) {
      setResults(cached.items);
      setTotal(cached.total);
      setTookMs(cached.took_ms);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          q: debounced,
          type: String(type),
          limit: String(limit),
        });
        const res = await fetch(`/api/search?${params.toString()}`, {
          signal: controller.signal,
          headers: { accept: "application/json" },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as SearchResponse;
        if (cancelled) return;

        // Insert into cache (LRU trim)
        const cache = cacheRef.current;
        cache.set(key, data);
        if (cache.size > CACHE_LIMIT) {
          const first = cache.keys().next().value;
          if (first !== undefined) cache.delete(first);
        }

        setResults(data.items);
        setTotal(data.total);
        setTookMs(data.took_ms);
        setLoading(false);
      } catch (e) {
        if (cancelled) return;
        if ((e as Error).name === "AbortError") return;
        setError((e as Error).message);
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [debounced, type, limit, enabled]);

  return {
    query,
    setQuery,
    type,
    setType,
    results,
    loading,
    error,
    tookMs,
    total,
  };
}

export default useGlobalSearch;

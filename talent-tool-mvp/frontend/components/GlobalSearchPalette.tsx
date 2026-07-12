"use client";

/**
 * GlobalSearchPalette — popover modal containing search input + results.
 * Triggered by the GlobalSearchBar (⌘K / Ctrl+K).
 *
 * Features:
 *   - Debounced query (200ms)
 *   - Type filter chips (all / candidates / roles / tickets / policies)
 *   - Result list with keyboard navigation (↑/↓, Enter)
 *   - Esc closes, focus trapped
 */
import * as React from "react";
import { useRouter } from "next/navigation";
import { Search, X, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { SearchResultItem } from "@/components/SearchResultItem";
import {
  useGlobalSearch,
  type SearchEntityType,
  type SearchResult,
} from "@/hooks/use-global-search";
import { useEscapeToClose, useFocusTrap } from "@/hooks/use-keyboard-nav";

const TYPE_LABELS: Array<SearchEntityType | "all"> = [
  "all",
  "candidates",
  "roles",
  "tickets",
  "policies",
];

export interface GlobalSearchPaletteProps {
  open: boolean;
  onClose: () => void;
}

export function GlobalSearchPalette({
  open,
  onClose,
}: GlobalSearchPaletteProps) {
  const router = useRouter();
  const [activeIdx, setActiveIdx] = React.useState(0);

  const {
    query,
    setQuery,
    type,
    setType,
    results,
    loading,
    error,
    tookMs,
    total,
  } = useGlobalSearch({ enabled: open });

  const focusRef = useFocusTrap<HTMLDivElement>({ active: open });
  useEscapeToClose(onClose, { enabled: open });

  React.useEffect(() => {
    if (open) setActiveIdx(0);
  }, [open, results.length]);

  // Reset on close
  React.useEffect(() => {
    if (!open) {
      setActiveIdx(0);
      // Don't clear query — user may reopen to refine.
    }
  }, [open]);

  const go = React.useCallback(
    (r: SearchResult) => {
      onClose();
      router.push(r.url);
    },
    [onClose, router]
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(results.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = results[activeIdx];
      if (target) go(target);
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Search"
      className="fixed inset-0 z-[70] flex items-start justify-center px-4 pt-[10vh] sm:pt-[15vh]"
    >
      <button
        type="button"
        aria-label="Close search"
        onClick={onClose}
        tabIndex={-1}
        className="absolute inset-0 cursor-default bg-black/50"
        style={{ border: 0 }}
      />
      <div
        ref={focusRef}
        onKeyDown={onKeyDown}
        className="relative w-full max-w-xl rounded-xl border bg-popover text-popover-foreground shadow-2xl ring-1 ring-foreground/10 outline-none"
        data-testid="global-search-palette"
      >
        <div className="flex items-center gap-2 border-b px-3 py-2">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索候选人、岗位、工单、政策..."
            aria-label="Search"
            className="border-0 bg-transparent shadow-none focus-visible:ring-0"
            autoFocus
          />
          {loading && (
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close search"
            className="rounded p-1 text-muted-foreground hover:bg-muted"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex gap-1 border-b px-3 py-2">
          {TYPE_LABELS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setType(t)}
              aria-pressed={type === t}
              className={cn(
                "rounded-full px-3 py-1 text-xs capitalize transition-colors",
                type === t
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted"
              )}
            >
              {t === "all" ? "全部" : t}
            </button>
          ))}
        </div>

        <div
          role="listbox"
          aria-label="Search results"
          className="max-h-[60vh] overflow-y-auto p-2"
        >
          {!query && (
            <p className="px-3 py-12 text-center text-sm text-muted-foreground">
              开始输入以搜索 (候选人 / 岗位 / 工单 / 政策)。
            </p>
          )}

          {query && !loading && results.length === 0 && !error && (
            <p className="px-3 py-12 text-center text-sm text-muted-foreground">
              未匹配到 "{query}" 的相关结果
            </p>
          )}

          {error && (
            <p className="px-3 py-12 text-center text-sm text-destructive">
              搜索出错:{error}
            </p>
          )}

          {results.map((r, i) => (
            <SearchResultItem
              key={`${r.type}-${r.id}`}
              result={r}
              active={i === activeIdx}
              onSelect={go}
            />
          ))}
        </div>

        <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
          <span>
            ↑/↓ 选择 · Enter 打开 · Esc 关闭
          </span>
          {tookMs !== null && (
            <span data-testid="search-took-ms">{tookMs} ms · {total} 条</span>
          )}
        </div>
      </div>
    </div>
  );
}

export default GlobalSearchPalette;

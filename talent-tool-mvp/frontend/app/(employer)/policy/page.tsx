"use client";

/**
 * Policy browsing page (T601).
 *
 * Loads `GET /api/policy/list` for the current organisation, renders a
 * searchable / filterable grid of policy cards. Clicking a card pushes
 * to `/employer/policy/[id]`.
 *
 * Layout (top → bottom):
 *   Header (title + refresh)
 *   CategoryFilter (pills)
 *   PolicySearch (local full-text)
 *   PolicyList (3-col on desktop)
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  RefreshCcw,
  Loader2,
  FileText,
  AlertCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import {
  policyApi,
  type PolicyCategory,
  type PolicyDoc,
} from "@/lib/api-policy";
import { CategoryFilter } from "@/components/policy/CategoryFilter";
import { PolicySearch } from "@/components/policy/PolicySearch";
import { PolicyList } from "@/components/policy/PolicyList";

const REFRESH_MS = 60_000;

export default function PolicyBrowsePage() {
  const router = useRouter();
  const [docs, setDocs] = React.useState<PolicyDoc[]>([]);
  const [category, setCategory] = React.useState<PolicyCategory | "">("");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);

  const load = React.useCallback(
    async (manual = false) => {
      if (manual) setRefreshing(true);
      else setLoading(true);
      setError(null);
      try {
        const resp = await policyApi.list({ category: category || undefined });
        setDocs(resp.data);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "加载制度失败");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [category],
  );

  React.useEffect(() => {
    load();
    const id = window.setInterval(() => load(), REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => router.push("/employer")}
              aria-label="返回"
            >
              <ArrowLeft className="size-4" />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                <FileText className="size-5 text-blue-500" />
                规章制度库
              </h1>
              <p className="text-xs text-muted-foreground">
                浏览、检索公司制度 · 智能体语义检索已接入
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(true)}
            disabled={refreshing}
            className="gap-2"
          >
            {refreshing ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCcw className="size-4" />
            )}
            刷新
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-4 px-6 py-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <CategoryFilter
            value={category || null}
            onChange={(v) => setCategory((v ?? "") as PolicyCategory | "")}
            className="lg:flex-1"
          />
          <PolicySearch
            corpus={docs}
            mode="local"
            autoFocus
            placeholder="按关键词搜索制度 (例: 出差, 加班, 报销)…"
            onSelect={(item) => router.push(`/employer/policy/${item.id}`)}
            className="lg:max-w-sm lg:flex-1"
          />
        </div>

        {loading && <LoadingState />}
        {error && !loading && (
          <ErrorState message={error} onRetry={() => load(true)} />
        )}

        {!loading && !error && (
          <PolicyList
            docs={docs}
            loading={loading}
            showCountBadge
            onSelect={(d) => router.push(`/employer/policy/${d.id}`)}
          />
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin text-blue-500" />
        加载制度中…
      </CardContent>
    </Card>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Card className="border-rose-200 bg-rose-50/60">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-10 text-sm text-rose-700">
        <AlertCircle className="size-5" />
        <span>{message}</span>
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      </CardContent>
    </Card>
  );
}

export { cn };

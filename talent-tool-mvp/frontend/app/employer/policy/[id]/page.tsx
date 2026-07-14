"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Policy detail page (T601).
 *
 * Loads `GET /api/policy/list` once to resolve the requested id (cheap
 * list endpoint) — proper detail endpoint isn't part of the T601 backend
 * yet, so the page re-uses the list call to look up the doc. Clauses are
 * sourced from the same request payload when available, else from the
 * raw `content`.
 */

import * as React from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  Search,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

import {
  policyApi,
  type PolicyDoc,
  type PolicyClause,
} from "@/lib/api-policy";
import { PolicyDetail } from "@/components/policy/PolicyDetail";
import { PolicySearch } from "@/components/policy/PolicySearch";

export default function PolicyDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const [doc, setDoc] = React.useState<PolicyDoc | null>(null);
  const [clauses, setClauses] = React.useState<PolicyClause[]>([]);
  const [corpus, setCorpus] = React.useState<PolicyDoc[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    policyApi
      .list({})
      .then((resp) => {
        if (cancelled) return;
        setCorpus(resp.data);
        const match = resp.data.find((d) => d.id === id) ?? null;
        setDoc(match);
        if (!match) {
          setError("未找到该制度,可能已被删除或归档");
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
        <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-4">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => router.push("/employer/policy")}
              aria-label="返回制度库"
            >
              <ArrowLeft className="size-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <h1 className="flex items-center gap-2 text-lg font-semibold text-foreground">
                <FileText className="size-5 text-blue-500" />
                制度详情
              </h1>
              <p className="truncate text-xs text-muted-foreground">
                {doc?.title ?? "加载中…"}
              </p>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-5xl space-y-4 px-6 py-6">
          <PolicyDetail
            doc={doc}
            clauses={clauses}
            loading={loading}
            error={error}
            onBack={() => router.push("/employer/policy")}
          />

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <header className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
              <Search className="size-4 text-blue-500" />
              跳转到其他制度
            </header>
            <PolicySearch
              corpus={corpus}
              mode="local"
              placeholder="从制度库中搜索其他条目…"
              onSelect={(item) => router.push(`/employer/policy/${item.id}`)}
            />
          </div>
        </main>
      </div>)</ErrorBoundary>
  );
}

export { cn };

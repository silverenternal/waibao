"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * T2704: Prompt v2 admin index — list + create new versions.
 */

import * as React from "react";
import { useRouter } from "next/navigation";

import PromptEditor from "@/components/prompts/PromptEditor";
import type { PromptSummary, PromptVersion } from "@/components/prompts/types";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  if (r.status === 204) return null as unknown as T;
  return r.json();
}

export default function PromptsAdminPage(): React.JSX.Element {
  const router = useRouter();
  const [summaries, setSummaries] = React.useState<PromptSummary[]>([]);
  const [showCreate, setShowCreate] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const reload = React.useCallback(async () => {
    try {
      const rows = await api<PromptSummary[]>(`/api/prompts`);
      setSummaries(rows || []);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  React.useEffect(() => {
    reload();
  }, [reload]);

  return (
    <ErrorBoundary>(<main className="mx-auto max-w-6xl p-6 space-y-6">
        <header className="flex justify-between items-end">
          <div>
            <h1 className="text-3xl font-semibold">Prompts</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Versioned prompts with A/B traffic split and LLM-as-judge
              evaluation (Agenta vendor-in).
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowCreate((v) => !v)}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium"
          >
            {showCreate ? "Cancel" : "New version"}
          </button>
        </header>
        {error && (
          <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm">
            {error}
          </div>
        )}
        {showCreate && (
          <section className="rounded-md border p-4">
            <h2 className="text-lg font-semibold mb-3">Create draft version</h2>
            <PromptEditor
              submitLabel="Create draft"
              onSubmit={async (values) => {
                await api<PromptVersion>(`/api/prompts`, {
                  method: "POST",
                  body: JSON.stringify(values),
                });
                setShowCreate(false);
                await reload();
              }}
            />
          </section>
        )}
        <section>
          <h2 className="text-lg font-semibold mb-2">Tracked prompts</h2>
          {summaries.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No prompts yet — create one above.
            </p>
          ) : (
            <table className="w-full text-sm border rounded-md overflow-hidden">
              <thead className="bg-muted text-left">
                <tr>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Agent</th>
                  <th className="px-3 py-2">Latest</th>
                  <th className="px-3 py-2">Active</th>
                  <th className="px-3 py-2">Versions</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {summaries.map((s) => (
                  <tr
                    key={`${s.name}::${s.agent}`}
                    className="border-t hover:bg-muted/40"
                  >
                    <td className="px-3 py-2 font-medium">{s.name}</td>
                    <td className="px-3 py-2">{s.agent}</td>
                    <td className="px-3 py-2">v{s.latest_version}</td>
                    <td className="px-3 py-2">{s.active}</td>
                    <td className="px-3 py-2">{s.versions}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        onClick={() =>
                          router.push(`/admin/prompts/${encodeURIComponent(s.name)}`)
                        }
                        className="px-2 py-1 rounded border text-xs"
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>)</ErrorBoundary>
  );
}
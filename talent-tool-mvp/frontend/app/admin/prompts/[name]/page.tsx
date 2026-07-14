"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * T2704: Prompt v2 detail — version list, A/B traffic, eval.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";

import PromptEditor from "@/components/prompts/PromptEditor";
import PromptVersionDiff from "@/components/prompts/PromptVersionDiff";
import type {
  EvalRun,
  PromptDiff,
  PromptVersion,
} from "@/components/prompts/types";

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

export default function PromptDetailPage(): React.JSX.Element {
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params?.name ?? "");
  const router = useRouter();

  const [versions, setVersions] = React.useState<PromptVersion[]>([]);
  const [leftId, setLeftId] = React.useState<string | null>(null);
  const [rightId, setRightId] = React.useState<string | null>(null);
  const [diff, setDiff] = React.useState<PromptDiff | null>(null);
  const [runs, setRuns] = React.useState<EvalRun[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [trafficFrom, setTrafficFrom] = React.useState<string>("");
  const [trafficTo, setTrafficTo] = React.useState<string>("");
  const [trafficPct, setTrafficPct] = React.useState<number>(10);
  const [showDraft, setShowDraft] = React.useState(false);

  const reload = React.useCallback(async () => {
    if (!name) return;
    try {
      const [vs, evals] = await Promise.all([
        api<PromptVersion[]>(`/api/prompts/${encodeURIComponent(name)}`),
        api<EvalRun[]>(`/api/prompts/${encodeURIComponent(name)}/evaluations`),
      ]);
      setVersions(vs || []);
      setRuns(evals || []);
      if (!leftId && vs?.length) setLeftId(vs[0].id);
      if (!rightId && vs?.length > 1) setRightId(vs[1].id);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [name, leftId, rightId]);

  React.useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name]);

  React.useEffect(() => {
    if (!leftId || !rightId) return;
    api<PromptDiff>(
      `/api/prompts/${encodeURIComponent(name)}/diff?left=${leftId}&right=${rightId}`,
    ).then(setDiff).catch(() => setDiff(null));
  }, [leftId, rightId, name]);

  const active = versions.filter((v) => v.status === "active");
  const totalTraffic = active.reduce((acc, v) => acc + v.traffic_pct, 0);

  const runEval = async (versionId: string) => {
    setBusy(true);
    try {
      await api<EvalRun>(
        `/api/prompts/${encodeURIComponent(name)}/evaluate`,
        { method: "POST", body: JSON.stringify({ version_id: versionId, n: 50 }) },
      );
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const shift = async () => {
    if (!trafficFrom || !trafficTo) return;
    setBusy(true);
    try {
      await api(
        `/api/prompts/${encodeURIComponent(name)}/traffic`,
        {
          method: "POST",
          body: JSON.stringify({
            from_version: Number(trafficFrom),
            to_version: Number(trafficTo),
            shift_pct: trafficPct,
          }),
        },
      );
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ErrorBoundary>(<main className="mx-auto max-w-7xl p-6 space-y-6">
        <header className="flex justify-between items-end">
          <div>
            <button
              type="button"
              onClick={() => router.push("/admin/prompts")}
              className="text-xs text-muted-foreground hover:underline"
            >
              ← back to prompts
            </button>
            <h1 className="text-3xl font-semibold mt-1">{name}</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {versions.length} versions — active traffic split: {totalTraffic}%
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowDraft((v) => !v)}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium"
          >
            {showDraft ? "Cancel" : "New draft"}
          </button>
        </header>
        {error && (
          <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm">
            {error}
          </div>
        )}
        {showDraft && (
          <section className="rounded-md border p-4">
            <h2 className="text-lg font-semibold mb-3">New draft version</h2>
            <PromptEditor
              initial={{ name, status: "draft", traffic_pct: 0 }}
              submitLabel="Create draft"
              onSubmit={async (values) => {
                await api(`/api/prompts`, {
                  method: "POST",
                  body: JSON.stringify({ ...values, name, agent: "default" }),
                });
                setShowDraft(false);
                await reload();
              }}
            />
          </section>
        )}
        <section className="rounded-md border p-4 space-y-3">
          <h2 className="text-lg font-semibold">Versions</h2>
          <table className="w-full text-sm">
            <thead className="text-left">
              <tr>
                <th className="py-1 pr-2">Version</th>
                <th className="py-1 pr-2">Status</th>
                <th className="py-1 pr-2">Traffic %</th>
                <th className="py-1 pr-2">Variables</th>
                <th className="py-1 pr-2">Tags</th>
                <th className="py-1 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.id} className="border-t">
                  <td className="py-1 pr-2 font-mono">v{v.version}</td>
                  <td className="py-1 pr-2">
                    <span className={statusClass(v.status)}>{v.status}</span>
                  </td>
                  <td className="py-1 pr-2">{v.traffic_pct}</td>
                  <td className="py-1 pr-2 text-xs">
                    {v.variables.join(", ") || "—"}
                  </td>
                  <td className="py-1 pr-2 text-xs">
                    {v.tags.join(", ") || "—"}
                  </td>
                  <td className="py-1 pr-2 text-right space-x-1">
                    <button
                      type="button"
                      onClick={() => runEval(v.id)}
                      disabled={busy}
                      className="px-2 py-1 rounded border text-xs disabled:opacity-50"
                    >
                      Eval
                    </button>
                    <button
                      type="button"
                      onClick={() => setLeftId(v.id)}
                      className="px-2 py-1 rounded border text-xs"
                    >
                      Left
                    </button>
                    <button
                      type="button"
                      onClick={() => setRightId(v.id)}
                      className="px-2 py-1 rounded border text-xs"
                    >
                      Right
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="rounded-md border p-4 space-y-3">
          <h2 className="text-lg font-semibold">A/B traffic shift</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end text-sm">
            <label>
              <span className="block font-medium mb-1">From version</span>
              <input
                value={trafficFrom}
                onChange={(e) => setTrafficFrom(e.target.value)}
                className="w-full border rounded px-2 py-1 bg-background"
              />
            </label>
            <label>
              <span className="block font-medium mb-1">To version</span>
              <input
                value={trafficTo}
                onChange={(e) => setTrafficTo(e.target.value)}
                className="w-full border rounded px-2 py-1 bg-background"
              />
            </label>
            <label>
              <span className="block font-medium mb-1">Shift %</span>
              <input
                type="number"
                min={1}
                max={100}
                value={trafficPct}
                onChange={(e) => setTrafficPct(Number(e.target.value) || 0)}
                className="w-full border rounded px-2 py-1 bg-background"
              />
            </label>
            <button
              type="button"
              onClick={shift}
              disabled={busy}
              className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50"
            >
              Shift traffic
            </button>
          </div>
        </section>
        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <h3 className="text-md font-semibold mb-2">Left</h3>
            <select
              value={leftId ?? ""}
              onChange={(e) => setLeftId(e.target.value)}
              className="w-full border rounded px-2 py-1 text-sm bg-background mb-2"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version} ({v.status})
                </option>
              ))}
            </select>
          </div>
          <div>
            <h3 className="text-md font-semibold mb-2">Right</h3>
            <select
              value={rightId ?? ""}
              onChange={(e) => setRightId(e.target.value)}
              className="w-full border rounded px-2 py-1 text-sm bg-background mb-2"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version} ({v.status})
                </option>
              ))}
            </select>
          </div>
        </section>
        {diff && <PromptVersionDiff diff={diff} />}
        <section className="rounded-md border p-4 space-y-3">
          <h2 className="text-lg font-semibold">Evaluation history</h2>
          {runs.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No runs yet — click Eval on a version above.
            </p>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-left">
                <tr>
                  <th className="py-1 pr-2">Run</th>
                  <th className="py-1 pr-2">Version</th>
                  <th className="py-1 pr-2">Cases</th>
                  <th className="py-1 pr-2">Accuracy</th>
                  <th className="py-1 pr-2">Fluency</th>
                  <th className="py-1 pr-2">Safety</th>
                  <th className="py-1 pr-2">Bias</th>
                  <th className="py-1 pr-2">Overall</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-t">
                    <td className="py-1 pr-2 font-mono">{r.id.slice(0, 8)}</td>
                    <td className="py-1 pr-2">v{r.version}</td>
                    <td className="py-1 pr-2">{r.case_count}</td>
                    <td className="py-1 pr-2">{r.summary.accuracy.toFixed(3)}</td>
                    <td className="py-1 pr-2">{r.summary.fluency.toFixed(3)}</td>
                    <td className="py-1 pr-2">{r.summary.safety.toFixed(3)}</td>
                    <td className="py-1 pr-2">{r.summary.bias.toFixed(3)}</td>
                    <td className="py-1 pr-2 font-medium">
                      {r.summary.overall.toFixed(3)}
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

function statusClass(status: string): string {
  const base = "px-2 py-0.5 rounded text-xs";
  if (status === "active") return `${base} bg-green-500/15 text-green-700`;
  if (status === "retired") return `${base} bg-muted text-muted-foreground`;
  return `${base} bg-amber-500/15 text-amber-700`;
}
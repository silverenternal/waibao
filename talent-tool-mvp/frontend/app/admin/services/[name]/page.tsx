"use client";

/**
 * v8.0 T3501 — Single Service detail / override / rollback.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";

type Status = "enabled" | "disabled" | "maintenance" | "beta";

interface ServiceDetail {
  name: string;
  display_name: string;
  description?: string;
  category: string;
  status: Status;
  plan_required: string;
  roles_allowed: string[];
  dependencies?: string[];
  dependencies_resolved?: string[];
  dependents?: string[];
  declared_dependencies?: string[];
  version?: number;
}

const STATUSES: Status[] = ["enabled", "disabled", "maintenance", "beta"];

async function apiFetch<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${txt}`);
  }
  return (await res.json()) as T;
}

export default function ServiceDetailPage(): React.ReactElement {
  const params = useParams<{ name: string }>();
  const router = useRouter();
  const name = decodeURIComponent(params.name);

  const [detail, setDetail] = React.useState<ServiceDetail | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [orgId, setOrgId] = React.useState("");
  const [overrideStatus, setOverrideStatus] = React.useState<Status>("disabled");
  const [reason, setReason] = React.useState("");

  const reload = React.useCallback(async () => {
    try {
      const data = await apiFetch<ServiceDetail>(
        `/api/admin/services/${encodeURIComponent(name)}`,
      );
      setDetail(data);
      setError(null);
    } catch (e: unknown) {
      setError((e as Error).message ?? "load failed");
    }
  }, [name]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  async function setStatus(status: Status): Promise<void> {
    setSaving(true);
    try {
      await apiFetch(`/api/admin/services/${encodeURIComponent(name)}`, {
        method: "PATCH",
        body: JSON.stringify({ status, reason }),
      });
      await reload();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function applyOverride(): Promise<void> {
    if (!orgId) return;
    setSaving(true);
    try {
      await apiFetch(`/api/admin/services/${encodeURIComponent(name)}/override`, {
        method: "POST",
        body: JSON.stringify({
          org_id: orgId,
          status: overrideStatus,
          reason,
        }),
      });
      await reload();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function rollback(): Promise<void> {
    setSaving(true);
    try {
      await apiFetch(`/api/admin/services/${encodeURIComponent(name)}/rollback`, {
        method: "POST",
      });
      await reload();
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {detail?.display_name ?? name}
          </h1>
          <p className="font-mono text-xs text-slate-500">{name}</p>
        </div>
        <button
          onClick={() => router.push("/admin/services")}
          className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm"
        >
          ← Back
        </button>
      </header>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {detail ? (
        <>
          <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Stat label="Status" value={detail.status} />
            <Stat label="Plan" value={detail.plan_required} />
            <Stat label="Category" value={detail.category} />
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-lg font-medium">Change status</h2>
            <div className="flex flex-wrap gap-2">
              {STATUSES.map((s) => (
                <button
                  key={s}
                  disabled={saving}
                  onClick={() => setStatus(s)}
                  className={
                    "rounded-md border px-3 py-1 text-sm " +
                    (detail.status === s
                      ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                      : "border-slate-300 bg-white hover:bg-slate-50")
                  }
                >
                  {s}
                </button>
              ))}
              <button
                disabled={saving}
                onClick={rollback}
                className="ml-auto rounded-md border border-amber-300 bg-amber-50 px-3 py-1 text-sm text-amber-800 hover:bg-amber-100"
              >
                1-key rollback
              </button>
            </div>
            <textarea
              placeholder="Reason (audit log)…"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              rows={2}
            />
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-lg font-medium">Per-org override</h2>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
              <input
                placeholder="org_id"
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
              <select
                value={overrideStatus}
                onChange={(e) => setOverrideStatus(e.target.value as Status)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                {STATUSES.filter((s) => s !== "beta").map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <button
                disabled={!orgId || saving}
                onClick={applyOverride}
                className="rounded-md border border-slate-900 bg-slate-900 px-3 py-2 text-sm text-white hover:bg-black disabled:opacity-50"
              >
                Apply override
              </button>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-lg font-medium">Dependency graph</h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">
                  Declared dependencies
                </div>
                <ul className="list-disc pl-5 text-sm">
                  {(detail.declared_dependencies ?? []).map((d) => (
                    <li key={d} className="font-mono">{d}</li>
                  ))}
                  {(detail.declared_dependencies ?? []).length === 0 ? (
                    <li className="text-slate-400">none</li>
                  ) : null}
                </ul>
              </div>
              <div>
                <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">
                  Resolved (transitive)
                </div>
                <ul className="list-disc pl-5 text-sm">
                  {(detail.dependencies_resolved ?? []).map((d) => (
                    <li key={d} className="font-mono">{d}</li>
                  ))}
                </ul>
              </div>
              <div className="md:col-span-2">
                <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">
                  Dependents (services that require this one)
                </div>
                <ul className="list-disc pl-5 text-sm">
                  {(detail.dependents ?? []).map((d) => (
                    <li key={d} className="font-mono">{d}</li>
                  ))}
                  {(detail.dependents ?? []).length === 0 ? (
                    <li className="text-slate-400">none</li>
                  ) : null}
                </ul>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-lg font-medium">Roles allowed</h2>
            <ul className="flex flex-wrap gap-2 text-xs">
              {(detail.roles_allowed ?? []).length === 0 ? (
                <li className="text-slate-400">any</li>
              ) : (
                detail.roles_allowed.map((r) => (
                  <li
                    key={r}
                    className="rounded-full bg-indigo-50 px-2 py-1 text-indigo-700"
                  >
                    {r}
                  </li>
                ))
              )}
            </ul>
          </section>
        </>
      ) : (
        <div className="rounded-md border border-slate-200 bg-white p-6 text-center text-slate-500">
          Loading service…
        </div>
      )}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }): React.ReactElement {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-900">{value}</div>
    </div>
  );
}

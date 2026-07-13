"use client";

import { useEffect, useState } from "react";
import { getAuthToken, apiFetch } from "@/lib/api-portal";

type DeveloperApp = {
  id: string;
  name: string;
  client_id: string;
  environment: "sandbox" | "live";
};

type ApiKeyRow = {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  rate_limit_per_min: number;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
};

const SCOPES = [
  "candidates:read",
  "candidates:write",
  "roles:read",
  "matches:write",
  "tickets:write",
];

export function ManageKeysClient() {
  const [apps, setApps] = useState<DeveloperApp[]>([]);
  const [selectedApp, setSelectedApp] = useState<string>("");
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [selectedScopes, setSelectedScopes] = useState<string[]>(["candidates:read"]);
  const [reveal, setReveal] = useState<{
    plaintext: string;
    name: string;
  } | null>(null);

  async function loadApps() {
    const res = await apiFetch("/api/developer/apps");
    if (!res.ok) {
      setLoading(false);
      return;
    }
    const data = (await res.json()) as DeveloperApp[];
    setApps(data);
    if (data[0] && !selectedApp) setSelectedApp(data[0].id);
  }

  async function loadKeys(appId: string) {
    if (!appId) return;
    const res = await apiFetch(`/api/developer/apps/${appId}/keys`);
    if (!res.ok) {
      setKeys([]);
      return;
    }
    setKeys((await res.json()) as ApiKeyRow[]);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await loadApps();
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedApp) loadKeys(selectedApp);
  }, [selectedApp]);

  async function createKey(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedApp || !newName.trim()) return;
    setCreating(true);
    try {
      const res = await apiFetch(`/api/developer/apps/${selectedApp}/keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName,
          scopes: selectedScopes,
          rate_limit_per_min: 60,
        }),
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = (await res.json()) as ApiKeyRow & { plaintext: string };
      setReveal({ plaintext: data.plaintext, name: data.name });
      setNewName("");
      await loadKeys(selectedApp);
    } finally {
      setCreating(false);
    }
  }

  async function revokeKey(keyId: string) {
    if (!selectedApp) return;
    if (!confirm("Revoke this key? Active integrations using it will start failing."))
      return;
    await apiFetch(`/api/developer/apps/${selectedApp}/keys/${keyId}`, {
      method: "DELETE",
    });
    await loadKeys(selectedApp);
  }

  if (loading) {
    return (
      <div className="rounded-md border border-border bg-muted/20 p-6 text-sm text-muted-foreground">
        Loading apps …
      </div>
    );
  }

  if (apps.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border bg-muted/20 p-6 text-sm">
        <p className="font-medium">No developer apps yet.</p>
        <p className="mt-1 text-muted-foreground">
          Register your first app from the dashboard, then come back here to mint
          keys.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-xs">
          <span className="text-muted-foreground">App</span>
          <select
            value={selectedApp}
            onChange={(e) => setSelectedApp(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1 text-sm"
          >
            {apps.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.environment})
              </option>
            ))}
          </select>
        </label>
      </div>

      <form
        onSubmit={createKey}
        className="rounded-lg border border-border bg-card p-4 space-y-3"
      >
        <p className="text-sm font-semibold">Mint a new key</p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-1 flex-col text-xs">
            <span className="text-muted-foreground">Name</span>
            <input
              required
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. ci-deployment"
              className="rounded-md border border-input bg-background px-3 py-1 text-sm"
            />
          </label>
          <fieldset className="text-xs">
            <legend className="mb-1 text-muted-foreground">Scopes</legend>
            <div className="flex flex-wrap gap-2">
              {SCOPES.map((s) => (
                <label
                  key={s}
                  className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={selectedScopes.includes(s)}
                    onChange={(e) => {
                      setSelectedScopes((prev) =>
                        e.target.checked
                          ? [...prev, s]
                          : prev.filter((x) => x !== s),
                      );
                    }}
                  />
                  <code>{s}</code>
                </label>
              ))}
            </div>
          </fieldset>
          <button
            type="submit"
            disabled={creating}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {creating ? "Creating …" : "Generate key"}
          </button>
        </div>
      </form>

      {reveal ? (
        <div className="rounded-md border-2 border-amber-400 bg-amber-50 p-4 dark:bg-amber-950/30">
          <p className="text-sm font-semibold text-amber-900 dark:text-amber-100">
            Save this key now — you will not see it again.
          </p>
          <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">
            <code>{reveal.name}</code>
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-background p-2 text-xs">
            <code>{reveal.plaintext}</code>
          </pre>
          <button
            type="button"
            onClick={() => setReveal(null)}
            className="mt-2 rounded-md bg-amber-900 px-3 py-1 text-xs text-amber-50 hover:bg-amber-700"
          >
            I have saved it
          </button>
        </div>
      ) : null}

      <table className="w-full overflow-hidden rounded-md border border-border bg-card text-sm">
        <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left">Name</th>
            <th className="px-3 py-2 text-left">Prefix</th>
            <th className="px-3 py-2 text-left">Scopes</th>
            <th className="px-3 py-2 text-left">Rate/min</th>
            <th className="px-3 py-2 text-left">Status</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {keys.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                No keys yet. Mint your first one above.
              </td>
            </tr>
          ) : null}
          {keys.map((k) => (
            <tr key={k.id}>
              <td className="px-3 py-2">{k.name}</td>
              <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                {k.key_prefix}…
              </td>
              <td className="px-3 py-2 text-xs">
                {k.scopes.length === 0 ? <em>none</em> : k.scopes.join(", ")}
              </td>
              <td className="px-3 py-2 text-xs">{k.rate_limit_per_min}</td>
              <td className="px-3 py-2 text-xs">
                {k.revoked_at ? (
                  <span className="rounded bg-red-500/10 px-2 py-0.5 text-red-700 dark:text-red-300">
                    revoked
                  </span>
                ) : (
                  <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-emerald-700 dark:text-emerald-300">
                    active
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-right">
                {!k.revoked_at ? (
                  <button
                    type="button"
                    onClick={() => revokeKey(k.id)}
                    className="rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-muted"
                  >
                    Revoke
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

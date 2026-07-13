"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api-portal";

type DeveloperApp = {
  id: string;
  name: string;
  client_id: string;
  environment: "sandbox" | "live";
};

type WebhookRow = {
  id: string;
  app_id: string;
  url: string;
  events: string[];
  secret_prefix: string;
  created_at: string;
  active: boolean;
  last_delivered_at: string | null;
  last_status: number | null;
};

export function WebhookManager({
  supportedEvents,
}: {
  supportedEvents: string[];
}) {
  const [apps, setApps] = useState<DeveloperApp[]>([]);
  const [selectedApp, setSelectedApp] = useState("");
  const [hooks, setHooks] = useState<WebhookRow[]>([]);
  const [creating, setCreating] = useState(false);
  const [url, setUrl] = useState("https://example.com/webhook");
  const [events, setEvents] = useState<string[]>(["candidate.created"]);
  const [reveal, setReveal] = useState<{ id: string; secret: string } | null>(
    null,
  );

  async function loadApps() {
    const r = await apiFetch("/api/developer/apps");
    if (!r.ok) return;
    const data = (await r.json()) as DeveloperApp[];
    setApps(data);
    if (data[0]) setSelectedApp(data[0].id);
  }

  async function loadHooks(appId: string) {
    if (!appId) return;
    const r = await apiFetch(`/api/developer/apps/${appId}/webhooks`);
    if (!r.ok) {
      setHooks([]);
      return;
    }
    setHooks((await r.json()) as WebhookRow[]);
  }

  useEffect(() => {
    loadApps();
  }, []);

  useEffect(() => {
    loadHooks(selectedApp);
  }, [selectedApp]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedApp) return;
    setCreating(true);
    try {
      const r = await apiFetch(`/api/developer/apps/${selectedApp}/webhooks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, events }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = (await r.json()) as WebhookRow & { secret: string };
      setReveal({ id: data.id, secret: data.secret });
      await loadHooks(selectedApp);
    } finally {
      setCreating(false);
    }
  }

  async function rotate(webhookId: string) {
    if (!selectedApp) return;
    if (
      !confirm(
        "Rotate the secret? The new value will be shown once and the old one will stop working immediately.",
      )
    )
      return;
    const r = await apiFetch(
      `/api/developer/apps/${selectedApp}/webhooks/${webhookId}/rotate`,
      { method: "POST" },
    );
    if (!r.ok) return;
    const data = (await r.json()) as WebhookRow & { secret: string };
    setReveal({ id: data.id, secret: data.secret });
    await loadHooks(selectedApp);
  }

  async function remove(webhookId: string) {
    if (!selectedApp) return;
    if (!confirm("Delete this webhook? Pending events will be discarded."))
      return;
    await apiFetch(`/api/developer/apps/${selectedApp}/webhooks/${webhookId}`, {
      method: "DELETE",
    });
    await loadHooks(selectedApp);
  }

  if (apps.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border bg-muted/20 p-6 text-sm">
        Register an app first to configure webhooks.
      </div>
    );
  }

  return (
    <div className="space-y-6">
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

      <form
        onSubmit={create}
        className="rounded-lg border border-border bg-card p-4 space-y-3"
      >
        <p className="text-sm font-semibold">Subscribe a URL</p>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="flex flex-col text-xs">
            <span className="text-muted-foreground">Endpoint URL</span>
            <input
              required
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="rounded-md border border-input bg-background px-3 py-1 text-sm"
            />
          </label>
        </div>
        <fieldset className="text-xs">
          <legend className="mb-1 text-muted-foreground">Events</legend>
          <div className="flex flex-wrap gap-2">
            {supportedEvents.map((e) => (
              <label
                key={e}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-xs"
              >
                <input
                  type="checkbox"
                  checked={events.includes(e)}
                  onChange={(ev) => {
                    setEvents((prev) =>
                      ev.target.checked
                        ? [...prev, e]
                        : prev.filter((x) => x !== e),
                    );
                  }}
                />
                <code>{e}</code>
              </label>
            ))}
          </div>
        </fieldset>
        <button
          type="submit"
          disabled={creating}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {creating ? "Creating …" : "Subscribe"}
        </button>
      </form>

      {reveal ? (
        <div className="rounded-md border-2 border-amber-400 bg-amber-50 p-4 dark:bg-amber-950/30">
          <p className="text-sm font-semibold text-amber-900 dark:text-amber-100">
            New webhook secret — copy now, you will not see it again.
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-background p-2 text-xs">
            <code>{reveal.secret}</code>
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
            <th className="px-3 py-2 text-left">URL</th>
            <th className="px-3 py-2 text-left">Events</th>
            <th className="px-3 py-2 text-left">Secret</th>
            <th className="px-3 py-2 text-left">Status</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {hooks.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">
                No webhooks yet.
              </td>
            </tr>
          ) : null}
          {hooks.map((h) => (
            <tr key={h.id}>
              <td className="px-3 py-2 font-mono text-xs">{h.url}</td>
              <td className="px-3 py-2 text-xs">
                {h.events.map((e) => (
                  <code
                    key={e}
                    className="mr-1 rounded bg-muted px-1 py-0.5 text-[10px]"
                  >
                    {e}
                  </code>
                ))}
              </td>
              <td className="px-3 py-2 font-mono text-[10px] text-muted-foreground">
                {h.secret_prefix}…
              </td>
              <td className="px-3 py-2 text-xs">
                <span
                  className={
                    "rounded px-2 py-0.5 " +
                    (h.active
                      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                      : "bg-muted text-muted-foreground")
                  }
                >
                  {h.active ? "active" : "paused"}
                </span>
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={() => rotate(h.id)}
                  className="mr-1 rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-muted"
                >
                  Rotate
                </button>
                <button
                  type="button"
                  onClick={() => remove(h.id)}
                  className="rounded-md border border-red-500/50 bg-background px-2 py-1 text-xs text-red-600 hover:bg-red-500/10"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

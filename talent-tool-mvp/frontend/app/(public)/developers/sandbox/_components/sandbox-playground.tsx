"use client";

import { useState } from "react";

type Preset = {
  label: string;
  method: string;
  path: string;
  body?: string;
};

type ResultRow = {
  status: number;
  ok: boolean;
  body: string;
  headers: Record<string, string>;
  durationMs: number;
};

const INTERESTING_HEADERS = [
  "x-api-version",
  "x-api-deprecated",
  "deprecation",
  "sunset",
  "link",
  "x-api-successor-version",
  "x-request-id",
  "x-rate-limit-remaining",
  "content-type",
];

export function SandboxPlayground({ presets }: { presets: Preset[] }) {
  const [method, setMethod] = useState("GET");
  const [path, setPath] = useState("/api/v2/version");
  const [body, setBody] = useState("");
  const [result, setResult] = useState<ResultRow | null>(null);
  const [loading, setLoading] = useState(false);

  async function fire(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const started = performance.now();
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const headers: Record<string, string> = { "X-API-Version": "v2" };
      let payload: BodyInit | undefined;
      if (method !== "GET" && method !== "HEAD" && body.trim()) {
        headers["Content-Type"] = headers["Content-Type"] ?? "application/json";
        payload = body;
      }
      const r = await fetch(`${apiBase}${path}`, {
        method,
        headers,
        body: payload,
      });
      const text = await r.text();
      const hdrs: Record<string, string> = {};
      r.headers.forEach((v, k) => (hdrs[k] = v));
      setResult({
        ok: r.ok,
        status: r.status,
        body: text,
        headers: hdrs,
        durationMs: Math.round(performance.now() - started),
      });
    } finally {
      setLoading(false);
    }
  }

  function apply(p: Preset) {
    setMethod(p.method);
    setPath(p.path);
    setBody(p.body ?? "");
  }

  return (
    <div className="grid gap-4 md:grid-cols-[1fr_2fr]">
      <aside className="space-y-3">
        <p className="text-xs font-medium uppercase text-muted-foreground">
          Presets
        </p>
        <ul className="space-y-1">
          {presets.map((p) => (
            <li key={p.label}>
              <button
                type="button"
                onClick={() => apply(p)}
                className="w-full rounded-md border border-border bg-card px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <span className="block font-medium">{p.label}</span>
                <span className="block font-mono text-[10px] uppercase text-muted-foreground">
                  {p.method} {p.path}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="space-y-3">
        <form onSubmit={fire} className="space-y-2 rounded-lg border border-border bg-card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              className="rounded-md border border-input bg-background px-2 py-1 text-sm"
            >
              {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
            <input
              required
              value={path}
              onChange={(e) => setPath(e.target.value)}
              className="flex-1 rounded-md border border-input bg-background px-3 py-1 font-mono text-sm"
              placeholder="/api/v2/candidates"
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-primary px-3 py-1 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {loading ? "Sending …" : "Send"}
            </button>
          </div>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={6}
            placeholder="{ } — request body (JSON)"
            className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
          />
        </form>

        {result ? (
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
              <span
                className={
                  "rounded px-2 py-0.5 font-mono text-xs " +
                  (result.ok
                    ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                    : "bg-red-500/10 text-red-700 dark:text-red-300")
                }
              >
                {result.status}
              </span>
              <span className="text-xs text-muted-foreground">
                {result.durationMs} ms
              </span>
              {result.headers["x-api-deprecated"] === "true" ? (
                <span className="rounded bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
                  Deprecated API — migrate to v2
                </span>
              ) : null}
            </div>
            <details open>
              <summary className="cursor-pointer text-xs font-semibold uppercase text-muted-foreground">
                Response body
              </summary>
              <pre className="mt-2 max-h-72 overflow-auto rounded bg-muted p-3 text-xs">
                <code>{pretty(result.body)}</code>
              </pre>
            </details>
            <details>
              <summary className="cursor-pointer text-xs font-semibold uppercase text-muted-foreground">
                Headers
              </summary>
              <ul className="mt-2 grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
                {INTERESTING_HEADERS.map((h) =>
                  result.headers[h] !== undefined ? (
                    <li key={h} className="font-mono">
                      <span className="text-muted-foreground">{h}:</span>{" "}
                      {result.headers[h]}
                    </li>
                  ) : null,
                )}
              </ul>
            </details>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function pretty(input: string): string {
  try {
    return JSON.stringify(JSON.parse(input), null, 2);
  } catch {
    return input;
  }
}

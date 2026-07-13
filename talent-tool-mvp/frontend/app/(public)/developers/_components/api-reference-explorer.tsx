"use client";

import { useEffect, useState } from "react";

type Operation = {
  operationId: string;
  method: string;
  path: string;
  summary: string;
  tags: string[];
};

type SpecSummary = {
  title: string;
  version: string;
  operations: Operation[];
};

/**
 * Lightweight API reference explorer.
 *
 * Loads /openapi.json from the API, extracts the endpoints, and renders them
 * with a search bar + tag-grouped list.  This is intentionally minimal:
 * for the full schema browser we host Scalar via a CDN script tag at
 * /developers/_scalar (lazy).
 */
export function ApiReferenceExplorer() {
  const [data, setData] = useState<SpecSummary | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const apiBase =
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        const r = await fetch(`${apiBase}/openapi.json`);
        if (!r.ok) {
          setData(fallback());
          return;
        }
        const spec = await r.json();
        const ops: Operation[] = [];
        for (const [path, item] of Object.entries(spec.paths || {})) {
          for (const [method, value] of Object.entries(item as object)) {
            const op = value as Record<string, unknown>;
            ops.push({
              operationId: String(op.operationId ?? `${method}-${path}`),
              method: method.toUpperCase(),
              path,
              summary: String(op.summary ?? ""),
              tags: Array.isArray(op.tags) ? op.tags.map(String) : [],
            });
          }
        }
        if (!cancelled) {
          setData({
            title: spec.info?.title ?? "RecruitTech OpenAPI",
            version: spec.info?.version ?? "3.0",
            operations: ops,
          });
        }
      } catch {
        if (!cancelled) setData(fallback());
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) {
    return (
      <div className="rounded-md border border-border bg-muted/20 p-6 text-sm text-muted-foreground">
        Loading API reference …
      </div>
    );
  }

  const needle = filter.trim().toLowerCase();
  const filtered = data.operations.filter(
    (op) =>
      !needle ||
      op.path.toLowerCase().includes(needle) ||
      op.summary.toLowerCase().includes(needle) ||
      op.method.toLowerCase().includes(needle),
  );
  const grouped = filtered.reduce<Record<string, Operation[]>>((acc, op) => {
    const tag = op.tags[0] ?? "Other";
    acc[tag] = acc[tag] ? [...acc[tag], op] : [op];
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {data.title} v{data.version} — {filtered.length} endpoints
        </p>
        <input
          type="search"
          placeholder="Filter endpoints (path / summary / method) …"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-72 max-w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
        />
      </div>

      {Object.entries(grouped).map(([tag, ops]) => (
        <section key={tag} className="rounded-md border border-border bg-card">
          <header className="border-b border-border bg-muted/30 px-4 py-2 text-xs uppercase tracking-wider text-muted-foreground">
            {tag} <span className="ml-2 rounded bg-background px-1.5 py-0.5">{ops.length}</span>
          </header>
          <ul className="divide-y divide-border">
            {ops.map((op) => (
              <li
                key={`${op.method}-${op.path}-${op.operationId}`}
                className="flex items-start gap-3 px-4 py-2 text-sm"
              >
                <span
                  className={
                    "mt-0.5 inline-block rounded px-2 py-0.5 font-mono text-[10px] font-semibold uppercase " +
                    methodColor(op.method)
                  }
                >
                  {op.method}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs">{op.path}</p>
                  {op.summary ? (
                    <p className="text-xs text-muted-foreground">{op.summary}</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <p className="text-xs text-muted-foreground">
        Prefer the full schema editor? Open{" "}
        <a href="/scalar" className="underline">/scalar</a>{" "}
        (bundled externally) or the classic{" "}
        <a href="/docs" className="underline">/docs</a> Swagger UI.
      </p>
    </div>
  );
}

function methodColor(method: string): string {
  switch (method) {
    case "GET":
      return "bg-blue-500/10 text-blue-700 dark:text-blue-300";
    case "POST":
      return "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "PATCH":
    case "PUT":
      return "bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "DELETE":
      return "bg-red-500/10 text-red-700 dark:text-red-300";
    default:
      return "bg-muted text-foreground";
  }
}

function fallback(): SpecSummary {
  return {
    title: "RecruitTech OpenAPI",
    version: "3.0",
    operations: [
      {
        operationId: "register-developer-app",
        method: "POST",
        path: "/api/developer/apps",
        summary: "Register a developer app",
        tags: ["developer-portal"],
      },
      {
        operationId: "oauth-authorize",
        method: "POST",
        path: "/api/developer/oauth/authorize",
        summary: "OAuth 2.0 Authorization Code grant step 1",
        tags: ["developer-portal"],
      },
      {
        operationId: "oauth-token",
        method: "POST",
        path: "/api/developer/oauth/token",
        summary: "OAuth 2.0 token grant (code or refresh_token)",
        tags: ["developer-portal"],
      },
      {
        operationId: "create-webhook",
        method: "POST",
        path: "/api/developer/apps/{id}/webhooks",
        summary: "Self-service webhook subscription",
        tags: ["developer-portal"],
      },
    ],
  };
}

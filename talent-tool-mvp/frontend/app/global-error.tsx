"use client";

/**
 * T5006 — Global error fallback.
 *
 * This is the outermost error boundary in the Next.js App Router. When it
 * fires the root layout has NOT rendered, so it MUST render its own
 * <html>/<body>. Keep it dependency-free (no CSS imports that rely on the
 * layout, no context providers) so it can boot from a cold failure.
 */

import * as React from "react";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[global-error]", error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily:
            "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
          backgroundColor: "#f8fafc",
          color: "#0f172a",
        }}
      >
        <div style={{ maxWidth: 480, textAlign: "center", padding: "2rem" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 64,
              height: 64,
              borderRadius: "9999px",
              backgroundColor: "#fee2e2",
              color: "#dc2626",
              fontSize: 28,
              marginBottom: 16,
            }}
            aria-hidden
          >
            ⚠
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
            Application error
          </h1>
          <p style={{ fontSize: 14, color: "#475569", marginBottom: 4 }}>
            A critical error occurred and the application could not recover.
          </p>
          {error.digest ? (
            <p
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 12,
                color: "#94a3b8",
              }}
            >
              error digest: {error.digest}
            </p>
          ) : null}
          <p
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 12,
              color: "#94a3b8",
              marginTop: 8,
              wordBreak: "break-word",
            }}
          >
            {error.message}
          </p>
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: 24,
              padding: "10px 20px",
              borderRadius: 8,
              border: "1px solid #cbd5e1",
              backgroundColor: "#ffffff",
              color: "#0f172a",
              fontSize: 14,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}

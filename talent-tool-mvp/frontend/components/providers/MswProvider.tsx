"use client";

/**
 * T5007 — MSW bootstrap provider.
 *
 * When NEXT_PUBLIC_USE_MOCK=true this starts the MSW Service Worker BEFORE
 * the app renders, so every `fetch` the apiClient makes is intercepted by the
 * mock handlers. In any other mode it is a transparent passthrough.
 *
 * Because the worker start is async, we gate children behind `ready` so the
 * first data-fetching render only fires once interception is active — avoiding
 * a race where the initial request escapes to the real network.
 */

import * as React from "react";

const USE_MOCK =
  process.env.NEXT_PUBLIC_USE_MOCK === "true" ||
  process.env.NEXT_PUBLIC_USE_MOCKS === "true";

export function MswProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = React.useState(!USE_MOCK);

  React.useEffect(() => {
    if (!USE_MOCK) return;
    let active = true;
    // Dynamic import keeps msw/browser out of the prod bundle when mocking
    // is disabled (it touches `window`/ServiceWorker at import time).
    import("@/mocks/browser")
      .then(({ worker }) => worker.start({ onUnhandledRequest: "bypass" }))
      .then(() => {
        if (active) setReady(true);
      })
      .catch((err) => {
        console.warn("[msw] failed to start worker", err);
        if (active) setReady(true); // don't block the UI on a mock failure
      });
    return () => {
      active = false;
    };
  }, []);

  if (!ready) return null;
  return <>{children}</>;
}

export default MswProvider;

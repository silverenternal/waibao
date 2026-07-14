/**
 * T5007 — Shared TanStack Query client factory.
 *
 * A single QueryClient is created per browser session (and per request on the
 * server when needed). Defaults are tuned for a recruitment dashboard:
 *   - staleTime 30s: most list/detail views are fine to reuse briefly.
 *   - retry 1 with exponential backoff: avoid hammering a flaky backend.
 *   - refetchOnWindowFocus off: dashboards shouldn't refetch on every tab flip.
 */

import { QueryClient, isServer } from "@tanstack/react-query";

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30 * 1000,
        gcTime: 5 * 60 * 1000,
        retry: 1,
        refetchOnWindowFocus: false,
        retryDelay: (attemptIndex) =>
          Math.min(1000 * 2 ** attemptIndex, 30_000),
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

/**
 * Return a singleton QueryClient in the browser (so cache survives re-renders
 * and HMR), and a fresh client on the server (no cross-request leakage).
 */
export function getQueryClient(): QueryClient {
  if (isServer) {
    // Server: always make a new client.
    return makeQueryClient();
  }
  // Browser: reuse the singleton.
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient();
  }
  return browserQueryClient;
}

export { QueryClient };

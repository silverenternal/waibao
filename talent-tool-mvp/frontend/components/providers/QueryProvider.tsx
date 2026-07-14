"use client";

/**
 * T5007 — TanStack Query provider.
 *
 * Wraps the app in a QueryClientProvider backed by the shared singleton
 * client (see lib/query-client). Place this high in the tree (inside the root
 * Providers) so every client page/hook can call useQuery / useMutation.
 */

import * as React from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { getQueryClient } from "@/lib/query-client";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  // getQueryClient returns a stable singleton in the browser.
  const [client] = React.useState(() => getQueryClient());
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

export default QueryProvider;

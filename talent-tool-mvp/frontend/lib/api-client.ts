/**
 * T5007 — Unified API client.
 *
 * The app always talks to the REAL `api` (lib/api → fetch to the backend). Mock
 * isolation is now handled at the NETWORK layer by MSW (mocks/handlers.ts),
 * enabled via NEXT_PUBLIC_USE_MOCK=true — no more in-process mockApi swap, so
 * pages cannot accidentally import fixture data and the data-fetching path is
 * identical in mock and real modes.
 *
 * For declarative data fetching prefer the TanStack Query hooks in
 * lib/queries.ts (useQuery / useMutation) over calling apiClient directly.
 */

import { api } from "./api";
import type { ApiClient } from "./api";

export const apiClient: ApiClient = api;

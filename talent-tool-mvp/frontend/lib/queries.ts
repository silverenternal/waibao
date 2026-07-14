/**
 * T5007 — TanStack Query hooks over the apiClient.
 *
 * Pages should migrate from `useState` + `useEffect` + `apiClient.x()` to these
 * `useQuery` / `useMutation` hooks. They give you caching, dedup, background
 * refetch, loading/error states, and invalidation — for free.
 *
 * Convention:
 *   - queryKey is a stable tuple hierarchy: `["resource", ...args]`.
 *   - list/detail keys are namespaced so a mutation can invalidate a whole
 *     resource with `queryClient.invalidateQueries({ queryKey: ["candidates"] })`.
 */

"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
  keepPreviousData,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { CandidateCreate } from "@/contracts/canonical";

// ------------------------------------------------------------------
// Generic helper — wrap any apiClient reader in useQuery.
// ------------------------------------------------------------------
export function useApiQuery<T>(
  key: unknown[],
  fetcher: () => Promise<T>,
  options?: Omit<UseQueryOptions<T>, "queryKey" | "queryFn">,
) {
  return useQuery<T>({
    queryKey: key,
    queryFn: fetcher,
    ...options,
  });
}

// ------------------------------------------------------------------
// Candidates
// ------------------------------------------------------------------
export const candidateKeys = {
  all: ["candidates"] as const,
  lists: () => [...candidateKeys.all, "list"] as const,
  detail: (id: string) => [...candidateKeys.all, "detail", id] as const,
};

export function useCandidates() {
  return useQuery({
    queryKey: candidateKeys.lists(),
    queryFn: () => apiClient.candidates.list(),
  });
}

export function useCandidate(id: string) {
  return useQuery({
    queryKey: candidateKeys.detail(id),
    queryFn: () => apiClient.candidates.get(id),
    enabled: !!id,
  });
}

export function useSearchCandidates(query: string) {
  return useQuery({
    queryKey: [...candidateKeys.all, "search", query] as const,
    queryFn: () => apiClient.candidates.search(query),
    enabled: query.length > 0,
    placeholderData: keepPreviousData,
  });
}

export function useCreateCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CandidateCreate) => apiClient.candidates.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: candidateKeys.all }),
  });
}

// ------------------------------------------------------------------
// Roles
// ------------------------------------------------------------------
export const roleKeys = {
  all: ["roles"] as const,
  lists: () => [...roleKeys.all, "list"] as const,
  detail: (id: string) => [...roleKeys.all, "detail", id] as const,
};

export function useRoles() {
  return useQuery({
    queryKey: roleKeys.lists(),
    queryFn: () => apiClient.roles.list(),
  });
}

export function useRole(id: string) {
  return useQuery({
    queryKey: roleKeys.detail(id),
    queryFn: () => apiClient.roles.get(id),
    enabled: !!id,
  });
}

// ------------------------------------------------------------------
// Matches
// ------------------------------------------------------------------
export const matchKeys = {
  all: ["matches"] as const,
  forRole: (roleId: string) => [...matchKeys.all, "role", roleId] as const,
  forCandidate: (id: string) =>
    [...matchKeys.all, "candidate", id] as const,
};

export function useMatchesForRole(roleId: string) {
  return useQuery({
    queryKey: matchKeys.forRole(roleId),
    queryFn: () => apiClient.matches.forRole(roleId),
    enabled: !!roleId,
  });
}

// ------------------------------------------------------------------
// Users
// ------------------------------------------------------------------
export function useCurrentUser() {
  return useQuery({
    queryKey: ["users", "me"],
    queryFn: () => apiClient.users.me(),
  });
}

export function useAdminUsers() {
  return useQuery({
    queryKey: ["users", "admin"],
    queryFn: () => apiClient.admin.users(),
  });
}

// ------------------------------------------------------------------
// Collections / Handoffs
// ------------------------------------------------------------------
export function useCollections() {
  return useQuery({
    queryKey: ["collections"],
    queryFn: () => apiClient.collections.list(),
  });
}

export function useHandoffInbox() {
  return useQuery({
    queryKey: ["handoffs", "inbox"],
    queryFn: () => apiClient.handoffs.inbox(),
  });
}

export function useHandoffOutbox() {
  return useQuery({
    queryKey: ["handoffs", "outbox"],
    queryFn: () => apiClient.handoffs.outbox(),
  });
}

// ------------------------------------------------------------------
// Analytics
// ------------------------------------------------------------------
export function useFunnel(days = 30, orgId?: string) {
  return useQuery({
    queryKey: ["analytics", "funnel", days, orgId ?? null],
    queryFn: () => apiClient.analytics.funnel(days, orgId),
  });
}

export function useChannelRoi(days = 30) {
  return useQuery({
    queryKey: ["analytics", "channels", "roi", days],
    queryFn: () => apiClient.analytics.channelRoi(days),
  });
}

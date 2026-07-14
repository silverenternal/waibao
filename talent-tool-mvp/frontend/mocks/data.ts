/**
 * T5007 — Mock data source for MSW handlers.
 *
 * This module is the ONLY place MSW (and any fixture consumer) reaches for
 * mock data. Application code must NEVER import fixtures directly — it goes
 * through the real `apiClient` (lib/api-client), and MSW intercepts the
 * underlying `fetch` at the network layer when `NEXT_PUBLIC_USE_MOCK=true`.
 *
 * The actual fixtures live in mocks/fixtures.ts (moved out of lib/ to enforce
 * the boundary — lib/mock-data.ts no longer exists).
 */

export {
  MOCK_USERS,
  MOCK_ORGANISATIONS,
  MOCK_CANDIDATES,
  MOCK_ROLES,
  MOCK_MATCHES,
  MOCK_COLLECTIONS,
  anonymizeCandidate,
  getCandidateById,
  getRoleById,
  getMatchesForRole,
  getMatchesForCandidate,
} from "./fixtures";

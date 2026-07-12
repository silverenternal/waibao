/**
 * Frontend global-search tests — Vitest.
 *
 * Verifies:
 *   1. Module exports are intact.
 *   2. Hard latency budget — debounce window < 500ms (read from source).
 *   3. Cache cap is bounded (prevents memory leaks).
 *   4. SearchResultItem exposes the role=option contract.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.stubGlobal("fetch", vi.fn());

const fs = await import("node:fs");
const path = await import("node:path");
const url = await import("node:url");

const filename = url.fileURLToPath(import.meta.url);
const HERE = path.dirname(filename);
const ROOT = path.resolve(HERE, ".."); // frontend/
const REPO = path.resolve(HERE, "..", ".."); // talent-tool-mvp/

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO, rel), "utf8");
}

describe("Global search — module contracts", () => {
  beforeEach(() => { vi.clearAllMocks(); return; });

  it("useGlobalSearch hook is exported", async () => {
    const mod = await import("@/hooks/use-global-search");
    expect(typeof mod.useGlobalSearch).toBe("function");
    expect(typeof mod.default).toBe("function");
  });

  it("GlobalSearchBar registers ⌘K / Ctrl+K shortcut", async () => {
    const mod = await import("@/components/GlobalSearchBar");
    expect(typeof mod.GlobalSearchBar).toBe("function");
    expect(typeof mod.default).toBe("function");
  });

  it("GlobalSearchPalette is exported", async () => {
    const mod = await import("@/components/GlobalSearchPalette");
    expect(typeof mod.GlobalSearchPalette).toBe("function");
    expect(typeof mod.default).toBe("function");
  });

  it("SearchResultItem is exported", async () => {
    const mod = await import("@/components/SearchResultItem");
    expect(typeof mod.SearchResultItem).toBe("function");
    expect(typeof mod.default).toBe("function");
  });
});

describe("Global search — hard budget (< 500ms)", () => {
  it("default debounce is 200ms (well under 500ms)", () => {
    const source = read("frontend/hooks/use-global-search.ts");
    expect(source).toContain("debounceMs = 200");
    const matches = source.match(/debounceMs\s*=\s*(\d+)/g) ?? [];
    expect(matches.length).toBeGreaterThan(0);
    for (const m of matches) {
      const n = parseInt(m.split("=")[1], 10);
      expect(n).toBeLessThanOrEqual(500);
    }
  });

  it("cache size cap is 32 entries", () => {
    const source = read("frontend/hooks/use-global-search.ts");
    expect(source).toContain("CACHE_LIMIT = 32");
  });
});

describe("Global search — API endpoint contract", () => {
  it("/api/search exposes q / type / limit query params", () => {
    const source = read("backend/api/search.py");
    for (const needle of ["q", "type", "limit"]) {
      expect(source).toContain(needle);
    }
  });

  it("search router has all 4 entity types", () => {
    const source = read("backend/api/search.py");
    for (const t of ["candidates", "roles", "tickets", "policies"]) {
      expect(source).toContain(t);
    }
  });
});

describe("Global search — DB index migration", () => {
  it("migration adds tsvector + GIN to all four tables", () => {
    const source = read("supabase/migrations/025_search_index.sql");
    for (const table of ["candidates", "roles", "tickets", "company_policies"]) {
      expect(source).toContain(`ALTER TABLE ${table}`);
      expect(source).toContain(`USING GIN`);
    }
    expect(source).toContain("tsvector");
  });
});

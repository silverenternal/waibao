/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    globals: false,
    environment: "node",
    include: ["tests/**/*.spec.ts"],
    // Vitest 4 removed `environmentMatchGlobs` in favor of per-file
    // workspace / `// @vitest-environment happy-dom` pragmas. Project
    // specs have been updated accordingly; the explicit pragmas in
    // tests/test_a11y*.spec.ts and tests/test_search.spec.ts take effect.
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});

/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    globals: false,
    environment: "node",
    include: ["tests/**/*.spec.ts"],
    environmentMatchGlobs: [
      // a11y/scan tests need DOM; everything else stays in node.
      ["tests/test_a11y*.spec.ts", "happy-dom"],
      ["tests/test_search.spec.ts", "happy-dom"],
    ],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});

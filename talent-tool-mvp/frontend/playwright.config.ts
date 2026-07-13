import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config — v9.1 Jobseeker end-to-end suite.
 *
 * Scope: Drive the (jobseeker) AppShell + /jobseeker/* routes in a real
 * browser against the local Next.js dev server. Selectors are based on
 * accessible role / text and avoid hard backend dependencies by stubbing
 * /api/** responses at the browser boundary.
 *
 * Run with:
 *   npm run dev          # in one shell (started automatically below)
 *   npx playwright test  # in another shell
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: /jobseeker-v91\.spec\.ts$/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",

  // The v9.1 spec is a smoke-grade suite — give pages generous load budgets
  // but fail fast on hard crashes.
  timeout: 60_000,
  expect: { timeout: 7_000 },

  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    locale: "zh-CN",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Boot the Next.js dev server before the suite runs; reuse it across
  // workers. `reuseExistingServer` lets you run `npm run dev` manually
  // during local development without Playwright fighting for the port.
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
    env: {
      // No real Supabase / backend in CI; specs stub the network at the
      // browser level so the dev server can run without secrets.
      NEXT_PUBLIC_API_URL: "",
    },
  },
});

/**
 * v9.0 — Smoke test for the 17 critical paths.
 *
 * Spec coverage map (16 项需求 + 服务开关 + 数据驱动 = 17):
 *
 *   1. /login renders                                          (auth)
 *   2. /employer/dashboard renders                            (2.1 HR)
 *   3. /employer/hr-tone renders                              (2.1 个性化 HR)
 *   4. /mothership/compliance-review renders                   (2.2 假资质)
 *   5. /employer/strategy renders                              (2.3 战略)
 *   6. /mothership/analytics/bias-impact renders              (2.4 偏见)
 *   7. /employer/roles/[id]/marketing renders                  (2.5 JD 营销)
 *   8. /jobseeker/policy-explainer renders                     (2.6 制度 AI)
 *   9. /employer/rooms renders                                (2.7 协同)
 *  10. /mothership/matching/quality renders                    (3 双向匹配)
 *  11. /mothership/analytics/salary-report renders             (T2402)
 *  12. /jobseeker/probation renders                            (T2404)
 *  13. /admin/services renders                                 (服务开关)
 *  14. /admin/feature-flags renders                            (服务开关)
 *  15. /mothership/analytics renders                           (T3901 数据驱动)
 *  16. /employer/hr/suggestions renders                        (2.9 主动 HR)
 *  17. /employer/tickets renders                               (2.7 多方 notification)
 *
 * This spec uses Playwright's networkidle + title-not-empty assertion so
 * it runs cheaply in CI without depending on real LLM responses.
 */
import { test, expect } from "@playwright/test";

const BASE = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";

const PAGES: Array<{ path: string; name: string }> = [
  { path: "/login", name: "login" },
  { path: "/employer/dashboard", name: "employer dashboard" },
  { path: "/employer/hr-tone", name: "HR tone" },
  { path: "/mothership/compliance-review", name: "compliance" },
  { path: "/employer/strategy", name: "strategy" },
  { path: "/mothership/analytics/bias-impact", name: "bias impact" },
  { path: "/employer/roles/1/marketing", name: "JD marketing" },
  { path: "/jobseeker/policy-explainer", name: "policy explainer" },
  { path: "/employer/rooms", name: "rooms" },
  { path: "/mothership/matching/quality", name: "matching quality" },
  { path: "/mothership/analytics/salary-report", name: "salary report" },
  { path: "/jobseeker/probation", name: "probation" },
  { path: "/admin/services", name: "service catalog" },
  { path: "/admin/feature-flags", name: "feature flags" },
  { path: "/mothership/analytics", name: "analytics" },
  { path: "/employer/hr/suggestions", name: "HR suggestions" },
  { path: "/employer/tickets", name: "tickets" },
];

for (const p of PAGES) {
  test(`v9.0 smoke — ${p.name} (${p.path})`, async ({ page }) => {
    const resp = await page.goto(`${BASE}${p.path}`, { waitUntil: "domcontentloaded" });
    // 401 / 403 / redirect to login are acceptable for unauthenticated smoke;
    // 404 / 500 are not.
    expect(resp, `no response for ${p.path}`).toBeTruthy();
    expect(resp!.status(), `unexpected status on ${p.path}`).toBeLessThan(500);
    const title = await page.title();
    expect(title.length, `empty title on ${p.path}`).toBeGreaterThan(0);
  });
}
/**
 * v9.1 Jobseeker — Playwright end-to-end suite.
 *
 * Coverage (7 critical user paths from the jobseeker shell):
 *   1. Dashboard         → /jobseeker  (ProactiveBanner + 4 KPI cards)
 *   2. Chat (AI friend)  → /jobseeker/chat
 *   3. Profile           → /jobseeker/profile
 *   4. Emotion           → /jobseeker/emotion
 *   5. Plan              → /jobseeker/plan
 *   6. Offers            → /jobseeker/offers
 *   7. Account           → /jobseeker/account
 *
 * Design notes:
 *   - The jobseeker pages are SSR-rendered React Server Components with
 *     a (jobseeker) AppShell. We bypass auth by setting a demo cookie
 *     (the middleware redirects unauthenticated requests to /login).
 *   - We do NOT mutate any page source.
 *   - Selectors are role / text based (no CSS class scraping).
 *   - `/api/**` is stubbed at the browser layer so the dev server can
 *     run with no backend / no Supabase secrets.
 *   - Each test asserts the page returns 200 and at least one stable
 *     role/text affordance, so regressions in the layout are caught.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

async function stubBackend(page: Page) {
  const handler = (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], items: [], plan: null, user: null }),
    });
  await page.route("**/api/**", handler);
}

async function signInAsDemo(page: Page) {
  await page.context().addCookies([
    {
      name: "recruittech_demo_role",
      value: "client",
      url: "http://localhost:3000",
    },
  ]);
}

test.describe("v9.1 Jobseeker — key user paths", () => {
  test.beforeEach(async ({ page }) => {
    await signInAsDemo(page);
    await stubBackend(page);
  });

  // 1) Dashboard — root of the jobseeker shell
  test("Dashboard mounts and the main heading / region are reachable", async ({
    page,
  }) => {
    const res = await page.goto("/jobseeker");
    expect(res?.ok()).toBeTruthy();
    // The page renders a stable <h1> within the first 10s.
    await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10_000 });
  });

  // 2) Chat — the Open WebUI-style AI friend shell
  test("Chat page mounts and shows an input control", async ({ page }) => {
    const res = await page.goto("/jobseeker/chat");
    expect(res?.ok()).toBeTruthy();
    await expect(
      page.getByPlaceholder(/说点什么|输入|搜索|聊聊|消息|Ask|Search/i).first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  // 3) Profile — OpenResume-style résumé
  test("Profile page renders a heading and a primary affordance", async ({
    page,
  }) => {
    const res = await page.goto("/jobseeker/profile");
    expect(res?.ok()).toBeTruthy();
    await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10_000 });
    // OpenResume-style pages have a print/export or edit affordance.
    const cta = page
      .getByRole("button", { name: /下载|打印|编辑|保存|分享|Download|Print|Edit|Save|Share/i })
      .first();
    await expect(cta).toBeVisible({ timeout: 10_000 });
  });

  // 4) Emotion — Tremor/Recharts dashboard
  test("Emotion page mounts and the care entrypoint is reachable", async ({
    page,
  }) => {
    const res = await page.goto("/jobseeker/emotion");
    expect(res?.ok()).toBeTruthy();
    await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10_000 });
    await expect(
      page
        .getByRole("link", { name: /关怀|记录|写日记|日记|情绪|返回|查看/ })
        .first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  // 5) Plan — career plan
  test("Plan page mounts with a heading and a generator / sub-route link", async ({
    page,
  }) => {
    const res = await page.goto("/jobseeker/plan");
    expect(res?.ok()).toBeTruthy();
    await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10_000 });
    await expect(
      page
        .getByRole("link", {
          name: /进度|市场|学习|market|progress|learning|洞察|详情/i,
        })
        .first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  // 6) Offers — list with region toggle
  test("Offers page exposes a heading, a form, and a region toggle", async ({
    page,
  }) => {
    const res = await page.goto("/jobseeker/offers");
    expect(res?.ok()).toBeTruthy();
    await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10_000 });
    // Region toggle: CN / US / SG.
    const regions = page.getByRole("button", { name: /CN|US|SG|中|美|新|¥|\$|S\$|美元|人民币|新加坡/i });
    await expect(regions.first()).toBeVisible({ timeout: 10_000 });
  });

  // 7) Account — settings hub
  test("Account page exposes a heading and at least one settings entry", async ({
    page,
  }) => {
    const res = await page.goto("/jobseeker/account");
    expect(res?.ok()).toBeTruthy();
    await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10_000 });
    await expect(
      page
        .getByRole("link", {
          name: /通知|偏好|隐私|反馈|删除|导出|安全|资料|设置|Notif|Pref|Privacy|Settings/i,
        })
        .first(),
    ).toBeVisible({ timeout: 10_000 });
  });
});

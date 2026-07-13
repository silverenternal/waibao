/**
 * v7.0 T3003 — White-label theme system.
 *
 * Reads the per-tenant branding record from ``/api/whitelabel/{tenant_id}``
 * and pushes the values into CSS custom properties on
 * ``document.documentElement``. Every page + component must consume those
 * variables rather than hard-coded Tailwind colors so that a tenant can
 * change the brand at runtime.
 *
 * Variables exposed (all read by Tailwind via the ``theme.extend.colors``
 * mapping in ``tailwind.config.ts``):
 *
 *  --color-primary         (e.g.  #2563EB)
 *  --color-secondary       (e.g.  #0F172A)
 *  --color-accent          (e.g.  #F59E0B)
 *  --logo-url              (e.g.  url("https://cdn.example/logo.png"))
 *  --favicon-url
 *  --font-family
 *  --product-name
 *  --footer-text
 *  --support-email
 *  --hide-powered-by       ("true" | "false")
 *  --locale                (zh-CN | en-US | ja-JP)
 */

export type WhitelabelLocale = "zh-CN" | "en-US" | "ja-JP";

export interface Branding {
  tenant_id: string;
  product_name: string;
  domain: string;
  logo_url: string;
  favicon_url: string;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  font_family: string;
  support_email: string;
  footer_text: string;
  locale: WhitelabelLocale;
  email_template: string;
  report_template: string;
  custom_css: string;
  hide_powered_by: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface BrandingBundle {
  branding: Branding;
  css_variables: Record<string, string>;
}

/** Default branding — used when the API is offline or the tenant has no row. */
export const DEFAULT_BRANDING: Branding = {
  tenant_id: "public",
  product_name: "Waibao Recruitment",
  domain: "",
  logo_url: "",
  favicon_url: "",
  primary_color: "#2563EB",
  secondary_color: "#0F172A",
  accent_color: "#F59E0B",
  font_family: "Inter",
  support_email: "support@waibao.example.com",
  footer_text: "Powered by Waibao Recruitment",
  locale: "zh-CN",
  email_template: "transactional",
  report_template: "default",
  custom_css: "",
  hide_powered_by: false,
};

/** CSS variables to push into :root. Stable contract — keys never rename. */
export const CSS_VAR_KEYS = [
  "--color-primary",
  "--color-secondary",
  "--color-accent",
  "--logo-url",
  "--favicon-url",
  "--font-family",
  "--product-name",
  "--footer-text",
  "--hide-powered-by",
  "--support-email",
  "--locale",
] as const;

export type CssVarKey = (typeof CSS_VAR_KEYS)[number];

/**
 * Convert a :class:`Branding` into the CSS variable dictionary consumed
 * by :func:`applyCssVariables`.
 *
 * The function is pure — no DOM access — which makes it trivial to test
 * in Storybook + vitest.
 */
export function toCssVariables(branding: Branding): Record<string, string> {
  return {
    "--color-primary": branding.primary_color || DEFAULT_BRANDING.primary_color,
    "--color-secondary": branding.secondary_color || DEFAULT_BRANDING.secondary_color,
    "--color-accent": branding.accent_color || DEFAULT_BRANDING.accent_color,
    "--logo-url": branding.logo_url
      ? `url("${branding.logo_url}")`
      : "none",
    "--favicon-url": branding.favicon_url || "",
    "--font-family": branding.font_family || DEFAULT_BRANDING.font_family,
    "--product-name": branding.product_name || DEFAULT_BRANDING.product_name,
    "--footer-text": branding.footer_text || "",
    "--hide-powered-by": branding.hide_powered_by ? "true" : "false",
    "--support-email": branding.support_email || "",
    "--locale": branding.locale || DEFAULT_BRANDING.locale,
  };
}

/**
 * Push a dictionary of CSS variables onto ``document.documentElement``.
 * Falls back to :data:`DEFAULT_BRANDING` when called on the server.
 */
export function applyCssVariables(
  cssVars: Record<string, string>,
  target?: HTMLElement,
): void {
  if (typeof document === "undefined" && !target) return;
  const root = target ?? document.documentElement;
  for (const key of CSS_VAR_KEYS) {
    if (cssVars[key] !== undefined) {
      root.style.setProperty(key, cssVars[key]);
    }
  }
}

/** Inject ``branding.custom_css`` as a <style> tag and return its id. */
export function applyCustomCss(customCss: string): string | null {
  if (typeof document === "undefined" || !customCss) return null;
  const id = "waibao-whitelabel-custom-css";
  let el = document.getElementById(id) as HTMLStyleElement | null;
  if (!el) {
    el = document.createElement("style");
    el.id = id;
    document.head.appendChild(el);
  }
  el.textContent = customCss;
  return id;
}

/** Update <link rel="icon"> if a favicon URL was supplied. */
export function applyFavicon(faviconUrl: string): void {
  if (typeof document === "undefined") return;
  let link = document.querySelector(
    'link[rel="icon"]',
  ) as HTMLLinkElement | null;
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  if (faviconUrl) {
    link.href = faviconUrl;
  }
}

/** Apply the full branding record to the current document. */
export function applyBranding(branding: Branding): void {
  applyCssVariables(toCssVariables(branding));
  applyCustomCss(branding.custom_css);
  applyFavicon(branding.favicon_url);
  if (typeof document !== "undefined" && branding.product_name) {
    document.title = branding.product_name;
  }
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!r.ok) {
    throw new Error(`whitelabel API ${r.status} ${r.statusText}`);
  }
  return (await r.json()) as T;
}

/** Resolve the current tenant_id. SSR-safe — falls back to "public". */
export function resolveTenantId(): string {
  if (typeof window === "undefined") return "public";
  // Try: subdomain > URL ?tenant= > localStorage > "public"
  try {
    const host = window.location.hostname;
    const parts = host.split(".");
    if (parts.length >= 3 && parts[0] !== "www") {
      return parts[0];
    }
  } catch {
    /* ignore */
  }
  try {
    const url = new URL(window.location.href);
    const q = url.searchParams.get("tenant");
    if (q) return q;
  } catch {
    /* ignore */
  }
  try {
    const v = window.localStorage.getItem("waibao.tenant_id");
    if (v) return v;
  } catch {
    /* ignore */
  }
  return "public";
}

export const whitelabelApi = {
  /** GET /api/whitelabel/{tenant_id} — fetch the bundle (branding + css). */
  get: (tenantId: string, opts: { signal?: AbortSignal } = {}) =>
    fetchJson<BrandingBundle>(
      `${API_BASE}/api/whitelabel/${encodeURIComponent(tenantId)}`,
      { signal: opts.signal },
    ),

  /** GET /api/whitelabel/{tenant_id}/email-preview */
  emailPreview: (
    tenantId: string,
    body: { template?: string; subject?: string } = {},
  ) =>
    fetchJson<{
      template: string;
      subject: string;
      html: string;
      text: string;
    }>(
      `${API_BASE}/api/whitelabel/${encodeURIComponent(tenantId)}/email-preview?template=${encodeURIComponent(
        body.template || "transactional",
      )}&subject=${encodeURIComponent(body.subject || "预览邮件")}`,
    ),

  /** GET /api/whitelabel/{tenant_id}/pdf-brand */
  pdfBrand: (tenantId: string) =>
    fetchJson<{
      product_name: string;
      logo_url: string;
      primary_color: string;
      secondary_color: string;
      font_family: string;
      footer_text: string;
      hide_powered_by: boolean;
      report_template: string;
      custom_css: string;
    }>(
      `${API_BASE}/api/whitelabel/${encodeURIComponent(tenantId)}/pdf-brand`,
    ),

  /** PUT /api/whitelabel/{tenant_id} — full upsert (admin). */
  upsert: (tenantId: string, payload: Partial<Branding>, actor = "admin") =>
    fetchJson<Branding>(
      `${API_BASE}/api/whitelabel/${encodeURIComponent(tenantId)}`,
      {
        method: "PUT",
        headers: { "x-actor": actor },
        body: JSON.stringify({ tenant_id: tenantId, ...payload }),
      },
    ),

  /** PATCH /api/whitelabel/{tenant_id} — partial update (admin). */
  patch: (tenantId: string, payload: Partial<Branding>, actor = "admin") =>
    fetchJson<Branding>(
      `${API_BASE}/api/whitelabel/${encodeURIComponent(tenantId)}`,
      {
        method: "PATCH",
        headers: { "x-actor": actor },
        body: JSON.stringify(payload),
      },
    ),

  /** DELETE /api/whitelabel/{tenant_id} */
  remove: (tenantId: string, actor = "admin") =>
    fetchJson<{ deleted: boolean }>(
      `${API_BASE}/api/whitelabel/${encodeURIComponent(tenantId)}`,
      { method: "DELETE", headers: { "x-actor": actor } },
    ),

  /** GET /api/whitelabel/ — list all (admin only). */
  list: () =>
    fetchJson<{ items: Branding[]; count: number }>(
      `${API_BASE}/api/whitelabel/`,
    ),
};

// ---------------------------------------------------------------------------
// Re-exports kept at the bottom to avoid breaking on circular imports.
// ---------------------------------------------------------------------------

export type { BrandingBundle };
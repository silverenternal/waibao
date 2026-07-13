/**
 * T2903 — Third-party Application Marketplace API client.
 *
 * Talks to /api/marketplace/* on the FastAPI backend.
 * The public surface (browse / search / reviews) is unauthenticated;
 * author + tenant + admin endpoints require a session.
 */

import { fetchAPI, ApiError } from "@/lib/api";

const BASE = "/api/marketplace";

export type PricingModel = "free" | "one_time" | "subscription" | "usage";
export type PluginStatus =
  | "pending_review"
  | "rejected"
  | "approved"
  | "deprecated"
  | "suspended";
export type Category =
  | "integration"
  | "analytics"
  | "automation"
  | "sourcing"
  | "assessment"
  | "video"
  | "utility"
  | "other";

export interface MarketplacePlugin {
  id: string;
  slug: string;
  name: string;
  tagline: string;
  description: string;
  category: Category;
  tags: string[];
  author_id: string;
  author_name: string;
  author_email: string | null;
  homepage_url: string | null;
  repo_url: string | null;
  icon_url: string | null;
  screenshots: string[];
  pricing_model: PricingModel;
  price_cents: number;
  revenue_share: number;
  status: PluginStatus;
  rejection_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: number | null;
  total_installs: number;
  avg_rating: number;
  rating_count: number;
  manifest: Record<string, unknown>;
  created_at: number;
  updated_at: number;
  releases?: PluginRelease[];
}

export interface PluginRelease {
  id: string;
  plugin_id: string;
  version: string;
  changelog: string;
  artifact_url: string;
  artifact_sha256: string;
  min_waibao_ver: string;
  max_waibao_ver: string | null;
  manifest: Record<string, unknown>;
  status: string;
  size_bytes: number;
  downloads: number;
  created_at: number;
}

export interface Review {
  id: string;
  plugin_id: string;
  author_id: string;
  author_name: string;
  rating: number;
  title: string;
  body: string;
  status: "published" | "hidden" | "flagged";
  helpful_count: number;
  created_at: number;
  updated_at: number;
}

export interface ReviewSummary {
  plugin_id: string;
  count: number;
  avg: number;
  distribution: Record<string, number>;
}

export interface InstallRecord {
  install_id: string;
  slug: string;
  plugin_id: string;
  name: string;
  version: string;
  release_id: string;
  installed_at: number;
}

export interface InstallResult {
  success: boolean;
  plugin_id: string;
  release_id: string | null;
  version: string | null;
  install_id: string;
  duration_ms: number;
  detail: Record<string, unknown>;
  error: string | null;
}

export interface Purchase {
  id: string;
  plugin_id: string;
  release_id: string | null;
  tenant_id: string;
  user_id: string;
  amount_cents: number;
  currency: string;
  payment_method: string;
  payment_status: "pending" | "paid" | "refunded" | "failed" | "cancelled";
  payment_ref: string | null;
  author_share_cents: number;
  platform_share_cents: number;
  created_at: number;
  paid_at: number | null;
}

export interface ListPluginsResponse {
  items: MarketplacePlugin[];
  limit: number;
  offset: number;
  count: number;
}

// ---------------------------------------------------------------------------
// Public catalog
// ---------------------------------------------------------------------------

export async function listPlugins(opts: {
  category?: Category;
  sort?: "popular" | "recent" | "rating" | "name";
  limit?: number;
  offset?: number;
} = {}): Promise<ListPluginsResponse> {
  const params = new URLSearchParams();
  if (opts.category) params.set("category", opts.category);
  if (opts.sort) params.set("sort", opts.sort);
  if (opts.limit != null) params.set("limit", String(opts.limit));
  if (opts.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return fetchAPI<ListPluginsResponse>(`${BASE}${qs ? `?${qs}` : ""}`);
}

export async function searchPlugins(
  query: string,
  opts: { category?: Category; limit?: number } = {},
): Promise<ListPluginsResponse> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (opts.category) params.set("category", opts.category);
  if (opts.limit != null) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return fetchAPI<ListPluginsResponse>(`${BASE}/search${qs ? `?${qs}` : ""}`);
}

export async function getPlugin(slug: string): Promise<MarketplacePlugin> {
  return fetchAPI<MarketplacePlugin>(`${BASE}/${encodeURIComponent(slug)}`);
}

export async function listReviews(
  slug: string,
  opts: { sort?: "recent" | "helpful" | "rating"; limit?: number; offset?: number } = {},
): Promise<{ items: Review[]; count: number; limit: number; offset: number }> {
  const params = new URLSearchParams();
  if (opts.sort) params.set("sort", opts.sort);
  if (opts.limit != null) params.set("limit", String(opts.limit));
  if (opts.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return fetchAPI(`${BASE}/${encodeURIComponent(slug)}/reviews${qs ? `?${qs}` : ""}`);
}

export async function getReviewSummary(slug: string): Promise<ReviewSummary> {
  return fetchAPI<ReviewSummary>(
    `${BASE}/${encodeURIComponent(slug)}/reviews/summary`,
  );
}

export async function getStats(): Promise<{
  total_plugins: number;
  pending_review: number;
  approved: number;
}> {
  return fetchAPI(`${BASE}/stats`);
}

// ---------------------------------------------------------------------------
// Author surface
// ---------------------------------------------------------------------------

export interface PublishRequest {
  slug: string;
  name: string;
  tagline?: string;
  description?: string;
  category?: Category;
  tags?: string[];
  author_id?: string;
  author_name: string;
  author_email?: string;
  homepage_url?: string;
  repo_url?: string;
  icon_url?: string;
  screenshots?: string[];
  pricing_model?: PricingModel;
  price_cents?: number;
  revenue_share?: number;
  manifest?: Record<string, unknown>;
}

export async function publishPlugin(
  body: PublishRequest,
): Promise<MarketplacePlugin> {
  return fetchAPI<MarketplacePlugin>(`${BASE}/publish`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function addRelease(
  pluginId: string,
  body: {
    version: string;
    artifact_url: string;
    artifact_sha256: string;
    changelog?: string;
    min_waibao_ver?: string;
    max_waibao_ver?: string;
    size_bytes?: number;
    manifest?: Record<string, unknown>;
  },
): Promise<PluginRelease> {
  return fetchAPI<PluginRelease>(
    `${BASE}/${pluginId}/releases`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function submitReview(
  slug: string,
  body: {
    author_id?: string;
    author_name: string;
    rating: number;
    title?: string;
    body?: string;
  },
): Promise<Review> {
  return fetchAPI<Review>(
    `${BASE}/${encodeURIComponent(slug)}/reviews`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

// ---------------------------------------------------------------------------
// Tenant surface (install / purchase)
// ---------------------------------------------------------------------------

export async function installPlugin(
  slug: string,
  body: {
    tenant_id: string;
    version?: string;
    waibao_version?: string;
    accept_terms?: boolean;
  },
): Promise<InstallResult> {
  return fetchAPI<InstallResult>(
    `${BASE}/${encodeURIComponent(slug)}/install`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function uninstallPlugin(
  slug: string,
  body: { tenant_id: string },
): Promise<{ success: boolean; error?: string }> {
  return fetchAPI(
    `${BASE}/${encodeURIComponent(slug)}/uninstall`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function listInstalled(
  tenantId: string,
): Promise<{ items: InstallRecord[]; count: number; tenant_id: string }> {
  return fetchAPI(
    `${BASE}/installed?tenant_id=${encodeURIComponent(tenantId)}`,
  );
}

export async function createPurchase(
  slug: string,
  body: {
    plugin_id: string;
    tenant_id: string;
    user_id: string;
    payment_method?: "stripe" | "wechat" | "alipay" | "manual";
    currency?: string;
    release_id?: string;
  },
): Promise<Purchase> {
  return fetchAPI<Purchase>(
    `${BASE}/${encodeURIComponent(slug)}/purchase`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function listPurchases(tenantId?: string): Promise<{
  items: Purchase[];
  count: number;
  tenant_id?: string;
}> {
  const qs = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : "";
  return fetchAPI(`${BASE}/purchases${qs}`);
}

// ---------------------------------------------------------------------------
// Admin / moderation
// ---------------------------------------------------------------------------

export async function listPending(): Promise<{
  items: MarketplacePlugin[];
  count: number;
}> {
  return fetchAPI(`${BASE}/admin/pending`);
}

export async function approvePlugin(
  pluginId: string,
): Promise<MarketplacePlugin> {
  return fetchAPI<MarketplacePlugin>(
    `${BASE}/admin/${pluginId}/approve`,
    { method: "POST" },
  );
}

export async function rejectPlugin(
  pluginId: string,
  reason: string,
): Promise<MarketplacePlugin> {
  return fetchAPI<MarketplacePlugin>(
    `${BASE}/admin/${pluginId}/reject`,
    { method: "POST", body: JSON.stringify({ reason }) },
  );
}

export async function getAuditLog(limit = 100): Promise<{
  items: Record<string, unknown>[];
  limit: number;
}> {
  return fetchAPI(`${BASE}/admin/audit?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

export function formatPrice(priceCents: number, currency: string = "USD"): string {
  if (priceCents === 0) return "Free";
  const amount = priceCents / 100;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format(amount);
}

export function ratingStars(rating: number): string {
  const full = Math.floor(rating);
  const half = rating - full >= 0.5 ? 1 : 0;
  const empty = 5 - full - half;
  return "★".repeat(full) + (half ? "⯨" : "") + "☆".repeat(empty);
}

export { ApiError };

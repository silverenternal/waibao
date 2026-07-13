import type { Metadata } from "next";
import { fetchAPI, ApiError } from "@/lib/api";
import { type MarketplacePlugin } from "@/lib/api-marketplace";
import { PluginDetailClient } from "./_client";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function loadPlugin(slug: string): Promise<MarketplacePlugin | null> {
  try {
    return await fetchAPI<MarketplacePlugin>(
      `${API_BASE}/api/marketplace/${encodeURIComponent(slug)}`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const plugin = await loadPlugin(params.slug);
  if (!plugin) {
    return { title: "Plugin not found — Marketplace" };
  }
  return {
    title: `${plugin.name} — Marketplace`,
    description: plugin.tagline || plugin.description.slice(0, 200),
  };
}

export default async function PluginDetailPage({
  params,
}: {
  params: { slug: string };
}) {
  const initial = await loadPlugin(params.slug);
  return <PluginDetailClient slug={params.slug} initial={initial} />;
}

import type { MetadataRoute } from "next";
import { SITE_NAME } from "@/lib/metadata";

/**
 * manifest.ts — Next App Router PWA manifest endpoint.
 *
 * Generated via MetadataRoute API so Next emits /manifest.webmanifest
 * during build. This file overrides the previously hand-written
 * /public/manifest.json with type-safe config.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE_NAME,
    short_name: "RecruitTech",
    description:
      "AI-powered talent platform: candidate matching, copilot dashboards and multi-persona workflows.",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#1772F6",
    orientation: "portrait",
    lang: "en",
    categories: ["business", "productivity", "utilities"],
    icons: [
      {
        src: "/icons/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/maskable-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icons/maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    screenshots: [
      {
        src: "/screenshots/dashboard.png",
        sizes: "1280x720",
        type: "image/png",
      },
    ],
    shortcuts: [
      { name: "Matches", url: "/match", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Inbox", url: "/my-tickets", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
    related_applications: [],
    prefer_related_applications: false,
  };
}

import { ErrorBoundary } from "@/components/ErrorBoundary";
import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/LegalPage";
import { generatePageMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePageMetadata({
  title: "Cookie Policy",
  description:
    "RecruitTech Cookie Policy — categories of cookies, opt-out controls and per-region cookie consent rules.",
  path: "/legal/cookies",
});

export default function CookiesPage() {
  return <ErrorBoundary><LegalPage docType="cookies" title="Cookie Policy / Cookie 政策 / Cookie ポリシー" /></ErrorBoundary>;
}

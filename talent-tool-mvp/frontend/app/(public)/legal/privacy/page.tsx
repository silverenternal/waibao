import { ErrorBoundary } from "@/components/ErrorBoundary";
import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/LegalPage";
import { generatePageMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePageMetadata({
  title: "Privacy Policy",
  description:
    "RecruitTech Privacy Policy — how we collect, process, store and protect personal data in compliance with GDPR, UK GDPR, PIPL and APPI.",
  path: "/legal/privacy",
});

export default function PrivacyPage() {
  return <ErrorBoundary><LegalPage docType="privacy" title="Privacy Policy / 隐私政策 / プライバシーポリシー" /></ErrorBoundary>;
}

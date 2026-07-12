import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/LegalPage";
import { generatePageMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePageMetadata({
  title: "Terms of Service",
  description:
    "RecruitTech Terms of Service — usage rights, billing, uptime commitments, liability and termination clauses.",
  path: "/legal/terms",
});

export default function TermsPage() {
  return <LegalPage docType="terms" title="Terms of Service / 服务条款 / 利用規約" />;
}

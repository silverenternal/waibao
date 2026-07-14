import { ErrorBoundary } from "@/components/ErrorBoundary";
import type { Metadata } from "next";
import { LegalPage } from "@/components/legal/LegalPage";
import { generatePageMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePageMetadata({
  title: "Data Processing Agreement",
  description:
    "RecruitTech Data Processing Agreement — GDPR Article 28 controller-processor terms, SCCs and sub-processor disclosures.",
  path: "/legal/dpa",
});

export default function DpaPage() {
  return <ErrorBoundary><LegalPage docType="dpa" title="Data Processing Agreement / 数据处理协议 / データ処理契約" /></ErrorBoundary>;
}

import type { Metadata } from "next";
import { generatePrivacyMetadata } from "@/lib/metadata";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { IdentityPageClient } from "./_client";

export const metadata: Metadata = generatePrivacyMetadata(
  "身份验证与档案版本 · Jobseeker Workspace",
);

export default function JobseekerIdentityPage() {
  return (
    <ErrorBoundary>
      <IdentityPageClient />
    </ErrorBoundary>
  );
}

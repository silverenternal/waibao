import type { Metadata } from "next";
import { generatePrivacyMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePrivacyMetadata('Refer · Jobseeker Workspace');

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

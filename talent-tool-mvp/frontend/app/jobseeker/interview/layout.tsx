import type { Metadata } from "next";
import { generatePrivacyMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePrivacyMetadata('Interview · Jobseeker Workspace');

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

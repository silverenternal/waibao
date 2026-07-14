import type { Metadata } from "next";
import { generatePrivacyMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePrivacyMetadata('Dashboard · Employer Workspace');

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

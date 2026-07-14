import type { Metadata } from "next";
import { generatePrivacyMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePrivacyMetadata('Dashboard · Hiring Manager Console');

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

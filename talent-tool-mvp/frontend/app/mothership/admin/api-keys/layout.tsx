import type { Metadata } from "next";
import { generatePrivacyMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePrivacyMetadata('Api Keys · Talent Partner Console');

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

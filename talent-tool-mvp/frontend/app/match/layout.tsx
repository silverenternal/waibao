import type { Metadata } from "next";
import { generatePrivacyMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePrivacyMetadata("Match Workspace");

export default function MatchLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}

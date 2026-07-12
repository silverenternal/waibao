import type { Metadata } from "next";
import { generatePrivacyMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePrivacyMetadata("Jobseeker Workspace");

export default function JobseekerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}

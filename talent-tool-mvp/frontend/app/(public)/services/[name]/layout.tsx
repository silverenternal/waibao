import type { Metadata } from "next";
import { generatePageMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePageMetadata({
  title: 'Name · Workspace',
  path: '/services/[name]',
});

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

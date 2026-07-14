import type { Metadata } from "next";
import { generatePageMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePageMetadata({
  title: 'Services · Workspace',
  path: '/services',
});

export default function PageLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

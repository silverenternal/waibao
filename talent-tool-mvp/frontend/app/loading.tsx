import { PageLoader } from "@/components/shared/PageLoader";

/**
 * T5006 — Root loading state. Rendered by Next.js while any top-level
 * route segment is loading.
 */
export default function Loading() {
  return <PageLoader variant="dashboard" />;
}

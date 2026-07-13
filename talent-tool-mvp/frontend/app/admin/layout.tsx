/**
 * Admin layout — wraps the Refine provider around admin pages.
 *
 * The Refine provider exposes:
 *   - DataProvider for CRUD
 *   - AuthProvider (Supabase JWT)
 *   - i18nProvider (zh-CN / en-US / ja-JP)
 *   - Resources registry (users / services / tickets / feedback / ...)
 *   - Standard notification hooks (`useNotificationProvider`)
 *
 * Layout also widens the nav to include the new admin resources
 * (tickets / feedback / pilot / insights).
 */

import * as React from "react";
import {
  Activity,
  Blocks,
  Flag,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  UsersRound,
  Workflow,
  Ticket,
  MessageSquare,
  Rocket,
  BarChart3,
} from "lucide-react";
import { AppShell } from "@/components/shared/AppShell";
import { RefineAdminProvider } from "@/lib/admin";

const NAV = [
  { label: "Overview", href: "/admin", icon: LayoutDashboard },
  { label: "Services", href: "/admin/services", icon: Blocks },
  { label: "Users", href: "/admin/users", icon: UsersRound },
  { label: "Feature flags", href: "/admin/feature-flags", icon: Flag },
  { label: "Workflows", href: "/admin/workflows", icon: Workflow },
  { label: "Tickets", href: "/admin/tickets", icon: Ticket },
  { label: "Feedback", href: "/admin/feedback", icon: MessageSquare },
  { label: "Pilot", href: "/admin/pilot", icon: Rocket },
  { label: "Insights", href: "/admin/insights", icon: BarChart3 },
  { label: "Observability", href: "/admin/insights", icon: Activity },
  { label: "Audit", href: "/admin/audit", icon: ShieldCheck },
  { label: "Configuration", href: "/admin/config", icon: Settings },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RefineAdminProvider basePath="/admin">
      <AppShell title="waibao Admin" nav={NAV} admin>
        {children}
      </AppShell>
    </RefineAdminProvider>
  );
}

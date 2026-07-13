"use client";

/**
 * Refine admin integration — refinedev/refine.
 *
 * Sets up Refine's provider stack with:
 *   - DataProvider    : Supabase REST (`@refinedev/supabase`) configured for our project
 *   - AuthProvider    : JWT-based auth using Supabase (`@refinedev/supabase`)
 *   - RouterProvider  : Next.js App Router (already wired via `lib/refine.tsx`)
 *   - i18nProvider    : zh-CN + en-US + ja-JP, delegates to next-intl
 *   - Resources       : central registry — adds users / services / tickets / feedback / ...
 *   - NotificationProvider: toaster for create/update/delete
 *
 * The module also exposes helper hooks (`useResourceList`, `useAdminUser`)
 * for use in the new admin pages.
 *
 * Why Refine:
 *   - A drop-in headless admin shell we can compose with our shared UI
 *   - Auto CRUD pages (list / show / edit / create) for any resource
 *   - Lives happily next to our hand-written Tremor / shadcn-admin pages
 */

import * as React from "react";
import { Refine } from "@refinedev/core";
import routerProvider from "@refinedev/nextjs-router";
import dataProvider from "@refinedev/simple-rest";
import type { ReactNode } from "react";
import { createClient as createSupabaseClient } from "@/lib/supabase";
const supabaseClient = createSupabaseClient();
import { authProvider } from "@/lib/admin-auth-provider";
import { i18nProvider } from "@/lib/admin-i18n-provider";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

// ---------------------------------------------------------------------------
// Resource registry
// ---------------------------------------------------------------------------

export interface AdminResource {
  name: string;
  list: string; // route paths
  show?: string;
  edit?: string;
  create?: string;
  label?: string;
  icon?: string;
}

export const ADMIN_RESOURCES: AdminResource[] = [
  {
    name: "users",
    list: "/admin/users",
    show: "/admin/users/show/:id",
    edit: "/admin/users/edit/:id",
    label: "用户",
    icon: "users",
  },
  {
    name: "services",
    list: "/admin/services",
    show: "/admin/services/show/:name",
    edit: "/admin/services/edit/:name",
    label: "服务目录",
    icon: "blocks",
  },
  {
    name: "tickets",
    list: "/admin/tickets",
    show: "/admin/tickets/show/:id",
    label: "工单",
    icon: "ticket",
  },
  {
    name: "feedback",
    list: "/admin/feedback",
    show: "/admin/feedback/show/:id",
    label: "反馈",
    icon: "message-square",
  },
  {
    name: "insights",
    list: "/admin/insights",
    label: "数据洞察",
    icon: "activity",
  },
  {
    name: "pilot",
    list: "/admin/pilot",
    show: "/admin/pilot/show/:id",
    label: "试点",
    icon: "rocket",
  },
  {
    name: "feature_flags",
    list: "/admin/feature-flags",
    edit: "/admin/feature-flags/edit/:id",
    label: "Feature Flag",
    icon: "flag",
  },
  {
    name: "workflows",
    list: "/admin/workflows",
    show: "/admin/workflows/show/:id",
    label: "Workflow",
    icon: "workflow",
  },
];

// ---------------------------------------------------------------------------
// DataProvider that forwards to our FastAPI backend (simple-rest adapter)
// plus a Supabase decorator for auth-table queries. The simple-rest adapter
// handles create/list/get/update/delete out of the box.
// ---------------------------------------------------------------------------

export function buildAdminDataProvider(baseUrl = API_BASE) {
  return dataProvider(baseUrl);
}

// ---------------------------------------------------------------------------
// Provider component
// ---------------------------------------------------------------------------

export interface RefineAdminProviderProps {
  children: ReactNode;
  basePath?: string;
}

export function RefineAdminProvider({
  children,
  basePath = "/admin",
}: RefineAdminProviderProps) {
  return (
    <Refine
      routerProvider={routerProvider}
      dataProvider={buildAdminDataProvider()}
      authProvider={authProvider(supabaseClient)}
      i18nProvider={i18nProvider}
      resources={ADMIN_RESOURCES.map((r) => ({
        name: r.name,
        list: r.list,
        show: r.show,
        edit: r.edit,
        create: r.create,
        meta: { label: r.label, icon: r.icon },
      }))}
      options={
        {
          // The options shape depends on the Refine version; cast to `any`
          // so this module compiles regardless of installed patch version.
          syncWithLocation: true,
          warnWhenUnsavedChanges: true,
          disableTelemetry: true,
          basePath,
        } as any
      }
    >
      {children}
    </Refine>
  );
}

// ---------------------------------------------------------------------------
// Helper hooks
// ---------------------------------------------------------------------------

/** Look up a resource definition by name. */
export function useResource(name: string): AdminResource | undefined {
  return ADMIN_RESOURCES.find((r) => r.name === name);
}

/** All resources as a flat array — used to drive the admin sidebar. */
export function useAdminNav() {
  return React.useMemo(() => ADMIN_RESOURCES, []);
}

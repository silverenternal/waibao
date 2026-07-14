"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Admin Service Catalog — v8.0 T3501 with shadcn-admin polish.
 *
 * Uses our shared ResourceTable (Refine-aware) with sortable / filterable
 * columns, status KPI row up top, and a status toggle quick action per row.
 */

import * as React from "react";
import Link from "next/link";
import { useServiceCatalog } from "@/hooks/use-service-toggle";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RefreshCw, PlusCircle, Blocks } from "lucide-react";
import {
  ResourceTable,
  ResourceRowLink,
} from "@/components/admin/ResourceTable";
import type { ColumnDef } from "@tanstack/react-table";

interface CatalogItem {
  name: string;
  display_name: string;
  description?: string;
  category: string;
  status: string;
  plan_required: string;
  roles_allowed: string[];
  dependencies?: string[];
  available?: boolean;
}

const CATEGORY_LABELS: Record<string, string> = {
  agent: "Agent",
  api: "API",
  business: "Business",
  integration: "Integration",
  platform: "Platform",
  frontend: "Frontend",
  analytics: "Analytics",
  misc: "Misc",
};

const STATUS_STYLE: Record<string, string> = {
  enabled: "bg-emerald-500/15 text-emerald-700",
  disabled: "bg-rose-500/15 text-rose-700",
  maintenance: "bg-amber-500/15 text-amber-700",
  beta: "bg-blue-500/15 text-blue-700",
};

const STATUS_LABEL: Record<string, string> = {
  enabled: "启用",
  disabled: "禁用",
  maintenance: "维护",
  beta: "Beta",
};

export default function AdminServicesPage() {
  const [plan, setPlan] = React.useState("free");
  const [role, setRole] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [category, setCategory] = React.useState<string>("all");
  const { data, isLoading, refetch } = useServiceCatalog(plan, role);

  const items: CatalogItem[] = React.useMemo(() => {
    const rows = (data ?? []) as CatalogItem[];
    return rows.filter((row) => {
      if (
        search &&
        !row.name.toLowerCase().includes(search.toLowerCase()) &&
        !(row.display_name ?? "").toLowerCase().includes(search.toLowerCase())
      )
        return false;
      if (category !== "all" && row.category !== category) return false;
      return true;
    });
  }, [data, search, category]);

  const totals = React.useMemo(() => {
    const all = (data ?? []) as CatalogItem[];
    const by: Record<string, number> = {};
    for (const r of all) by[r.status] = (by[r.status] ?? 0) + 1;
    return { total: all.length, by };
  }, [data]);

  const columns: ColumnDef<CatalogItem>[] = React.useMemo(
    () => [
      {
        id: "name",
        header: "Name",
        cell: ({ row }) => (
          <ResourceRowLink href={`/admin/services/${encodeURIComponent(row.original.name)}`}>
            <span className="font-mono text-xs">{row.original.name}</span>
          </ResourceRowLink>
        ),
      },
      {
        id: "display",
        header: "Display",
        cell: ({ row }) => row.original.display_name ?? row.original.name,
      },
      {
        id: "category",
        header: "Category",
        cell: ({ row }) => (
          <Badge variant="outline">
            {CATEGORY_LABELS[row.original.category] ?? row.original.category}
          </Badge>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: ({ row }) => {
          const s = row.original.status;
          return (
            <span
              className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                STATUS_STYLE[s] ?? STATUS_STYLE.disabled
              }`}
            >
              {STATUS_LABEL[s] ?? s}
            </span>
          );
        },
      },
      {
        id: "plan",
        header: "Plan",
        cell: ({ row }) => (
          <span className="text-xs uppercase">{row.original.plan_required}</span>
        ),
      },
      {
        id: "roles",
        header: "Roles",
        cell: ({ row }) =>
          row.original.roles_allowed?.length ? row.original.roles_allowed.join(", ") : "any",
      },
      {
        id: "deps",
        header: "Deps",
        cell: ({ row }) => (
          <span className="text-xs tabular-nums">
            {(row.original.dependencies ?? []).length}
          </span>
        ),
      },
    ],
    [],
  );

  return (
    <ErrorBoundary>(<div className="space-y-6 p-4 md:p-8">
        <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Blocks className="h-5 w-5 text-primary" />
              <h1 className="text-2xl font-bold tracking-tight md:text-3xl">Service Catalog</h1>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              v8.0 T3501 · {totals.total} registered services
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => refetch()}>
              <RefreshCw className="mr-1 h-4 w-4" /> 刷新
            </Button>
            <Button>
              <PlusCircle className="mr-1 h-4 w-4" /> 新服务
            </Button>
          </div>
        </header>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Object.entries(STATUS_LABEL).map(([s, label]) => (
            <Card key={s} className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {label}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs ${
                    STATUS_STYLE[s] ?? "bg-muted"
                  }`}
                >
                  {s}
                </span>
              </div>
              <div className="mt-2 text-2xl font-bold tabular-nums">{totals.by[s] ?? 0}</div>
            </Card>
          ))}
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">筛选</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <Input
              placeholder="搜索服务..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Select value={plan} onValueChange={(v) => v && setPlan(v)}>
              <SelectTrigger><SelectValue placeholder="Plan" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="free">Free</SelectItem>
                <SelectItem value="pro">Pro</SelectItem>
                <SelectItem value="enterprise">Enterprise</SelectItem>
                <SelectItem value="internal">Internal</SelectItem>
              </SelectContent>
            </Select>
            <Select value={role} onValueChange={(v) => v && setRole(v)}>
              <SelectTrigger><SelectValue placeholder="Role" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">Any role</SelectItem>
                <SelectItem value="jobseeker">Jobseeker</SelectItem>
                <SelectItem value="employer">Employer</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
            <Select value={category} onValueChange={(v) => v && setCategory(v)}>
              <SelectTrigger><SelectValue placeholder="Category" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <ResourceTable<CatalogItem>
              data={items}
              columns={columns}
              resource="services"
              searchPlaceholder="按服务名筛选..."
              pageSize={10}
              getRowId={(row) => row.name}
              onRowClick={(row) => {
                if (typeof window !== "undefined")
                  window.location.href = `/admin/services/${encodeURIComponent(row.name)}`;
              }}
            />
          </CardContent>
        </Card>
        <p className="text-xs text-muted-foreground">
          {isLoading ? "加载中..." : `显示 ${items.length} 条`}
        </p>
      </div>)</ErrorBoundary>
  );
}

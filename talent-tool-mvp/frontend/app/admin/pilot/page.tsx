"use client";

/**
 * T1702 — /admin/pilot 管理面板.
 *
 * - 列出全部 pilot 项目
 * - KPI 概览 (active / completed / total)
 * - 点击项目跳转到 /admin/pilot/[id]
 */

import * as React from "react";
import { useRouter } from "next/navigation";

import { AdminDashboard } from "@/components/pilot/AdminDashboard";

export default function AdminPilotPage() {
  const router = useRouter();

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Pilot 管理</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理试用项目、邀请用户、查看 NPS / 周活 / 痛点报告.
        </p>
      </header>

      <AdminDashboard
        onSelect={(id) => router.push(`/admin/pilot/${id}`)}
      />
    </main>
  );
}
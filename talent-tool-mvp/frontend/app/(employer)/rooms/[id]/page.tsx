"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Single room view — same shell, but URL-driven room selection.
 * (Mirrors /employer/rooms but uses params.id for the active room.)
 */

import * as React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";

const RoomsView = dynamic(() => import("../page"), { ssr: false });

export default function RoomDetailPage({ params }: { params: { id: string } }) {
  // For brevity we just render the list-view; in production we would lift
  // the active room into context keyed by params.id. Done so the URL is
  // shareable while we keep one source of truth.
  return (
    <ErrorBoundary>(<div className="space-y-2 p-3 md:p-6">
        <Button variant="ghost" size="sm" asChild className="-ml-2">
          <Link href="/employer/rooms">
            <ChevronLeft className="mr-1 h-4 w-4" /> 全部空间
          </Link>
        </Button>
        <p className="text-xs text-muted-foreground">
          正在打开空间 <span className="font-mono">{params.id}</span> — 切到主视图。
        </p>
        <RoomsView />
      </div>)</ErrorBoundary>
  );
}

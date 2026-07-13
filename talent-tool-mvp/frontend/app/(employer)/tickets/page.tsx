"use client";

/**
 * Tickets Kanban — v8.1 + shadcn-ui dashboard pattern.
 *
 * Three-column board (Open · In Progress · Resolved), drag-and-drop columns,
 * filter bar at the top. Mobile: columns become vertical cards, accessible
 * via a horizontal scroll snap; on very small screens, columns stack.
 */

import * as React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PlusCircle, Search } from "lucide-react";

const TicketBoard = dynamic(
  () => import("@/components/tickets/TicketBoard").then((m) => m.TicketBoard),
  { ssr: false },
);

export default function TicketsPage() {
  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">工单 · Tickets</h1>
          <p className="text-sm text-muted-foreground">
            v8.1 T3709 · HR 主动建议一条转工单，看板管理
          </p>
        </div>
        <Button>
          <PlusCircle className="mr-1 h-4 w-4" />
          新建工单
        </Button>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">筛选</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <div className="relative w-full md:w-64">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="搜索工单..." className="pl-9" />
          </div>
          <Select defaultValue="all">
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部优先级</SelectItem>
              <SelectItem value="p0">P0</SelectItem>
              <SelectItem value="p1">P1</SelectItem>
              <SelectItem value="p2">P2</SelectItem>
            </SelectContent>
          </Select>
          <Select defaultValue="all">
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部标签</SelectItem>
              <SelectItem value="compliance">合规</SelectItem>
              <SelectItem value="interview">面试</SelectItem>
              <SelectItem value="offer">Offer</SelectItem>
              <SelectItem value="onboarding">入职</SelectItem>
            </SelectContent>
          </Select>
          <Badge variant="secondary">共 12 张工单</Badge>
        </CardContent>
      </Card>

      <TicketBoard tickets={[]} />
    </div>
  );
}

"use client";

/**
 * T2303 — 一键导出按钮
 * 支持 docx/pptx/pdf 三种格式的下拉菜单.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Download, FileText, Presentation, FileType, Loader2 } from "lucide-react";

type ExportKind = "candidate" | "funnel" | "sla" | "weekly" | "monthly";

interface ExportButtonProps {
  kind: ExportKind;
  /** 候选人/岗位 ID (candidate 必填) */
  id?: string;
  /** 时间窗口 (funnel/sla 必填) */
  periodDays?: number;
  /** 周/月偏移 (weekly/monthly 可选) */
  offset?: number;
  variant?: "default" | "outline" | "ghost";
  size?: "default" | "sm" | "lg";
  label?: string;
  className?: string;
}

const ENDPOINTS: Record<ExportKind, string> = {
  candidate: "/api/exports/candidate-report",
  funnel: "/api/exports/funnel-report",
  sla: "/api/exports/sla-report",
  weekly: "/api/exports/weekly",
  monthly: "/api/exports/monthly",
};

const FORMAT_ICONS = {
  docx: FileText,
  pptx: Presentation,
  pdf: FileType,
} as const;

const FORMAT_LABELS = {
  docx: "Word 文档 (.docx)",
  pptx: "PowerPoint (.pptx)",
  pdf: "PDF (.pdf)",
} as const;

export function ExportButton({
  kind,
  id,
  periodDays = 30,
  offset = 0,
  variant = "outline",
  size = "sm",
  label = "导出",
  className,
}: ExportButtonProps) {
  const [loading, setLoading] = useState<string | null>(null);

  async function handleExport(format: "docx" | "pptx" | "pdf") {
    setLoading(format);
    try {
      let url = ENDPOINTS[kind];
      const params = new URLSearchParams();
      params.set("format", format);

      if (kind === "candidate") {
        if (!id) return;
        url = `${url}/${id}`;
      } else if (kind === "funnel" || kind === "sla") {
        params.set("period_days", String(periodDays));
      } else if (kind === "weekly") {
        params.set("week_offset", String(offset));
      } else if (kind === "monthly") {
        params.set("month_offset", String(offset));
      }

      const token = typeof window !== "undefined"
        ? window.sessionStorage.getItem("sb-access-token") || ""
        : "";
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "";

      const res = await fetch(`${apiBase}${url}?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: "include",
      });
      if (!res.ok) {
        throw new Error(`导出失败: ${res.status}`);
      }
      // 触发下载
      const blob = await res.blob();
      const filename = `${kind}-report.${format}`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      console.error(e);
      alert(e instanceof Error ? e.message : "导出失败");
    } finally {
      setLoading(null);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant={variant} size={size} className={className}>
          {loading ? (
            <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
          ) : (
            <Download className="w-4 h-4 mr-1.5" />
          )}
          {label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel>选择格式</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(Object.keys(FORMAT_LABELS) as Array<keyof typeof FORMAT_LABELS>).map(
          (fmt) => {
            const Icon = FORMAT_ICONS[fmt];
            return (
              <DropdownMenuItem
                key={fmt}
                onSelect={() => handleExport(fmt)}
                disabled={loading !== null}
              >
                <Icon className="w-4 h-4 mr-2" />
                {FORMAT_LABELS[fmt]}
              </DropdownMenuItem>
            );
          }
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
"use client";

/**
 * JDVersionHistory (T604)
 *
 * Sidebar list of past JD edits for the current role. Each row shows:
 *   - version_no + creation time
 *   - description preview
 *   - over_spec_flags count badge
 *
 * Clicking a version sets `selectedId` which the parent uses to open the
 * diff viewer (`JDVersionDiff`).
 *
 * Backend storage: `role_jd_versions` table (planned migration 008). For
 * T604 the api-jd helper returns `[]` when the endpoint is missing — the
 * card just hides itself in that case so editors keep working.
 */

import * as React from "react";
import {
  History,
  GitCommit,
  Clock3,
  AlertTriangle,
  Eye,
  Loader2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

import { jdApi, type JDVersion } from "@/lib/api-jd";

export interface JDVersionHistoryProps {
  roleId: string;
  /** Currently selected version (controlled). */
  selectedId?: string | null;
  onSelect?: (version: JDVersion) => void;
  className?: string;
}

export function JDVersionHistory({
  roleId,
  selectedId,
  onSelect,
  className,
}: JDVersionHistoryProps) {
  const [versions, setVersions] = React.useState<JDVersion[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [hidden, setHidden] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!roleId) return;
    setLoading(true);
    try {
      const list = await jdApi.versions(roleId);
      setVersions(list);
      // If the backend doesn't expose the endpoint the helper returns [].
      if (list.length === 0) setHidden(true);
    } catch {
      setHidden(true);
    } finally {
      setLoading(false);
    }
  }, [roleId]);

  React.useEffect(() => {
    void load();
  }, [load]);

  if (hidden && !loading) return null;

  return (
    <Card className={cn(className)}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <History className="size-4 text-slate-500" />
          修订历史
          {!loading && (
            <Badge variant="outline" className="ml-auto text-[10px]">
              {versions.length} 个版本
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading ? (
          <ul className="space-y-1.5">
            {Array.from({ length: 3 }).map((_, i) => (
              <li key={i}>
                <Skeleton className="h-14 w-full" />
              </li>
            ))}
          </ul>
        ) : versions.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-center text-xs text-slate-500">
            还没有保存的版本历史。保存一次草稿后会自动记录。
          </p>
        ) : (
          <ul className="space-y-1.5">
            {versions.map((v) => (
              <li key={v.id}>
                <button
                  type="button"
                  onClick={() => onSelect?.(v)}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-md border bg-white p-2 text-left transition",
                    selectedId === v.id
                      ? "border-blue-500 ring-2 ring-blue-100"
                      : "border-slate-200 hover:border-blue-300 hover:bg-blue-50/30",
                  )}
                >
                  <GitCommit className="mt-0.5 size-4 shrink-0 text-blue-500" />
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-semibold text-slate-800">
                        v{v.version_no}
                      </span>
                      {(v.over_spec_flags ?? []).length > 0 && (
                        <Badge variant="outline" className="border-amber-300 bg-amber-50 text-[10px] text-amber-700">
                          <AlertTriangle className="mr-1 size-3" />
                          {v.over_spec_flags.length} 项提示
                        </Badge>
                      )}
                      <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-slate-400">
                        <Clock3 className="size-3" />
                        {new Date(v.created_at).toLocaleString("en-GB", {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </span>
                    </div>
                    <p className="line-clamp-2 text-[11px] text-slate-600">
                      {v.description}
                    </p>
                  </div>
                  <Eye className="size-3.5 shrink-0 text-slate-400" />
                </button>
              </li>
            ))}
          </ul>
        )}
        {!loading && versions.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full"
            onClick={() => void load()}
          >
            <Loader2 className="mr-1 hidden size-3" />
            刷新历史
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

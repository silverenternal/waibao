"use client";

/**
 * v11.2 T6303 — Profile version history.
 *
 * Lists all saved profile versions (newest-first) from
 * GET /api/identity/profile/versions. Clicking a version fetches its snapshot
 * (GET /profile/versions/{n}) and shows a preview; 恢复到此版本 does a
 * PUT /profile with that snapshot — the backend appends a NEW version (增量,
 * never deletes previous versions) and returns the new version_no.
 */

import * as React from "react";
import { History, Loader2, RotateCcw, FileText, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  fetchProfileVersion,
  fetchProfileVersions,
  updateProfile,
  type ProfileVersionMeta,
  type StructuredProfile,
} from "@/lib/api-identity";

export interface ProfileVersionHistoryProps {
  /**
   * Called after a successful 恢复到此版本: receives the new version_no and
   * the restored snapshot so the parent can refresh the editable form.
   */
  onRestored?: (versionNo: number, snapshot: StructuredProfile) => void;
  /** Bump this to force a refetch (e.g. after a profile save). */
  refreshKey?: number;
}

export function ProfileVersionHistory({
  onRestored,
  refreshKey = 0,
}: ProfileVersionHistoryProps) {
  const [versions, setVersions] = React.useState<ProfileVersionMeta[] | null>(
    null,
  );
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<ProfileVersionMeta | null>(
    null,
  );

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchProfileVersions();
      setVersions(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载版本历史失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="size-4 text-slate-500" />
          画像版本历史
        </CardTitle>
        <CardDescription>
          每次保存都会生成一个新版本(增量,历史版本不会被删除)。可预览并恢复到任意历史版本。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
            {error}
            <Button
              variant="link"
              size="sm"
              className="ml-2 h-auto p-0"
              onClick={() => void load()}
            >
              重试
            </Button>
          </div>
        ) : loading && !versions ? (
          <VersionSkeleton />
        ) : versions && versions.length > 0 ? (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {versions.map((v) => (
              <VersionRow
                key={v.version_no}
                meta={v}
                isSelected={selected?.version_no === v.version_no}
                onSelect={() =>
                  setSelected((cur) =>
                    cur?.version_no === v.version_no ? null : v,
                  )
                }
                onRestored={onRestored}
              />
            ))}
          </ul>
        ) : (
          <p className="py-6 text-center text-sm text-slate-500 dark:text-slate-400">
            还没有保存过任何版本。编辑下方档案并保存即可生成第一个版本。
          </p>
        )}
      </CardContent>

      {selected && (
        <VersionPreview
          meta={selected}
          onClose={() => setSelected(null)}
          onRestored={(versionNo, snapshot) => {
            onRestored?.(versionNo, snapshot);
            setSelected(null);
            void load();
          }}
        />
      )}
    </Card>
  );
}

function VersionRow({
  meta,
  isSelected,
  onSelect,
  onRestored,
}: {
  meta: ProfileVersionMeta;
  isSelected: boolean;
  onSelect: () => void;
  onRestored?: (versionNo: number, snapshot: StructuredProfile) => void;
}) {
  return (
    <li className="flex items-center justify-between gap-3 py-2.5">
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={isSelected}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
          "min-h-11 sm:min-h-0",
          isSelected
            ? "bg-slate-100 dark:bg-slate-800"
            : "hover:bg-slate-50 dark:hover:bg-slate-800/50",
        )}
      >
        <FileText className="size-4 shrink-0 text-slate-400" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-slate-900 dark:text-slate-100">
            版本 {meta.version_no}
          </span>
          <span className="block truncate text-xs text-slate-500 dark:text-slate-400">
            {meta.created_at
              ? formatDateTime(meta.created_at)
              : "保存时间未知"}
          </span>
        </span>
      </button>
      {isSelected && (
        <span className="shrink-0 text-xs font-medium text-slate-400">
          已选中
        </span>
      )}
    </li>
  );
}

function VersionPreview({
  meta,
  onClose,
  onRestored,
}: {
  meta: ProfileVersionMeta;
  onClose: () => void;
  onRestored?: (versionNo: number, snapshot: StructuredProfile) => void;
}) {
  const [snapshot, setSnapshot] = React.useState<StructuredProfile | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [restoring, setRestoring] = React.useState(false);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchProfileVersion(meta.version_no)
      .then((snap) => {
        if (active) setSnapshot(snap);
      })
      .catch((e) => {
        if (active)
          setError(e instanceof Error ? e.message : "加载版本快照失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [meta.version_no]);

  async function handleRestore() {
    if (!snapshot) return;
    setRestoring(true);
    try {
      const res = await updateProfile(snapshot);
      toast.success(`已恢复到版本 ${meta.version_no}(新版本 ${res.version_no})`);
      onRestored?.(res.version_no, res.profile ?? snapshot);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "恢复失败";
      setError(msg);
      toast.error(msg);
    } finally {
      setRestoring(false);
    }
  }

  return (
    <div className="border-t border-slate-100 bg-slate-50/60 px-6 py-4 dark:border-slate-800 dark:bg-slate-900/40">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          版本 {meta.version_no} 预览
        </h4>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={onClose}
          aria-label="关闭预览"
        >
          <X className="size-4" />
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
          <Loader2 className="size-4 animate-spin" />
          加载快照…
        </div>
      ) : error ? (
        <p className="py-2 text-sm text-rose-600 dark:text-rose-400" role="alert">
          {error}
        </p>
      ) : (
        <SnapshotPreview snapshot={snapshot} />
      )}

      <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onClose} disabled={restoring}>
          取消
        </Button>
        <Button
          size="sm"
          onClick={handleRestore}
          disabled={restoring || loading || !snapshot}
          className="h-11 sm:h-9"
        >
          {restoring ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RotateCcw className="size-4" />
          )}
          恢复到此版本
        </Button>
      </div>
    </div>
  );
}

function SnapshotPreview({ snapshot }: { snapshot: StructuredProfile | null }) {
  if (!snapshot) return null;
  const skills = Array.isArray(snapshot.skills) ? snapshot.skills : [];
  const rows: Array<[string, React.ReactNode]> = [
    ["姓名", snapshot.name || "—"],
    ["职位", snapshot.title || "—"],
    ["城市", snapshot.city || "—"],
    ["学历", snapshot.education || "—"],
    ["工作经历", snapshot.experience || "—"],
    ["期望薪资", snapshot.expected_salary || "—"],
    [
      "五险一金",
      snapshot.social_insurance_expectation ? "期望缴纳" : "未要求",
    ],
    [
      "出差接受度",
      travelLabel(snapshot.travel_tolerance),
    ],
  ];
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k} className="flex gap-2">
          <dt className="shrink-0 text-slate-500 dark:text-slate-400">{k}</dt>
          <dd className="min-w-0 flex-1 text-slate-900 dark:text-slate-100">
            {v}
          </dd>
        </div>
      ))}
      {skills.length > 0 && (
        <div className="flex gap-2 sm:col-span-2">
          <dt className="shrink-0 text-slate-500 dark:text-slate-400">技能</dt>
          <dd className="flex flex-1 flex-wrap gap-1">
            {skills.map((s) => (
              <span
                key={s}
                className="rounded bg-slate-200/70 px-1.5 py-0.5 text-xs text-slate-700 dark:bg-slate-700 dark:text-slate-200"
              >
                {s}
              </span>
            ))}
          </dd>
        </div>
      )}
    </dl>
  );
}

function travelLabel(
  v: StructuredProfile["travel_tolerance"],
): string {
  switch (v) {
    case "willing":
      return "接受出差";
    case "occasional":
      return "偶尔出差";
    case "unwilling":
      return "不出差";
    default:
      return "—";
  }
}

function VersionSkeleton() {
  return (
    <ul className="divide-y divide-slate-100 dark:divide-slate-800">
      {Array.from({ length: 3 }).map((_, i) => (
        <li key={i} className="flex items-center gap-2 py-2.5">
          <div className="size-4 shrink-0 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 w-20 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
            <div className="h-2.5 w-40 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
          </div>
        </li>
      ))}
    </ul>
  );
}

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    // Locale-stable, no timezone surprises in the display.
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default ProfileVersionHistory;

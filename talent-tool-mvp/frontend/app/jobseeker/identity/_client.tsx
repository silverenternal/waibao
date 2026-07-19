"use client";

/**
 * v11.2 T6303 — Jobseeker identity verification + structured-profile page.
 *
 * Combines:
 *   - overall IdentityStatusBadge
 *   - DocumentUploader (身份证 / 学历证明 / 简历)
 *   - editable structured profile form (GET/PUT /profile; save = new version)
 *   - ProfileVersionHistory (preview + 恢复到此版本)
 *
 * 甲方 rule: identity_status = 'verified' ONLY when id_card + education + resume
 * are ALL 'verified'. 五险一金 / 出差 are HIGH priority (shown prominently).
 */

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, Save, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { IdentityStatusBadge } from "@/components/identity/IdentityStatusBadge";
import { DocumentUploader } from "@/components/identity/DocumentUploader";
import { ProfileVersionHistory } from "@/components/identity/ProfileVersionHistory";
import {
  fetchIdentityStatus,
  fetchProfile,
  TRAVEL_TOLERANCE_OPTIONS,
  updateProfile,
  type IdentityStatus,
  type StructuredProfile,
} from "@/lib/api-identity";

const EMPTY_PROFILE: StructuredProfile = {
  name: "",
  title: "",
  city: "",
  skills: [],
  education: "",
  experience: "",
  expected_salary: "",
  social_insurance_expectation: false,
  travel_tolerance: "occasional",
};

export function IdentityPageClient() {
  return (
    <ErrorBoundary>
      <IdentityPageInner />
    </ErrorBoundary>
  );
}

function IdentityPageInner() {
  const [status, setStatus] = React.useState<IdentityStatus | null>(null);
  const [statusLoading, setStatusLoading] = React.useState(true);
  const [statusError, setStatusError] = React.useState<string | null>(null);
  // Bumped after a profile save so ProfileVersionHistory refetches.
  const [historyRefresh, setHistoryRefresh] = React.useState(0);

  const loadStatus = React.useCallback(async () => {
    setStatusLoading(true);
    setStatusError(null);
    try {
      const s = await fetchIdentityStatus();
      setStatus(s);
    } catch (e) {
      setStatusError(e instanceof Error ? e.message : "加载身份状态失败");
    } finally {
      setStatusLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 lg:py-10">
      <header className="mb-6 space-y-2">
        <Link
          href="/jobseeker/profile"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
        >
          <ArrowLeft className="size-4" />
          返回我的简历
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">身份验证与档案版本</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              上传资料完成身份核验,并维护你的结构化档案。每次保存都会生成一个新版本。
            </p>
          </div>
          <OverallBadge status={status} loading={statusLoading} error={statusError} />
        </div>
      </header>

      {statusError ? (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
          {statusError}
          <Button
            variant="link"
            size="sm"
            className="ml-2 h-auto p-0"
            onClick={() => void loadStatus()}
          >
            重试
          </Button>
        </div>
      ) : null}

      <div className="space-y-6">
        <DocumentUploader
          status={status}
          onStatusChange={setStatus}
          onError={(_doc, msg) => toast.error(msg)}
        />

        <StructuredProfileForm
          onSaved={() => {
            void loadStatus();
            setHistoryRefresh((n) => n + 1);
          }}
        />

        <ProfileVersionHistory refreshKey={historyRefresh} />
      </div>
    </main>
  );
}

function OverallBadge({
  status,
  loading,
  error,
}: {
  status: IdentityStatus | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-slate-500">
        <Loader2 className="size-4 animate-spin" />
        加载状态…
      </span>
    );
  }
  if (error || !status) {
    return <IdentityStatusBadge status="pending" label="状态未知" size="md" />;
  }
  return (
    <IdentityStatusBadge
      status={status.overall}
      label={status.overall_display}
      size="md"
    />
  );
}

// ---------------------------------------------------------------------------
// Editable structured profile form
// ---------------------------------------------------------------------------

function StructuredProfileForm({ onSaved }: { onSaved: () => void }) {
  const [profile, setProfile] = React.useState<StructuredProfile>(EMPTY_PROFILE);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [versionNo, setVersionNo] = React.useState<number | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await fetchProfile();
      setProfile(normalizeProfile(p));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载档案失败");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  function set<K extends keyof StructuredProfile>(
    key: K,
    value: StructuredProfile[K],
  ) {
    setProfile((cur) => ({ ...cur, [key]: value }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await updateProfile(toPayload(profile));
      setVersionNo(res.version_no);
      setProfile(normalizeProfile(res.profile ?? profile));
      toast.success(`已保存(版本 ${res.version_no})`);
      onSaved();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "保存失败";
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  const skillsText = Array.isArray(profile.skills)
    ? profile.skills.join(", ")
    : "";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="size-4 text-slate-500" />
          结构化档案
        </CardTitle>
        <CardDescription>
          编辑后保存将生成一个新版本(增量,历史版本保留)。带
          <span className="font-medium text-amber-600"> ★ </span>
          为高优先级匹配项(不会因此被淘汰)。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300">
            {error}
          </div>
        ) : null}
        {loading ? (
          <FormSkeleton />
        ) : (
          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="姓名" htmlFor="profile-name">
                <Input
                  id="profile-name"
                  value={profile.name ?? ""}
                  onChange={(e) => set("name", e.target.value)}
                  placeholder="你的姓名"
                />
              </Field>
              <Field label="职位 / 头衔" htmlFor="profile-title">
                <Input
                  id="profile-title"
                  value={profile.title ?? ""}
                  onChange={(e) => set("title", e.target.value)}
                  placeholder="如 高级前端工程师"
                />
              </Field>
              <Field label="城市" htmlFor="profile-city">
                <Input
                  id="profile-city"
                  value={profile.city ?? ""}
                  onChange={(e) => set("city", e.target.value)}
                  placeholder="如 上海"
                />
              </Field>
              <Field label="学历" htmlFor="profile-education">
                <Input
                  id="profile-education"
                  value={profile.education ?? ""}
                  onChange={(e) => set("education", e.target.value)}
                  placeholder="如 本科"
                />
              </Field>
              <Field label="期望薪资" htmlFor="profile-salary">
                <Input
                  id="profile-salary"
                  value={profile.expected_salary ?? ""}
                  onChange={(e) => set("expected_salary", e.target.value)}
                  placeholder="如 25-35K"
                />
              </Field>
              <Field label="技能(逗号分隔)" htmlFor="profile-skills">
                <Input
                  id="profile-skills"
                  value={skillsText}
                  onChange={(e) =>
                    set(
                      "skills",
                      e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    )
                  }
                  placeholder="如 TypeScript, React, Node.js"
                />
              </Field>
            </div>

            <Field label="工作经历" htmlFor="profile-experience">
              <Textarea
                id="profile-experience"
                value={profile.experience ?? ""}
                onChange={(e) => set("experience", e.target.value)}
                placeholder="简要描述工作经历(可被 AI 进一步结构化)"
                rows={3}
              />
            </Field>

            {/* HIGH priority — 五险一金 / 出差 (soft scoring, never eliminate). */}
            <div className="grid gap-4 rounded-lg border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-900 dark:bg-amber-950/20 sm:grid-cols-2">
              <div className="flex items-start gap-2.5 sm:col-span-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
                  ★ 高优先级偏好
                </span>
              </div>
              <label
                htmlFor="profile-social"
                className="flex min-h-11 cursor-pointer items-center gap-2.5 rounded-md px-1 py-1"
              >
                <Checkbox
                  id="profile-social"
                  checked={Boolean(profile.social_insurance_expectation)}
                  onCheckedChange={(v) =>
                    set("social_insurance_expectation", Boolean(v))
                  }
                />
                <span className="text-sm">
                  期望五险一金
                  <span className="ml-1 text-xs text-slate-500">(社保 + 公积金)</span>
                </span>
              </label>
              <Field label="出差接受度" htmlFor="profile-travel" inline>
                <Select
                  value={profile.travel_tolerance ?? "occasional"}
                  onValueChange={(v) =>
                    set(
                      "travel_tolerance",
                      (v as StructuredProfile["travel_tolerance"]) ?? "occasional",
                    )
                  }
                >
                  <SelectTrigger
                    id="profile-travel"
                    className="w-full"
                    aria-label="出差接受度"
                  >
                    <SelectValue placeholder="选择出差接受度" />
                  </SelectTrigger>
                  <SelectContent>
                    {TRAVEL_TOLERANCE_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {versionNo != null
                  ? `当前最新版本:${versionNo}`
                  : "尚未保存任何版本"}
              </p>
              <Button
                type="submit"
                disabled={saving}
                className="h-11 sm:h-9"
              >
                {saving ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Save className="size-4" />
                )}
                保存档案
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  htmlFor,
  inline,
  children,
}: {
  label: string;
  htmlFor: string;
  inline?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={inline ? "space-y-1.5" : "space-y-1.5"}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function FormSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="space-y-1.5">
            <div className="h-3 w-16 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
            <div className="h-9 w-full animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
          </div>
        ))}
      </div>
      <div className="h-20 w-full animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalizeProfile(p: StructuredProfile | null): StructuredProfile {
  if (!p) return { ...EMPTY_PROFILE };
  return {
    ...EMPTY_PROFILE,
    ...p,
    skills: Array.isArray(p.skills) ? p.skills : [],
    social_insurance_expectation: Boolean(p.social_insurance_expectation),
    travel_tolerance: p.travel_tolerance ?? "occasional",
  };
}

/** Strip UI-only junk before sending to the backend (only known fields). */
function toPayload(p: StructuredProfile): StructuredProfile {
  return {
    name: p.name ?? "",
    title: p.title ?? "",
    city: p.city ?? "",
    skills: Array.isArray(p.skills) ? p.skills : [],
    education: p.education ?? "",
    experience: p.experience ?? "",
    expected_salary: p.expected_salary ?? "",
    social_insurance_expectation: Boolean(p.social_insurance_expectation),
    travel_tolerance: p.travel_tolerance ?? "occasional",
  };
}

export default IdentityPageClient;

"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * JD editor page (T604).
 *
 * Flow:
 *   1. Load role by id (GET /api/roles/{role_id}) — populates draft JD.
 *   2. Pick an industry template from the picker (left column) to scaffold.
 *   3. Edit the JD in the textarea (center column).
 *   4. Click "提交生成" → POST /api/job-spec/submit — receives new
 *      responsibilities / hard reqs / nice-to-haves / over_spec_flags.
 *   5. Review-over-spec panel (right column) and version history below.
 *
 * All API access goes through `frontend/lib/api-jd.ts`.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  Save,
  Sparkles,
  AlertCircle,
  Wand2,
  CheckCircle2,
  Pencil,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

import {
  jdApi,
  classifyBatch,
  TONE,
  type JDVersion,
} from "@/lib/api-jd";

import { JDTemplatePicker } from "@/components/jd/JDTemplatePicker";
import { OverSpecWarning } from "@/components/jd/OverSpecWarning";
import { JDVersionHistory } from "@/components/jd/JDVersionHistory";
import { JDVersionDiff } from "@/components/jd/JDVersionDiff";

export default function RoleJDEditPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const roleId = params?.id ?? "";

  const [draft, setDraft] = React.useState("");
  const [original, setOriginal] = React.useState("");
  const [overSpec, setOverSpec] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [regenerating, setRegenerating] = React.useState(false);
  const [toast, setToast] = React.useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [selectedVersion, setSelectedVersion] = React.useState<JDVersion | null>(null);
  const [lastResult, setLastResult] = React.useState<{
    responsibilities: string[];
    hard_requirements: Array<{ category: string; value: string }>;
    nice_to_haves: string[];
  } | null>(null);

  // Initial load
  React.useEffect(() => {
    if (!roleId) return;
    let cancelled = false;
    setLoading(true);
    jdApi
      .getRole(roleId)
      .then((role) => {
        if (cancelled) return;
        const text = role.description ?? "";
        setDraft(text);
        setOriginal(text);
      })
      .catch(() => {
        // ignore — user can still edit on a blank slate
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [roleId]);

  async function handleSave() {
    if (!roleId) return;
    setSaving(true);
    setToast(null);
    try {
      await jdApi.updateRole(roleId, { description: draft });
      setOriginal(draft);
      setToast({ kind: "ok", text: "已保存" });
    } catch (e: unknown) {
      setToast({ kind: "err", text: e instanceof Error ? e.message : "保存失败" });
    } finally {
      setSaving(false);
      window.setTimeout(() => setToast(null), 2400);
    }
  }

  async function handleRegenerate() {
    setRegenerating(true);
    setToast(null);
    try {
      const resp = await jdApi.submitSpec({ text: draft, roleId });
      setOverSpec(resp.artifacts?.over_spec_flags ?? []);
      setLastResult({
        responsibilities: resp.artifacts?.responsibilities ?? [],
        hard_requirements: resp.artifacts?.hard_requirements ?? [],
        nice_to_haves: resp.artifacts?.nice_to_haves ?? [],
      });
      if (resp.artifacts?.draft_jd) {
        setDraft(resp.artifacts.draft_jd);
      }
      setToast({ kind: "ok", text: "已生成新草稿" });
    } catch (e: unknown) {
      setToast({ kind: "err", text: e instanceof Error ? e.message : "生成失败" });
    } finally {
      setRegenerating(false);
      window.setTimeout(() => setToast(null), 2400);
    }
  }

  async function handlePickTemplate(templateId: string) {
    try {
      const resp = await jdApi.template(templateId);
      const tpl = resp.template;
      // Hydrate the textarea with the template body, plus the user's raw entry appended.
      const sections: string[] = [];
      sections.push(`# ${tpl.title} (${tpl.industry})`);
      if (tpl.description) sections.push(tpl.description);
      sections.push("");
      sections.push("## 岗位职责");
      for (const r of tpl.responsibilities) sections.push(`- ${r}`);
      sections.push("");
      sections.push("## 硬性要求");
      for (const r of tpl.hard_requirements) {
        const yrs = r.min_years ? ` · ≥${r.min_years}年` : "";
        sections.push(`- ${r.value}${yrs}`);
      }
      sections.push("");
      sections.push("## 加分项");
      for (const r of tpl.nice_to_haves) sections.push(`- ${r}`);
      if (draft.trim()) {
        sections.push("");
        sections.push("## 我的补充");
        sections.push(draft);
      }
      setDraft(sections.join("\n"));
      setOverSpec(tpl.over_spec_warnings ?? []);
      setToast({ kind: "ok", text: `已载入模板「${tpl.title}」` });
    } catch (e: unknown) {
      setToast({ kind: "err", text: e instanceof Error ? e.message : "模板载入失败" });
    } finally {
      window.setTimeout(() => setToast(null), 2400);
    }
  }

  const overall = classifyBatch(overSpec);
  const tone = TONE[overall];
  const dirty = draft !== original;
  const wordCount = draft.trim().length;

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
        <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => router.push(`/employer/role/${roleId}/talent-image`)}
                aria-label="返回画像"
              >
                <ArrowLeft className="size-4" />
              </Button>
              <div>
                <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                  <Pencil className="size-5 text-violet-500" />
                  JD 编辑器
                </h1>
                <p className="text-xs text-muted-foreground">
                  Role ID · <span className="font-mono">{roleId || "—"}</span>
                  {dirty && (
                    <Badge
                      variant="outline"
                      className="ml-2 border-amber-300 bg-amber-50 text-[10px] text-amber-700"
                    >
                      未保存
                    </Badge>
                  )}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleRegenerate}
                disabled={regenerating || !draft.trim()}
                className="gap-2"
              >
                {regenerating ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Wand2 className="size-4" />
                )}
                {regenerating ? "生成中…" : "智能体润色"}
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving || !draft.trim() || !dirty}
                className="gap-2"
              >
                {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                保存
              </Button>
            </div>
          </div>
          {toast && (
            <div
              role="status"
              className={cn(
                "mx-auto max-w-7xl px-6 py-2 text-xs",
                toast.kind === "ok"
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-rose-50 text-rose-700",
              )}
            >
              {toast.text}
            </div>
          )}
        </header>
        <main className="mx-auto grid max-w-7xl gap-4 px-6 py-6 lg:grid-cols-12">
          {/* Left: templates */}
          <section className="space-y-4 lg:col-span-4">
            <JDTemplatePicker onPick={handlePickTemplate} />

            <OverSpecWarning flags={overSpec} loading={regenerating} />

            <JDVersionHistory
              roleId={roleId}
              selectedId={selectedVersion?.id ?? null}
              onSelect={setSelectedVersion}
            />
          </section>

          {/* Center: editor */}
          <section className="space-y-4 lg:col-span-5">
            <Card>
              <CardContent className="space-y-3 py-4">
                <header className="flex items-center justify-between gap-2">
                  <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                    <Sparkles className="size-4 text-blue-500" />
                    JD 草稿
                  </h2>
                  <span className="text-[10px] text-slate-500">
                    字数 {wordCount} ·{" "}
                    <span
                      className={cn(
                        "rounded px-1",
                        overall === "red"
                          ? "bg-rose-100 text-rose-700"
                          : overall === "amber"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-emerald-100 text-emerald-700",
                      )}
                    >
                      {tone.label}
                    </span>
                  </span>
                </header>
                {loading ? (
                  <div className="space-y-2">
                    <div className="h-3 w-3/4 animate-pulse rounded bg-slate-200" />
                    <div className="h-40 w-full animate-pulse rounded bg-slate-100" />
                  </div>
                ) : (
                  <Textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="在此编写或粘贴岗位描述...也可以从左侧模板库载入作为起点。"
                    className="min-h-[55vh] font-mono text-sm"
                  />
                )}
                <p className="text-[11px] text-slate-500">
                  修改后点击「保存」入库,点击「智能体润色」用 LLM 提炼职责/要求并检测过度项。
                </p>
              </CardContent>
            </Card>

            <JDVersionDiff current={draft} baseline={selectedVersion} />

            {lastResult && (
              <Card>
                <CardContent className="space-y-3 py-4">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                    <CheckCircle2 className="size-4 text-emerald-500" />
                    智能体提取结果
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setLastResult(null)}
                      className="ml-auto h-7 gap-1"
                    >
                      <X className="size-3" />
                      关闭
                    </Button>
                  </h3>
                  <Section title="岗位职责" items={lastResult.responsibilities} />
                  <Section
                    title="硬性要求"
                    items={lastResult.hard_requirements.map(
                      (r) => `${r.category} · ${r.value}`,
                    )}
                  />
                  <Section title="加分项" items={lastResult.nice_to_haves} />
                </CardContent>
              </Card>
            )}
          </section>

          {/* Right: secondary info / version detail */}
          <section className="space-y-4 lg:col-span-3">
            <Card>
              <CardContent className="space-y-2 py-4 text-xs text-slate-700">
                <h3 className="flex items-center gap-1 text-sm font-semibold text-slate-800">
                  <AlertCircle className="size-3.5 text-amber-500" />
                  编辑提示
                </h3>
                <ul className="list-disc space-y-1 pl-4 text-[11px] text-slate-600">
                  <li>避免硬性要求性别、年龄、婚育、地域等指标。</li>
                  <li>薪资带宽建议覆盖 P25–P75,过低会显著降低投递率。</li>
                  <li>硬性要求 ≤ 5 条为佳,过多会拉长招聘周期。</li>
                  <li>技术栈优先使用市场主流命名 (React/Vue/Python),便于自动匹配。</li>
                </ul>
              </CardContent>
            </Card>

            {selectedVersion && (
              <Card>
                <CardContent className="space-y-2 py-4 text-xs">
                  <h3 className="text-sm font-semibold text-slate-800">
                    选定版本 · v{selectedVersion.version_no}
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    {new Date(selectedVersion.created_at).toLocaleString("en-GB", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </p>
                  <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-2 text-[11px] text-slate-700">
                    {selectedVersion.description}
                  </pre>
                  {selectedVersion.over_spec_flags.length > 0 && (
                    <div className="rounded-md border border-amber-200 bg-amber-50/60 p-2 text-[11px] text-amber-700">
                      {selectedVersion.over_spec_flags.length} 项过度要求提示
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </section>
        </main>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// Helper components
// ---------------------------------------------------------------------------

function Section({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h4 className="text-xs font-medium text-slate-500">{title}</h4>
      <ul className="mt-1 space-y-1">
        {items.map((it, i) => (
          <li
            key={i}
            className="rounded-md border border-slate-200 bg-slate-50/50 px-2 py-1 text-[11px] text-slate-700"
          >
            · {it}
          </li>
        ))}
      </ul>
    </section>
  );
}

export { cn };

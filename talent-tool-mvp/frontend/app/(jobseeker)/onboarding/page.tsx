"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileUp,
  ScanLine,
  PencilLine,
  PartyPopper,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import { ResumeUpload, type OCRResult } from "@/components/ResumeUpload";
import {
  ProfileCompleteness,
  type ProfileField,
  type FieldStatus,
} from "@/components/ProfileCompleteness";
import { FieldHighlight } from "@/components/FieldHighlight";

type StepKey = "upload" | "confirm" | "supplement" | "done";

interface StepDef {
  key: StepKey;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}

const STEPS: StepDef[] = [
  {
    key: "upload",
    title: "上传简历",
    description: "支持 PDF / Word / 图片,自动 OCR 解析",
    icon: FileUp,
  },
  {
    key: "confirm",
    title: "OCR 确认",
    description: "检查识别结果,改正错误字段",
    icon: ScanLine,
  },
  {
    key: "supplement",
    title: "手动补充",
    description: "补全缺失字段,提升匹配准确度",
    icon: PencilLine,
  },
  {
    key: "done",
    title: "建档完成",
    description: "可以开始匹配工作啦",
    icon: PartyPopper,
  },
];

interface ProfileDraft {
  full_name?: string;
  email?: string;
  phone?: string;
  location?: string;
  headline?: string;
  years_experience?: number;
  skills?: string[];
  bio?: string;
  expected_salary?: string;
  remote?: string;
}

function fieldStatusFor(draft: ProfileDraft): ProfileField[] {
  const isStr = (v?: string) => Boolean(v && v.trim().length > 0);
  const isArr = (v?: string[]) => Boolean(v && v.length > 0);

  const check = (
    key: string,
    label: string,
    filled: boolean,
    preview?: string,
    weak = false,
  ): ProfileField => ({
    key,
    label,
    status: filled ? (weak ? "weak" : "filled") : "empty",
    preview,
  });

  return [
    check("full_name", "姓名", isStr(draft.full_name), draft.full_name),
    check("email", "邮箱", isStr(draft.email), draft.email, !draft.email?.includes("@")),
    check("phone", "联系电话", isStr(draft.phone), draft.phone),
    check("location", "所在城市", isStr(draft.location), draft.location),
    check("headline", "职位头衔", isStr(draft.headline), draft.headline, true),
    check(
      "years_experience",
      "工作年限",
      typeof draft.years_experience === "number" && draft.years_experience > 0,
      draft.years_experience ? `${draft.years_experience} 年` : undefined,
    ),
    check(
      "skills",
      "核心技能",
      isArr(draft.skills),
      draft.skills?.slice(0, 5).join("、"),
      isArr(draft.skills) && (draft.skills?.length ?? 0) < 3,
    ),
    check("bio", "个人简介", isStr(draft.bio), draft.bio, (draft.bio?.length ?? 0) < 30),
    check(
      "expected_salary",
      "期望薪资",
      isStr(draft.expected_salary),
      draft.expected_salary,
    ),
    check("remote", "工作偏好", isStr(draft.remote), draft.remote),
  ];
}

export default function OnboardingPage() {
  const router = useRouter();
  const [stepIdx, setStepIdx] = React.useState(0);
  const [draft, setDraft] = React.useState<ProfileDraft>({});
  const [uploaded, setUploaded] = React.useState(false);
  const [loadingProfile, setLoadingProfile] = React.useState(true);

  // Pre-populate from any existing profile the user already has.
  React.useEffect(() => {
    let cancelled = false;
    async function loadExisting() {
      try {
        const token =
          typeof window !== "undefined"
            ? localStorage.getItem("sb_token") || ""
            : "";
        const res = await fetch("/api/users/me", {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setDraft({
          full_name: data.full_name,
          email: data.email,
          phone: data.phone,
          location: data.location,
          headline: data.headline,
          years_experience: data.years_experience,
          skills: data.skills,
          bio: data.bio,
          expected_salary: data.expected_salary,
          remote: data.remote_preference,
        });
      } catch {
        // ignore — user just hasn't filled anything yet
      } finally {
        if (!cancelled) setLoadingProfile(false);
      }
    }
    void loadExisting();
    return () => {
      cancelled = true;
    };
  }, []);

  const fields = React.useMemo(() => fieldStatusFor(draft), [draft]);
  const missingCount = fields.filter((f) => f.status === "empty").length;

  const step = STEPS[stepIdx];
  const isFirst = stepIdx === 0;
  const isLast = stepIdx === STEPS.length - 1;
  const progressPct = Math.round(((stepIdx + 1) / STEPS.length) * 100);

  const canGoNext = (() => {
    switch (step.key) {
      case "upload":
        return uploaded;
      case "confirm":
        return Boolean(draft.full_name);
      case "supplement":
        return missingCount <= 5; // soft gate — allow proceed when most fields are filled
      default:
        return true;
    }
  })();

  const goNext = () => {
    if (stepIdx < STEPS.length - 1) setStepIdx((i) => i + 1);
  };
  const goBack = () => {
    if (stepIdx > 0) setStepIdx((i) => i - 1);
  };

  const handleOCRComplete = React.useCallback((ocr: OCRResult) => {
    setDraft((d) => ({
      ...d,
      full_name: ocr.full_name ?? d.full_name,
      email: ocr.email ?? d.email,
      phone: ocr.phone ?? d.phone,
      location: ocr.location ?? d.location,
      headline: ocr.headline ?? d.headline,
      years_experience: ocr.years_experience ?? d.years_experience,
      skills: ocr.skills ?? d.skills,
      bio: ocr.summary ?? d.bio,
    }));
    setUploaded(true);
    // Auto-advance once OCR lands — feels smoother than forcing a click.
    setTimeout(() => setStepIdx((i) => (i === 0 ? 1 : i)), 600);
  }, []);

  const handleFinish = async () => {
    // Submit the draft to /api/users/me or /api/candidates — best-effort.
    try {
      const token = localStorage.getItem("sb_token") || "";
      await fetch("/api/users/me", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(draft),
      });
    } catch {
      // ignored — onboarding continues even if the network blip
    }
    setStepIdx(STEPS.length - 1);
  };

  const update = <K extends keyof ProfileDraft>(key: K, v: ProfileDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: v }));

  return (
    <div className="min-h-screen bg-slate-50/60">
      {/* Top bar */}
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3 sm:px-6">
          <div>
            <h1 className="text-base font-semibold">建档向导</h1>
            <p className="text-xs text-muted-foreground">
              完成 4 步,即可开始智能匹配
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => router.push("/jobseeker")}>
            跳过
          </Button>
        </div>
        <Progress value={progressPct} className="h-1 rounded-none" />
      </header>

      {/* Stepper */}
      <nav
        aria-label="建档步骤"
        className="mx-auto max-w-4xl px-4 pt-6 sm:px-6"
      >
        <ol className="flex items-center justify-between gap-2 overflow-x-auto">
          {STEPS.map((s, i) => {
            const isCurrent = i === stepIdx;
            const isDone = i < stepIdx;
            const Icon = s.icon;
            return (
              <li key={s.key} className="flex flex-1 items-center">
                <div className="flex flex-col items-center text-center">
                  <div
                    className={cn(
                      "grid size-9 place-items-center rounded-full border-2 transition-colors",
                      isDone && "border-primary bg-primary text-primary-foreground",
                      isCurrent && "border-primary bg-primary/10 text-primary",
                      !isDone && !isCurrent && "border-muted-foreground/30 text-muted-foreground",
                    )}
                  >
                    {isDone ? <Check className="size-4" /> : <Icon className="size-4" />}
                  </div>
                  <span
                    className={cn(
                      "mt-1.5 text-[11px] font-medium sm:text-xs",
                      isCurrent ? "text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {s.title}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className={cn(
                      "mx-2 h-0.5 flex-1 rounded-full transition-colors",
                      i < stepIdx ? "bg-primary" : "bg-muted",
                    )}
                  />
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Step content */}
      <main className="mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-5">
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
            {step.title}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
        </div>

        <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
          {/* Left: step body */}
          <div className="space-y-5">
            {step.key === "upload" && (
              <ResumeUpload
                onOCRComplete={handleOCRComplete}
                onComplete={() => setUploaded(true)}
                folder="resumes"
              />
            )}

            {step.key === "confirm" && (
              <ConfirmStep
                draft={draft}
                update={update}
                loading={loadingProfile}
              />
            )}

            {step.key === "supplement" && (
              <SupplementStep
                draft={draft}
                update={update}
                fields={fields}
              />
            )}

            {step.key === "done" && <DoneStep draft={draft} />}
          </div>

          {/* Right: completeness sidebar (hidden on small screens for upload step) */}
          <aside
            className={cn(
              "space-y-4",
              step.key === "upload" ? "lg:block" : "lg:block",
            )}
          >
            <ProfileCompleteness
              fields={fields}
              title="档案完整度"
              showFieldList={step.key !== "upload"}
            />
            {step.key === "supplement" && missingCount > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">补全提示</CardTitle>
                  <CardDescription>
                    以下字段越完整,推荐越精准
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-1.5 text-xs text-muted-foreground">
                    {fields
                      .filter((f) => f.status !== "filled")
                      .slice(0, 5)
                      .map((f) => (
                        <li key={f.key} className="flex items-center gap-2">
                          <span
                            className={cn(
                              "size-1.5 rounded-full",
                              f.status === "weak" ? "bg-amber-500" : "bg-rose-500",
                            )}
                          />
                          <span>{f.label}</span>
                          <Badge
                            variant="outline"
                            className="ml-auto h-4 px-1 text-[9px]"
                          >
                            {f.status === "weak" ? "建议" : "缺失"}
                          </Badge>
                        </li>
                      ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </aside>
        </div>
      </main>

      {/* Bottom nav */}
      <footer className="sticky bottom-0 border-t bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Button
            variant="ghost"
            size="sm"
            onClick={goBack}
            disabled={isFirst}
          >
            <ArrowLeft className="mr-1 size-4" />
            上一步
          </Button>

          <p className="hidden text-xs text-muted-foreground sm:block">
            第 {stepIdx + 1} / {STEPS.length} 步
          </p>

          {isLast ? (
            <Button
              size="sm"
              onClick={() => router.push("/match")}
              className="min-w-28"
            >
              开始匹配
              <ArrowRight className="ml-1 size-4" />
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={
                step.key === "supplement" ? handleFinish : goNext
              }
              disabled={!canGoNext}
              className="min-w-28"
            >
              下一步
              <ArrowRight className="ml-1 size-4" />
            </Button>
          )}
        </div>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-steps
// ---------------------------------------------------------------------------

function ConfirmStep({
  draft,
  update,
  loading,
}: {
  draft: ProfileDraft;
  update: <K extends keyof ProfileDraft>(key: K, v: ProfileDraft[K]) => void;
  loading: boolean;
}) {
  if (loading) {
    return (
      <Card>
        <CardContent className="space-y-3 py-6">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>OCR 识别结果</CardTitle>
        <CardDescription>
          请确认以下内容;错误的地方直接改,空着的我们下一步再补。
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-sm font-medium">姓名</label>
          <Input
            value={draft.full_name ?? ""}
            onChange={(e) => update("full_name", e.target.value)}
            placeholder="请输入姓名"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">邮箱</label>
          <Input
            type="email"
            value={draft.email ?? ""}
            onChange={(e) => update("email", e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">电话</label>
          <Input
            value={draft.phone ?? ""}
            onChange={(e) => update("phone", e.target.value)}
            placeholder="+86 138 0000 0000"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">所在城市</label>
          <Input
            value={draft.location ?? ""}
            onChange={(e) => update("location", e.target.value)}
            placeholder="上海"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">职位头衔</label>
          <Input
            value={draft.headline ?? ""}
            onChange={(e) => update("headline", e.target.value)}
            placeholder="高级前端工程师"
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">工作年限</label>
          <Input
            type="number"
            min={0}
            max={50}
            value={draft.years_experience ?? ""}
            onChange={(e) =>
              update(
                "years_experience",
                e.target.value === "" ? undefined : Number(e.target.value),
              )
            }
            placeholder="5"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-sm font-medium">核心技能(逗号分隔)</label>
          <Input
            value={draft.skills?.join("、") ?? ""}
            onChange={(e) =>
              update(
                "skills",
                e.target.value
                  .split(/[,、\s]+/)
                  .map((s) => s.trim())
                  .filter(Boolean),
              )
            }
            placeholder="React, TypeScript, Next.js"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-sm font-medium">个人简介</label>
          <Textarea
            value={draft.bio ?? ""}
            onChange={(e) => update("bio", e.target.value)}
            placeholder="一句话介绍一下你自己"
            className="min-h-24"
          />
        </div>
      </CardContent>
    </Card>
  );
}

function SupplementStep({
  draft,
  update,
  fields,
}: {
  draft: ProfileDraft;
  update: <K extends keyof ProfileDraft>(key: K, v: ProfileDraft[K]) => void;
  fields: ProfileField[];
}) {
  // Build editable sections for every field — FieldHighlight shows the visual
  // status + one-click ask button per missing field.
  const renderers: Array<{
    key: keyof ProfileDraft;
    label: string;
    hint?: string;
    multiline?: boolean;
  }> = [
    { key: "full_name", label: "姓名", hint: "用于推荐信和合同签署" },
    { key: "email", label: "邮箱", hint: "招聘方会通过邮件联系你" },
    { key: "phone", label: "联系电话", hint: "可填写手机或座机" },
    { key: "location", label: "所在城市", hint: "影响通勤范围与远程匹配" },
    { key: "headline", label: "职位头衔", hint: "如:高级前端工程师" },
    {
      key: "years_experience",
      label: "工作年限",
      hint: "数字即可,如 5",
    },
    {
      key: "skills",
      label: "核心技能",
      hint: "用逗号分隔,至少 3 项更佳",
    },
    {
      key: "bio",
      label: "个人简介",
      hint: "建议 50 字以上,AI 会用于匹配",
      multiline: true,
    },
    {
      key: "expected_salary",
      label: "期望薪资",
      hint: "如 30k-50k / 月,或面议",
    },
    {
      key: "remote",
      label: "工作偏好",
      hint: "如:远程 / 混合 / 现场",
    },
  ];

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>补全关键字段</CardTitle>
          <CardDescription>
            {fields.filter((f) => f.status === "empty").length} 个字段待补充 ·
            点击「一键补问」让 AI 引导你填写
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="grid gap-3">
        {renderers.map((r) => {
          const meta = fields.find((f) => f.key === r.key);
          const isFilled = meta?.status === "filled";
          const severity: "missing" | "weak" =
            meta?.status === "weak"
              ? "weak"
              : "missing";
          return (
            <FieldHighlight
              key={r.key}
              label={r.label}
              value={draft[r.key] as string | string[] | number | null | undefined}
              severity={severity}
              hint={r.hint}
              multiline={r.multiline}
              aiQuestion={`你的${r.label}是什么?`}
              onAskAI={() => {
                // Placeholder: in production this opens a drawer with the
                // realtime copilot, prefilled with the field-specific prompt.
              }}
              onConfirmValue={
                isFilled
                  ? undefined
                  : async (val) => {
                      if (r.key === "years_experience") {
                        const n = Number(val);
                        update(r.key, (Number.isFinite(n) ? n : undefined) as never);
                      } else if (r.key === "skills") {
                        update(
                          r.key,
                          val
                            .split(/[,、\s]+/)
                            .map((s) => s.trim())
                            .filter(Boolean) as never,
                        );
                      } else {
                        update(r.key, val as never);
                      }
                    }
              }
            />
          );
        })}
      </div>
    </div>
  );
}

function DoneStep({ draft }: { draft: ProfileDraft }) {
  return (
    <Card className="border-emerald-200/60 bg-emerald-50/40">
      <CardContent className="flex flex-col items-center py-10 text-center">
        <div className="grid size-14 place-items-center rounded-full bg-emerald-100 text-emerald-600">
          <PartyPopper className="size-7" />
        </div>
        <h3 className="mt-4 text-xl font-semibold">建档完成 🎉</h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          你的档案已就绪,匹配引擎会根据
          {draft.skills && draft.skills.length > 0
            ? ` ${draft.skills.length} 项核心技能`
            : "你的信息"}
          推送合适的工作机会。
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-2 text-xs text-muted-foreground">
          {draft.skills?.slice(0, 5).map((s) => (
            <Badge key={s} variant="secondary">
              {s}
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// Re-export the status enum so future pages can reuse the same FieldStatus
// type without importing the ProfileCompleteness module twice.
export type { FieldStatus };
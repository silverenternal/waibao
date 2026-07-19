"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 · 求职者 Profile (OpenResume 风格)
 * --------------------------------------------------------------------
 * 思路:
 *   - 中间一份"简历纸张" (A4 比例, 11in / 8.5in),打印友好。
 *   - 顶部头像 + 联系方式 + 关键字标签。
 *   - 摘要 / 经验 / 项目 / 技能 / 教育 五段,统一排版节奏。
 *   - 右侧浮动操作:下载 PDF、复制为 Markdown、分享给顾问。
 *   - 数据来自 mock,接口后续接入;若 components/jobseeker/*
 *     出现同名导出,可被自然替换。
 *
 * v11.2 (T6305) · 身份与版本卡片
 *   - 右侧新增「身份与版本」卡片:整体身份徽章 + 最新版本号 + 跳转到
 *     /jobseeker/identity 进行身份核验与档案编辑。
 */

import * as React from "react";
import Link from "next/link";
import {
  Briefcase,
  Download,
  GraduationCap,
  History,
  Mail,
  Pencil,
  Phone,
  Share2,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { IdentityStatusBadge } from "@/components/identity/IdentityStatusBadge";
import {
  fetchIdentityStatus,
  fetchProfileVersions,
  type IdentityStatus,
} from "@/lib/api-identity";

// --------------------------------------------------------------------
// 1. Mock 数据
// --------------------------------------------------------------------

const PROFILE = {
  name: "陈思远",
  title: "高级前端工程师 · 候选 Lead",
  location: "London, UK · 远程友好",
  email: "siyuan.chen@example.com",
  phone: "+44 7700 900123",
  links: [
    { label: "LinkedIn", href: "https://www.linkedin.com/in/siyuan" },
    { label: "GitHub", href: "https://github.com/siyuan" },
    { label: "个人站", href: "https://siyuan.dev" },
  ],
  headline:
    "8 年前端经验,过去 3 年聚焦于设计系统、平台化与团队工程效能。带过 6 人小组,主导过 0 → 1 设计系统迁移,首屏体积下降 38%。",
  skills: [
    { name: "TypeScript", level: 5 },
    { name: "React / Next.js", level: 5 },
    { name: "Node.js", level: 4 },
    { name: "设计系统", level: 5 },
    { name: "GraphQL", level: 4 },
    { name: "Vite / Turbopack", level: 4 },
    { name: "Tailwind / shadcn", level: 5 },
    { name: "可访问性 a11y", level: 4 },
  ],
  experiences: [
    {
      company: "Tidewave Tech",
      title: "高级前端工程师",
      period: "2022.06 – 至今",
      location: "London · 混合办公",
      bullets: [
        "主导前端设计系统 v2 迁移:从 5 套主题/12 仓库统一到 1 套 + 88 组件,9 支团队切换,首屏体积 -38%。",
        "搭建内部 CLI + PR 模板 + 质量门禁,让组件贡献者从 3 人扩到 17 人,平均合入周期从 5.2 天降到 1.4 天。",
        "带 6 人小组,负责季度 OKR 与 1:1;3 人晋升,1 人转岗架构。",
      ],
      tags: ["React", "TypeScript", "设计系统", "团队管理"],
    },
    {
      company: "Northwind Labs",
      title: "前端工程师",
      period: "2019.08 – 2022.05",
      location: "Remote · UK",
      bullets: [
        "从 0 到 1 交付 B 端数据可视化平台,接入 14 家客户,平均加载 < 1.2s。",
        "推动 E2E 测试覆盖率从 12% 提升到 71%,线上 P0 故障同比下降 64%。",
      ],
      tags: ["React", "D3", "Playwright"],
    },
    {
      company: "Verdant Studio",
      title: "初级前端工程师",
      period: "2017.07 – 2019.07",
      location: "Edinburgh",
      bullets: [
        "参与 6 个商业站点交付,平均项目周期 8 周,客户满意度 4.8/5。",
        "在团队内引入 ESLint + Prettier + Husky 工具链,把代码评审时间缩短 35%。",
      ],
      tags: ["Vue", "Webpack"],
    },
  ],
  projects: [
    {
      name: "Resumable Design Tokens",
      period: "2024",
      summary:
        "开源的 design token 增量加载方案,支持热更新与回滚。GitHub 1.2k star。",
      link: "https://github.com/siyuan/resumable-tokens",
    },
    {
      name: "AI 求职助手 (内部)",
      period: "2024 Q3 – 2024 Q4",
      summary:
        "用 RAG + 多 agent 编排构建的内部求职助手,日活 320,平均任务时长 6 分钟。",
    },
  ],
  education: [
    {
      school: "University of Edinburgh",
      degree: "BSc Computer Science",
      period: "2013 – 2017",
      note: "一等学位 · Dean 名单",
    },
  ],
  languages: [
    { name: "中文", level: "母语" },
    { name: "English", level: "工作流利 (IELTS 8.0)" },
  ],
};

const COMPLETENESS = 86;

// --------------------------------------------------------------------
// 2. 小组件
// --------------------------------------------------------------------

function ResumePaper({ children }: { children: React.ReactNode }) {
  return (
    <div
      id="resume-paper"
      className={cn(
        "mx-auto w-full max-w-[820px] rounded-xl bg-white text-slate-900 shadow-xl ring-1 ring-slate-200",
        "print:shadow-none print:ring-0",
      )}
    >
      <div className="px-10 py-10 print:px-8 print:py-8">{children}</div>
    </div>
  );
}

function SectionTitle({ children, icon }: { children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="mb-3 mt-6 flex items-center gap-2 first:mt-0">
      {icon ? <span className="text-slate-500">{icon}</span> : null}
      <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
        {children}
      </h2>
      <span className="ml-2 h-px flex-1 bg-slate-200" />
    </div>
  );
}

function SkillBar({ name, level }: { name: string; level: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-medium text-slate-800">{name}</span>
        <span className="text-slate-500">{level}/5</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-slate-800"
          style={{ width: `${(level / 5) * 100}%` }}
        />
      </div>
    </div>
  );
}

// --------------------------------------------------------------------
// 3. 身份与版本卡片 (v11.2 T6305)
// --------------------------------------------------------------------

function IdentityAndVersionCard() {
  const [status, setStatus] = React.useState<IdentityStatus | null>(null);
  const [latestVersion, setLatestVersion] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.allSettled([fetchIdentityStatus(), fetchProfileVersions()])
      .then(([statusRes, versionsRes]) => {
        if (!active) return;
        if (statusRes.status === "fulfilled") setStatus(statusRes.value);
        if (
          versionsRes.status === "fulfilled" &&
          versionsRes.value.length > 0
        ) {
          setLatestVersion(versionsRes.value[0].version_no);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle className="flex items-center gap-2 text-sm">
          <ShieldCheck className="size-4 text-indigo-500" />
          身份与版本
        </CardTitle>
        <CardDescription>
          核验身份资料,管理结构化档案版本。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">整体身份状态</span>
          {loading ? (
            <span className="text-xs text-muted-foreground">加载中…</span>
          ) : (
            <IdentityStatusBadge
              status={status?.overall}
              label={status?.overall_display}
            />
          )}
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <History className="size-3.5" />
            最新档案版本
          </span>
          <span className="text-sm font-medium">
            {latestVersion != null ? `v${latestVersion}` : "—"}
          </span>
        </div>
        <Button size="sm" className="w-full" asChild>
          <Link href="/jobseeker/identity">前往身份验证与档案</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------
// 4. 页面
// --------------------------------------------------------------------

export function JobseekerProfileClient() {
  const [editing, setEditing] = React.useState(false);
  const initials = PROFILE.name.slice(0, 1);

  function handlePrint() {
    if (typeof window !== "undefined") window.print();
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(buildPlainText(PROFILE));
    } catch {
      /* ignore */
    }
  }

  return (
    <ErrorBoundary>
      <div className="mx-auto flex max-w-6xl flex-col gap-6 p-4 lg:p-8">
        {/* 操作条 */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">我的简历</h1>
            <p className="text-sm text-muted-foreground">
              AI 已根据你的档案和最近 90 天的工作自动整理。可以一键导出或分享。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={handleCopy}>
              <Share2 className="size-4" />
              复制为文本
            </Button>
            <Button size="sm" variant="outline" onClick={handlePrint}>
              <Download className="size-4" />
              下载 PDF
            </Button>
            <Button size="sm" onClick={() => setEditing((v) => !v)}>
              <Pencil className="size-4" />
              {editing ? "完成" : "编辑"}
            </Button>
          </div>
        </div>
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          {/* 左:简历纸张 */}
          <ResumePaper>
            {/* Header */}
            <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
              <Avatar className="size-20 ring-2 ring-slate-200">
                <AvatarFallback className="text-2xl font-semibold text-slate-700">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 space-y-1">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                  {PROFILE.name}
                </h1>
                <p className="text-sm font-medium text-slate-700">
                  {PROFILE.title}
                </p>
                <p className="text-sm text-slate-500">{PROFILE.location}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <Mail className="size-3" />
                    {PROFILE.email}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Phone className="size-3" />
                    {PROFILE.phone}
                  </span>
                  {PROFILE.links.map((l) => (
                    <a
                      key={l.label}
                      href={l.href}
                      className="text-indigo-600 hover:underline"
                      target="_blank"
                      rel="noreferrer"
                    >
                      {l.label}
                    </a>
                  ))}
                </div>
              </div>
            </header>

            <Separator className="my-5" />

            {/* Summary */}
            <SectionTitle>个人简介</SectionTitle>
            <p className="text-sm leading-relaxed text-slate-700">
              {PROFILE.headline}
            </p>

            {/* Skills */}
            <SectionTitle icon={<Wrench className="size-3.5" />}>技能</SectionTitle>
            <div className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
              {PROFILE.skills.map((s) => (
                <SkillBar key={s.name} name={s.name} level={s.level} />
              ))}
            </div>

            {/* Experience */}
            <SectionTitle icon={<Briefcase className="size-3.5" />}>
              工作经验
            </SectionTitle>
            <div className="space-y-5">
              {PROFILE.experiences.map((e) => (
                <article key={e.company}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-semibold text-slate-900">
                      {e.title} · {e.company}
                    </h3>
                    <span className="text-xs text-slate-500">{e.period}</span>
                  </div>
                  <p className="text-xs text-slate-500">{e.location}</p>
                  <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-slate-700">
                    {e.bullets.map((b, i) => (
                      <li key={i} className="relative pl-4">
                        <span className="absolute left-1 top-2 size-1 rounded-full bg-slate-400" />
                        {b}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {e.tags.map((t) => (
                      <Badge
                        key={t}
                        variant="secondary"
                        className="bg-slate-100 text-[10px] text-slate-600"
                      >
                        {t}
                      </Badge>
                    ))}
                  </div>
                </article>
              ))}
            </div>

            {/* Projects */}
            <SectionTitle>项目亮点</SectionTitle>
            <div className="space-y-3">
              {PROFILE.projects.map((p) => (
                <div key={p.name}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-semibold text-slate-900">
                      {p.name}
                      {p.link ? (
                        <a
                          href={p.link}
                          target="_blank"
                          rel="noreferrer"
                          className="ml-1.5 text-xs font-normal text-indigo-600 hover:underline"
                        >
                          ↗
                        </a>
                      ) : null}
                    </h3>
                    <span className="text-xs text-slate-500">{p.period}</span>
                  </div>
                  <p className="text-sm text-slate-700">{p.summary}</p>
                </div>
              ))}
            </div>

            {/* Education */}
            <SectionTitle icon={<GraduationCap className="size-3.5" />}>
              教育
            </SectionTitle>
            <div className="space-y-2">
              {PROFILE.education.map((e) => (
                <div
                  key={e.school}
                  className="flex flex-wrap items-baseline justify-between gap-2"
                >
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      {e.school} · {e.degree}
                    </p>
                    <p className="text-xs text-slate-500">{e.note}</p>
                  </div>
                  <span className="text-xs text-slate-500">{e.period}</span>
                </div>
              ))}
            </div>

            {/* Languages */}
            <SectionTitle>语言</SectionTitle>
            <ul className="grid grid-cols-1 gap-1.5 text-sm text-slate-700 sm:grid-cols-2">
              {PROFILE.languages.map((l) => (
                <li key={l.name} className="flex items-center justify-between">
                  <span className="font-medium">{l.name}</span>
                  <span className="text-xs text-slate-500">{l.level}</span>
                </li>
              ))}
            </ul>
          </ResumePaper>

          {/* 右:操作 + 提示 */}
          <aside className="space-y-4">
            <IdentityAndVersionCard />

            <Card>
              <CardHeader className="space-y-1">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Sparkles className="size-4 text-indigo-500" />
                  档案完整度
                </CardTitle>
                <CardDescription>
                  完整度越高,推荐越精准。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <div className="flex items-baseline justify-between text-xs">
                    <span className="text-muted-foreground">当前</span>
                    <span className="text-2xl font-semibold tracking-tight">
                      {COMPLETENESS}%
                    </span>
                  </div>
                  <Progress value={COMPLETENESS} className="mt-1 h-2" />
                </div>
                <ul className="space-y-1.5 text-xs">
                  <Hint done label="基础信息 / 联系方式" />
                  <Hint done label="工作经历 3 段" />
                  <Hint done label="技能 8 项,带熟练度" />
                  <Hint done label="2 个项目亮点" />
                  <Hint done label="教育背景" />
                  <Hint
                    label="上传作品集 / 视频简历(可解锁金牌)"
                  />
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="space-y-1">
                <CardTitle className="text-sm">分享给顾问</CardTitle>
                <CardDescription>
                  顾问 Lily 已经看过这份简历的最新版本。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <Button size="sm" className="w-full">
                  分享给 Lily
                </Button>
                <Button size="sm" variant="outline" className="w-full">
                  生成匿名版
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="space-y-1">
                <CardTitle className="text-sm">下一步</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-muted-foreground">
                <p>
                  · 让 Copilot{" "}
                  <span className="text-foreground">润色工作经历</span>
                  ,把数字结果前置。
                </p>
                <p>
                  · 看看{" "}
                  <span className="text-foreground">Tidewave</span>{" "}
                  给你的 88% 匹配度如何拆解。
                </p>
                <p>
                  · 打开{" "}
                  <span className="text-foreground">议价模拟</span>
                  ,为 92k 目标做准备。
                </p>
              </CardContent>
            </Card>

            {editing && (
              <Card className="border-dashed bg-muted/40">
                <CardContent className="space-y-1 py-3 text-xs text-muted-foreground">
                  <p className="font-medium text-foreground">编辑模式已开启</p>
                  <p>
                    真实的内联编辑组件会在 <code>components/jobseeker/</code>{" "}
                    出现后接入。当前页面以只读预览形式展示。
                  </p>
                </CardContent>
              </Card>
            )}
          </aside>
        </div>
      </div>
    </ErrorBoundary>
  );
}

function Hint({ label, done }: { label: string; done?: boolean }) {
  return (
    <li className="flex items-center gap-2">
      <span
        className={cn(
          "flex size-3.5 items-center justify-center rounded-full border text-[10px] font-bold",
          done
            ? "border-emerald-500 bg-emerald-500 text-white"
            : "border-slate-300 text-slate-400",
        )}
        aria-hidden
      >
        {done ? "✓" : ""}
      </span>
      <span className={cn(done ? "text-foreground" : "text-muted-foreground")}>
        {label}
      </span>
    </li>
  );
}

function buildPlainText(p: typeof PROFILE): string {
  return [
    `${p.name} — ${p.title}`,
    `${p.location} · ${p.email} · ${p.phone}`,
    "",
    "个人简介",
    p.headline,
    "",
    "技能",
    p.skills.map((s) => `- ${s.name} (${s.level}/5)`).join("\n"),
    "",
    "经验",
    p.experiences
      .map(
        (e) =>
          `${e.title} · ${e.company} (${e.period})\n` +
          e.bullets.map((b) => `  - ${b}`).join("\n"),
      )
      .join("\n\n"),
    "",
    "项目",
    p.projects.map((p) => `- ${p.name} (${p.period}): ${p.summary}`).join("\n"),
    "",
    "教育",
    p.education
      .map((e) => `- ${e.school} · ${e.degree} (${e.period}) · ${e.note}`)
      .join("\n"),
  ].join("\n");
}

export default JobseekerProfileClient;

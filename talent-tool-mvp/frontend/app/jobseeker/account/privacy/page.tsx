"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — 求职者隐私设置 (GDPR / 中国《个人信息保护法》双视角).
 *
 * 包含:
 *  - 数据类别同意 (必要 / 功能 / 分析 / 营销 / 跨境 / 训练)
 *  - 档案可见性 (公开 / 仅顾问 / 私密)
 *  - 个性化推荐开关 + 解释
 *  - AI 训练数据授权 (使用 / 退出)
 *  - 第三方数据共享
 *  - Cookie 同意 (快速设置)
 *  - 数据导出 / 删除请求
 *  - GDPR 权利清单 (访问/更正/删除/可携/反对/限制)
 *  - 投诉与 DPO 联系
 *
 * 设计:
 *  - 中文为主, 关键术语标注英文
 *  - 顶部 GDPR 概览, 下方分章节
 *  - 移动优先, lg 断点切换两列
 *  - 客户端 state, localStorage 持久化
 *  - ARIA: switch / role=region / aria-live 友好
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCheck,
  Cookie,
  Database,
  Download,
  Eye,
  EyeOff,
  FileLock2,
  Globe2,
  Info,
  Loader2,
  Lock,
  Mail,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  TriangleAlert,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";

const STORAGE_KEY = "v9.1.jobseeker.privacy";

type Visibility = "public" | "consultants" | "private";
type ConsentMap = Record<string, boolean>;

interface PrivacyState {
  consents: ConsentMap;
  visibility: Visibility;
  aiTraining: boolean;
  shareWithPartners: boolean;
  shareAnonymized: boolean;
  cookieSet: "all" | "essential" | "custom";
  cookies: { essential: boolean; functional: boolean; analytics: boolean; marketing: boolean };
}

const DEFAULT_STATE: PrivacyState = {
  consents: {
    necessary: true,
    functional: true,
    analytics: true,
    marketing: false,
    cross_border: false,
    ai_training: false,
  },
  visibility: "consultants",
  aiTraining: false,
  shareWithPartners: false,
  shareAnonymized: true,
  cookieSet: "custom",
  cookies: {
    essential: true,
    functional: true,
    analytics: true,
    marketing: false,
  },
};

interface CategoryDef {
  key: keyof PrivacyState["consents"];
  label: string;
  desc: string;
  required?: boolean;
  legal?: string;
}

const CATEGORIES: CategoryDef[] = [
  {
    key: "necessary",
    label: "必要数据",
    desc: "登录会话、CSRF Token、欺诈防护。关闭后无法登录。",
    required: true,
    legal: "GDPR Art.6(1)(b) 合同必要",
  },
  {
    key: "functional",
    label: "功能偏好",
    desc: "语言、主题、最近浏览、视图模式等用户体验。",
    legal: "GDPR Art.6(1)(a) 同意",
  },
  {
    key: "analytics",
    label: "匿名分析",
    desc: "页面访问、停留时长、点击分布,用于改进产品。",
    legal: "GDPR Art.6(1)(a) 同意",
  },
  {
    key: "marketing",
    label: "个性化推荐",
    desc: "在站内 / 站外向您展示更相关的工作机会和内容。",
    legal: "GDPR Art.6(1)(a) 同意",
  },
  {
    key: "cross_border",
    label: "跨境数据传输",
    desc: "为匹配海外岗位,数据可能传输至 EEA / 英国 / 美国。",
    legal: "GDPR Art.46 SCC 标准合同条款",
  },
  {
    key: "ai_training",
    label: "AI 模型训练",
    desc: "经过脱敏的档案与匹配记录用于训练和评估模型。",
    legal: "GDPR Art.6(1)(a) 同意",
  },
];

const VISIBILITY: Array<{
  key: Visibility;
  title: string;
  desc: string;
  icon: typeof Eye;
}> = [
  {
    key: "public",
    title: "公开",
    desc: "任何访问者都能看到你的公开档案;招聘方可一键申请约谈。",
    icon: Globe2,
  },
  {
    key: "consultants",
    title: "仅签约顾问可见",
    desc: "推荐选项;收到邀请的招聘方可在匹配池中看到你。",
    icon: Users,
  },
  {
    key: "private",
    title: "私密",
    desc: "只有你本人和你主动联系的顾问能看到;匹配仅基于匿名画像。",
    icon: Lock,
  },
];

const GDPR_RIGHTS: Array<{ key: string; title: string; desc: string }> = [
  { key: "access", title: "访问权 (Art.15)", desc: "获取我们持有的关于你的个人数据副本" },
  { key: "rectify", title: "更正权 (Art.16)", desc: "纠正不准确或不完整的数据" },
  { key: "erase", title: "被遗忘权 (Art.17)", desc: "删除您的个人数据(在符合条件时)" },
  { key: "restrict", title: "限制处理权 (Art.18)", desc: "在特定情况下限制我们处理您的数据" },
  { key: "portability", title: "可携带权 (Art.20)", desc: "以结构化、机器可读格式导出数据" },
  { key: "object", title: "反对权 (Art.21)", desc: "反对基于合法利益或营销目的的处理" },
];

export default function PrivacyPage() {
  const [state, setState] = React.useState<PrivacyState>(DEFAULT_STATE);
  const [hydrated, setHydrated] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [savedAt, setSavedAt] = React.useState<string | null>(null);
  const [dirty, setDirty] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [deleteStep, setDeleteStep] = React.useState<1 | 2>(1);
  const [exportOpen, setExportOpen] = React.useState(false);

  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<PrivacyState>;
        setState((prev) => ({ ...prev, ...parsed }));
      }
    } catch {
      /* ignore */
    } finally {
      setHydrated(true);
    }
  }, []);

  React.useEffect(() => {
    if (!hydrated || !dirty) return;
    const t = window.setTimeout(() => void doSave(false), 500);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, hydrated, dirty]);

  const doSave = async (manual: boolean) => {
    setSaving(true);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      await new Promise((r) => setTimeout(r, manual ? 380 : 120));
      setSavedAt(new Date().toLocaleTimeString("zh-CN"));
      setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  const setConsent = (key: keyof PrivacyState["consents"], v: boolean) => {
    setState((p) => {
      const cat = CATEGORIES.find((c) => c.key === key);
      if (cat?.required && !v) return p;
      return {
        ...p,
        consents: { ...p.consents, [key]: v },
        cookies:
          key === "necessary"
            ? { ...p.cookies, essential: true }
            : key === "functional"
              ? { ...p.cookies, functional: v }
              : key === "analytics"
                ? { ...p.cookies, analytics: v }
                : key === "marketing"
                  ? { ...p.cookies, marketing: v }
                  : p.cookies,
      };
    });
    setDirty(true);
  };

  const setVisibility = (v: Visibility) => {
    setState((p) => ({ ...p, visibility: v }));
    setDirty(true);
  };

  const setFlag = <K extends keyof PrivacyState>(key: K, value: PrivacyState[K]) => {
    setState((p) => ({ ...p, [key]: value }));
    setDirty(true);
  };

  const setCookie = (
    key: keyof PrivacyState["cookies"],
    v: boolean,
  ) => {
    setState((p) => ({
      ...p,
      cookies: { ...p.cookies, [key]: v },
      cookieSet: "custom",
    }));
    setDirty(true);
  };

  const applyCookieSet = (which: "all" | "essential") => {
    if (which === "all") {
      setState((p) => ({
        ...p,
        cookies: { essential: true, functional: true, analytics: true, marketing: true },
        cookieSet: "all",
      }));
    } else {
      setState((p) => ({
        ...p,
        cookies: { essential: true, functional: false, analytics: false, marketing: false },
        cookieSet: "essential",
      }));
    }
    setDirty(true);
  };

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
        {/* 顶部 */}
        <header className="mb-6 sm:mb-8">
          <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
            <Link
              href="/jobseeker/account"
              className="inline-flex items-center gap-1 hover:text-foreground"
            >
              <ArrowLeft className="size-3" aria-hidden="true" />
              返回账户
            </Link>
            <span aria-hidden="true">/</span>
            <span aria-current="page">隐私设置</span>
          </div>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                <ShieldCheck className="size-3.5" aria-hidden="true" />
                GDPR · PIPL 双视角
              </div>
              <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
                你的数据,你说了算
              </h1>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                我们按「数据最小化」原则收集信息;你可以随时撤回同意、导出或删除数据。
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {saving ? (
                <span className="inline-flex items-center gap-1">
                  <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                  保存中
                </span>
              ) : savedAt ? (
                <span className="inline-flex items-center gap-1 text-emerald-600">
                  <CheckCheck className="size-3" aria-hidden="true" />
                  已保存 · {savedAt}
                </span>
              ) : (
                <span>尚未修改</span>
              )}
              <Button
                size="sm"
                onClick={() => doSave(true)}
                disabled={!dirty || saving}
              >
                <Save className="mr-1.5 size-4" aria-hidden="true" />
                立即保存
              </Button>
            </div>
          </div>
        </header>
        {/* 概览卡 */}
        <section
          aria-label="隐私概览"
          className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4"
        >
          <PrivacyKpi
            icon={Eye}
            label="档案可见性"
            value={
              VISIBILITY.find((v) => v.key === state.visibility)?.title ?? "私密"
            }
            tone="indigo"
          />
          <PrivacyKpi
            icon={Sparkles}
            label="AI 训练"
            value={state.consents.ai_training ? "已授权" : "未授权"}
            tone="amber"
          />
          <PrivacyKpi
            icon={Database}
            label="跨境传输"
            value={state.consents.cross_border ? "已授权" : "未授权"}
            tone="sky"
          />
          <PrivacyKpi
            icon={Cookie}
            label="Cookie 模式"
            value={
              state.cookieSet === "all"
                ? "全部接受"
                : state.cookieSet === "essential"
                  ? "仅必要"
                  : "自定义"
            }
            tone="rose"
          />
        </section>
        {/* 数据类别同意 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">数据类别同意</CardTitle>
            <CardDescription>
              每项可独立开启 / 关闭;必要项无法关闭。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!hydrated ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : (
              CATEGORIES.map((c) => {
                const on = state.consents[c.key];
                return (
                  <ConsentRow
                    key={c.key}
                    def={c}
                    checked={on}
                    onChange={(v) => setConsent(c.key, v)}
                  />
                );
              })
            )}
          </CardContent>
        </Card>
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          {/* 档案可见性 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">档案可见性</CardTitle>
              <CardDescription>
                控制谁可以在匹配池中看到你的资料。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {VISIBILITY.map((v) => {
                const Icon = v.icon;
                const active = state.visibility === v.key;
                return (
                  <button
                    key={v.key}
                    type="button"
                    onClick={() => setVisibility(v.key)}
                    aria-pressed={active}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors",
                      active
                        ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                        : "border-border hover:bg-muted/40",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 grid size-9 place-items-center rounded-md",
                        active
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground",
                      )}
                      aria-hidden="true"
                    >
                      <Icon className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="text-sm font-medium leading-tight">
                          {v.title}
                        </span>
                        {active && (
                          <Badge variant="outline" className="h-4 px-1 text-[9px]">
                            当前
                          </Badge>
                        )}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-muted-foreground">
                        {v.desc}
                      </span>
                    </span>
                  </button>
                );
              })}
            </CardContent>
          </Card>

          {/* AI 训练 + 共享 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">AI 与第三方</CardTitle>
              <CardDescription>
                决定你的数据是否参与模型训练、是否与合作伙伴共享。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <ToggleRow
                icon={Sparkles}
                title="参与 AI 训练"
                description="经过脱敏的档案与匹配记录用于训练和评估模型。"
                checked={state.aiTraining}
                onChange={(v) => {
                  setFlag("aiTraining", v);
                  setConsent("ai_training", v);
                }}
              />
              <ToggleRow
                icon={Users}
                title="与签约合作伙伴共享"
                description="仅共享招聘方需要的字段(如技能、薪资区间),不共享联系方式。"
                checked={state.shareWithPartners}
                onChange={(v) => setFlag("shareWithPartners", v)}
              />
              <ToggleRow
                icon={Globe2}
                title="允许跨境传输 (SCC)"
                description="为匹配海外岗位,数据可能传输至 EEA / 英国 / 美国 (使用标准合同条款)。"
                checked={state.consents.cross_border}
                onChange={(v) => setConsent("cross_border", v)}
              />
              <ToggleRow
                icon={EyeOff}
                title="匿名化分析"
                description="允许在完全去标识化后用于产品分析。"
                checked={state.shareAnonymized}
                onChange={(v) => setFlag("shareAnonymized", v)}
              />
            </CardContent>
          </Card>
        </div>
        {/* Cookie */}
        <Card className="mb-6">
          <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
            <div>
              <CardTitle className="text-base">Cookie 同意</CardTitle>
              <CardDescription>
                控制网站 Cookie 类型;影响本地化、统计与营销功能。
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => applyCookieSet("essential")}
              >
                仅必要
              </Button>
              <Button size="sm" onClick={() => applyCookieSet("all")}>
                全部接受
              </Button>
            </div>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2">
            <CookieRow
              label="必要 Cookie"
              desc="登录会话、CSRF、负载均衡"
              checked={state.cookies.essential}
              disabled
              onChange={() => undefined}
            />
            <CookieRow
              label="功能 Cookie"
              desc="语言、主题、视图偏好"
              checked={state.cookies.functional}
              onChange={(v) => setCookie("functional", v)}
            />
            <CookieRow
              label="分析 Cookie"
              desc="页面访问、停留时长(匿名)"
              checked={state.cookies.analytics}
              onChange={(v) => setCookie("analytics", v)}
            />
            <CookieRow
              label="营销 Cookie"
              desc="站内 / 站外个性化推荐"
              checked={state.cookies.marketing}
              onChange={(v) => setCookie("marketing", v)}
            />
          </CardContent>
        </Card>
        {/* GDPR 权利 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">你的 GDPR 权利</CardTitle>
            <CardDescription>
              行使这些权利无需任何理由,我们会在 30 天内响应。
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2">
            {GDPR_RIGHTS.map((r) => (
              <div
                key={r.key}
                className="rounded-lg border bg-muted/30 p-3"
                role="region"
                aria-label={r.title}
              >
                <p className="text-sm font-medium">{r.title}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{r.desc}</p>
              </div>
            ))}
          </CardContent>
        </Card>
        {/* 数据导出 / 删除 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">数据导出与删除</CardTitle>
            <CardDescription>
              你随时可以拿回、或者永久删除你的数据。
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setExportOpen((v) => !v)}
              aria-expanded={exportOpen}
            >
              <Download className="mr-1.5 size-4" aria-hidden="true" />
              申请数据导出
            </Button>
            <Button
              asChild
              variant="outline"
              size="sm"
            >
              <Link href="/jobseeker/account/export-data">
                <FileLock2 className="mr-1.5 size-4" aria-hidden="true" />
                前往导出页
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setDeleteOpen(true);
                setDeleteStep(1);
              }}
              className="border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/30"
            >
              <Trash2 className="mr-1.5 size-4" aria-hidden="true" />
              申请删除账户
            </Button>
          </CardContent>

          {exportOpen && (
            <CardContent className="border-t pt-4">
              <div
                className="rounded-lg border border-emerald-200/60 bg-emerald-50 p-3 text-sm dark:border-emerald-900/40 dark:bg-emerald-950/30"
                role="status"
                aria-live="polite"
              >
                <p className="font-medium text-emerald-800 dark:text-emerald-200">
                  导出请求已提交
                </p>
                <p className="mt-0.5 text-xs text-emerald-700/80 dark:text-emerald-300/80">
                  我们会在 24 小时内把包含你的档案、消息、订阅、反馈的 JSON / CSV
                  文件,通过邮件发送到 {`<账户邮箱>`}。
                </p>
              </div>
            </CardContent>
          )}

          {deleteOpen && (
            <CardContent className="border-t pt-4">
              <div
                className="rounded-lg border border-rose-200/60 bg-rose-50 p-4 dark:border-rose-900/40 dark:bg-rose-950/30"
                role="alertdialog"
                aria-labelledby="del-title"
                aria-describedby="del-desc"
              >
                <div className="flex items-start gap-2">
                  <TriangleAlert
                    className="mt-0.5 size-5 shrink-0 text-rose-600"
                    aria-hidden="true"
                  />
                  <div className="flex-1">
                    <p id="del-title" className="font-semibold text-rose-800 dark:text-rose-200">
                      {deleteStep === 1 ? "确认删除账户?" : "最后确认 - 此操作不可撤销"}
                    </p>
                    <p id="del-desc" className="mt-1 text-sm text-rose-700/90 dark:text-rose-300/90">
                      {deleteStep === 1
                        ? "我们会在 7 天宽限期内保留你的数据(可恢复),之后将永久删除并断开与第三方合作伙伴的共享。"
                        : "请输入邮箱确认。我们将立即冻结账户,7 天后永久删除所有个人数据。"}
                    </p>
                  </div>
                </div>
                {deleteStep === 2 && (
                  <div className="mt-3 space-y-2">
                    <label
                      htmlFor="del-email"
                      className="block text-xs font-medium text-rose-800 dark:text-rose-200"
                    >
                      输入账户邮箱以确认
                    </label>
                    <input
                      id="del-email"
                      type="email"
                      placeholder="hugo.wang@example.com"
                      className="w-full rounded-md border border-rose-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-400 dark:border-rose-800 dark:bg-rose-950/40"
                    />
                  </div>
                )}
                <div className="mt-3 flex flex-wrap justify-end gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleteOpen(false)}
                  >
                    取消
                  </Button>
                  {deleteStep === 1 ? (
                    <Button
                      size="sm"
                      className="bg-rose-600 text-white hover:bg-rose-700"
                      onClick={() => setDeleteStep(2)}
                    >
                      继续
                    </Button>
                  ) : (
                    <Button
                      asChild
                      size="sm"
                      className="bg-rose-600 text-white hover:bg-rose-700"
                    >
                      <Link href="/jobseeker/account/delete-account">
                        永久删除
                      </Link>
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          )}
        </Card>
        {/* 合规说明 + DPO */}
        <Card className="border-dashed">
          <CardContent className="grid gap-4 p-5 sm:grid-cols-[1fr_auto] sm:items-center sm:p-6">
            <div>
              <p className="text-sm font-medium">数据保护官 (DPO)</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                如对您的数据处理有任何疑问、投诉或行权请求,可通过以下方式联系:
              </p>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                <li className="flex items-center gap-2">
                  <Mail className="size-3" aria-hidden="true" />
                  dpo@waibao.example
                </li>
                <li className="flex items-center gap-2">
                  <Globe2 className="size-3" aria-hidden="true" />
                  欧洲代表: 21 Rue de la Privacy, 75001 Paris
                </li>
                <li className="flex items-center gap-2">
                  <Info className="size-3" aria-hidden="true" />
                  响应时效: 一般 7 个工作日,最多 30 天(GDPR Art.12(3))
                </li>
              </ul>
            </div>
            <Button asChild size="sm" variant="outline">
              <Link href="/jobseeker/account/feedback-history">查看处理记录</Link>
            </Button>
          </CardContent>
        </Card>
        <Separator className="my-6" />
        <p className="text-center text-xs text-muted-foreground">
          我们遵循 GDPR (EU 2016/679) · UK GDPR · 中国《个人信息保护法》。
        </p>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function PrivacyKpi({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof ShieldCheck;
  label: string;
  value: string;
  tone: "indigo" | "amber" | "sky" | "rose";
}) {
  const toneCls: Record<typeof tone, string> = {
    indigo:
      "bg-indigo-50 text-indigo-700 ring-indigo-200/60 dark:bg-indigo-950/40 dark:text-indigo-200 dark:ring-indigo-900",
    amber: "bg-amber-50 text-amber-800 ring-amber-200/60 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900",
    sky: "bg-sky-50 text-sky-700 ring-sky-200/60 dark:bg-sky-950/40 dark:text-sky-200 dark:ring-sky-900",
    rose: "bg-rose-50 text-rose-700 ring-rose-200/60 dark:bg-rose-950/40 dark:text-rose-200 dark:ring-rose-900",
  };
  return (
    <div
      className={cn("rounded-xl p-3 ring-1 sm:p-4", toneCls[tone])}
      role="status"
      aria-label={`${label}: ${value}`}
    >
      <div className="flex items-center justify-between text-xs sm:text-sm">
        <span className="font-medium opacity-80">{label}</span>
        <Icon className="size-4 opacity-70" aria-hidden="true" />
      </div>
      <p className="mt-1.5 text-lg font-bold sm:text-xl">{value}</p>
    </div>
  );
}

function ConsentRow({
  def,
  checked,
  onChange,
}: {
  def: CategoryDef;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-lg border p-3",
        checked
          ? "border-primary/30 bg-primary/[0.025] dark:border-primary/30 dark:bg-primary/[0.04]"
          : "border-border",
      )}
    >
      <Checkbox
        checked={checked}
        disabled={def.required}
        onCheckedChange={(v) => onChange(v === true)}
        className="mt-0.5"
        aria-label={def.label}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium">{def.label}</p>
          {def.required && (
            <Badge variant="secondary" className="h-4 px-1.5 text-[9px]">
              必选
            </Badge>
          )}
          {def.legal && (
            <span className="text-[10px] text-muted-foreground">{def.legal}</span>
          )}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{def.desc}</p>
      </div>
    </div>
  );
}

function ToggleRow({
  icon: Icon,
  title,
  description,
  checked,
  onChange,
}: {
  icon: typeof Sparkles;
  title: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border p-3">
      <div className="flex min-w-0 items-start gap-3">
        <span
          className={cn(
            "mt-0.5 grid size-9 shrink-0 place-items-center rounded-md",
            checked
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground",
          )}
          aria-hidden="true"
        >
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-tight">{title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={title}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary",
          checked ? "bg-primary" : "bg-muted-foreground/30",
        )}
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-4" : "translate-x-0.5",
          )}
        />
      </button>
    </div>
  );
}

function CookieRow({
  label,
  desc,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  desc: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-3 rounded-lg border p-3",
        disabled && "opacity-80",
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-tight">{label}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{desc}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => !disabled && onChange(!checked)}
        disabled={disabled}
        className={cn(
          "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary",
          checked ? "bg-primary" : "bg-muted-foreground/30",
          disabled && "cursor-not-allowed",
        )}
      >
        <span
          className={cn(
            "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
            checked ? "translate-x-4" : "translate-x-0.5",
          )}
        />
      </button>
    </div>
  );
}

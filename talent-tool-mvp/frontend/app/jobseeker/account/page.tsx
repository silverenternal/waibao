"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — 求职者账户中心.
 *
 * 提供:
 *  - 顶部账户卡 (头像/姓名/角色/会员/安全摘要)
 *  - 个人信息 (可编辑:姓名/邮箱/电话/城市/简介)
 *  - 三个快速入口:通知偏好 / 隐私设置 / 反馈历史
 *  - 高级操作:导出数据 / 删除账户 (跳转现有路由)
 *  - 安全摘要 (登录设备 / 密码 / 两步验证)
 *  - 危险区 (注销 + 删除)
 *
 * 设计:
 *  - 中文精致:卡片+渐变+icon 风格统一
 *  - 响应式:mobile 单列 / lg 双列
 *  - 可访问:label / aria / focus 环 / role 标签
 */

import * as React from "react";
import Link from "next/link";
import {
  Bell,
  ChevronRight,
  Download,
  KeyRound,
  Lock,
  Mail,
  MapPin,
  Pencil,
  Phone,
  Save,
  Shield,
  ShieldCheck,
  Sparkles,
  Trash2,
  User,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { Avatar } from "@/components/ui/avatar";
import { Checkbox } from "@/components/ui/checkbox";

const PROFILE_KEY = "v9.1.jobseeker.account.profile";
const SECURITY_KEY = "v9.1.jobseeker.account.security";

interface ProfileDraft {
  fullName: string;
  email: string;
  phone: string;
  city: string;
  headline: string;
  bio: string;
  marketing: boolean;
  tips: boolean;
}

const DEFAULT_PROFILE: ProfileDraft = {
  fullName: "Hugo Wang",
  email: "hugo.wang@example.com",
  phone: "+44 7700 900 123",
  city: "London, UK",
  headline: "Senior Frontend Engineer · React / TypeScript",
  bio:
    "6 年前端经验,3 年带团队。最近在做的方向:设计系统、AI Copilot、跨端性能优化。",
  marketing: false,
  tips: true,
};

interface SecurityState {
  twoFactor: boolean;
  loginAlerts: boolean;
}

const DEFAULT_SECURITY: SecurityState = {
  twoFactor: true,
  loginAlerts: true,
};

export default function AccountPage() {
  const [profile, setProfile] = React.useState<ProfileDraft>(DEFAULT_PROFILE);
  const [security, setSecurity] = React.useState<SecurityState>(DEFAULT_SECURITY);
  const [hydrated, setHydrated] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [savedAt, setSavedAt] = React.useState<string | null>(null);

  React.useEffect(() => {
    try {
      const p = window.localStorage.getItem(PROFILE_KEY);
      const s = window.localStorage.getItem(SECURITY_KEY);
      if (p) {
        const parsed = JSON.parse(p) as Partial<ProfileDraft>;
        setProfile((prev) => ({ ...prev, ...parsed }));
      }
      if (s) {
        const parsed = JSON.parse(s) as SecurityState;
        setSecurity((prev) => ({ ...prev, ...parsed }));
      }
    } catch {
      /* ignore */
    } finally {
      setHydrated(true);
    }
  }, []);

  const updateProfile = <K extends keyof ProfileDraft>(
    key: K,
    value: ProfileDraft[K],
  ) => setProfile((p) => ({ ...p, [key]: value }));

  const save = async () => {
    setSaving(true);
    try {
      window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
      window.localStorage.setItem(SECURITY_KEY, JSON.stringify(security));
      await new Promise((r) => setTimeout(r, 350));
      setSavedAt(new Date().toLocaleTimeString("zh-CN"));
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">
        {/* 顶部账户卡 */}
        <Card className="mb-6 overflow-hidden border-none bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 text-white shadow-lg">
          <div className="grid gap-4 p-5 sm:grid-cols-[auto_1fr_auto] sm:items-center sm:p-7">
            <Avatar
              className="size-16 border-2 border-white/40 bg-white/20 text-lg font-semibold sm:size-20"
              aria-label="用户头像"
            >
              {profile.fullName.slice(0, 1) || "我"}
            </Avatar>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="truncate text-xl font-bold sm:text-2xl">
                  {profile.fullName}
                </h1>
                <Badge className="bg-white/20 text-white hover:bg-white/30">
                  <Sparkles className="mr-1 size-3" aria-hidden="true" />
                  Pro 会员
                </Badge>
              </div>
              <p className="mt-1 truncate text-sm text-white/85">
                {profile.headline}
              </p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-white/75">
                <MapPin className="size-3" aria-hidden="true" />
                {profile.city} · 账户 ID: hb-88219
              </p>
            </div>
            <div className="flex flex-wrap gap-2 sm:flex-col sm:items-end">
              <Button asChild variant="secondary" size="sm">
                <Link href="/jobseeker/profile">
                  <User className="mr-1.5 size-4" aria-hidden="true" />
                  公开档案
                </Link>
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setEditing((v) => !v)}
                aria-pressed={editing}
              >
                <Pencil className="mr-1.5 size-4" aria-hidden="true" />
                {editing ? "退出编辑" : "编辑信息"}
              </Button>
            </div>
          </div>
        </Card>
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <div className="space-y-6">
            {/* 个人信息 */}
            <Card>
              <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
                <div>
                  <CardTitle className="text-base">个人信息</CardTitle>
                  <CardDescription>
                    这些信息仅用于匹配和招聘方联系,不会公开展示邮箱和电话。
                  </CardDescription>
                </div>
                {savedAt && !editing && (
                  <Badge variant="outline" className="text-[10px] text-emerald-600">
                    已保存 · {savedAt}
                  </Badge>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                {!hydrated ? (
                  <div className="grid gap-4 sm:grid-cols-2">
                    {Array.from({ length: 6 }).map((_, i) => (
                      <Skeleton key={i} className="h-10 w-full" />
                    ))}
                  </div>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field
                      id="fullName"
                      label="姓名"
                      value={profile.fullName}
                      onChange={(v) => updateProfile("fullName", v)}
                      disabled={!editing}
                      icon={User}
                    />
                    <Field
                      id="email"
                      label="邮箱"
                      type="email"
                      value={profile.email}
                      onChange={(v) => updateProfile("email", v)}
                      disabled={!editing}
                      icon={Mail}
                    />
                    <Field
                      id="phone"
                      label="电话"
                      value={profile.phone}
                      onChange={(v) => updateProfile("phone", v)}
                      disabled={!editing}
                      icon={Phone}
                    />
                    <Field
                      id="city"
                      label="所在城市"
                      value={profile.city}
                      onChange={(v) => updateProfile("city", v)}
                      disabled={!editing}
                      icon={MapPin}
                    />
                    <Field
                      id="headline"
                      label="职位头衔"
                      value={profile.headline}
                      onChange={(v) => updateProfile("headline", v)}
                      disabled={!editing}
                      className="sm:col-span-2"
                    />
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="bio" className="text-sm font-medium">
                        个人简介
                      </Label>
                      <Textarea
                        id="bio"
                        value={profile.bio}
                        onChange={(e) => updateProfile("bio", e.target.value)}
                        disabled={!editing}
                        className="min-h-24"
                        placeholder="一句话介绍你自己的背景和求职方向"
                      />
                      <p className="text-[11px] text-muted-foreground">
                        建议 50-200 字,AI 会据此匹配岗位。
                      </p>
                    </div>
                  </div>
                )}

                <Separator />

                <div className="space-y-3">
                  <h3 className="text-sm font-medium">订阅与提示</h3>
                  <CheckboxRow
                    id="marketing"
                    label="接收合作方营销邮件"
                    description="如行业报告、雇主品牌活动等(每月 ≤ 2 封)"
                    checked={profile.marketing}
                    onChange={(v) => updateProfile("marketing", v)}
                    disabled={!editing}
                  />
                  <CheckboxRow
                    id="tips"
                    label="求职小贴士"
                    description="面试技巧、薪资谈判、签证政策等(每周精选)"
                    checked={profile.tips}
                    onChange={(v) => updateProfile("tips", v)}
                    disabled={!editing}
                  />
                </div>

                {editing && (
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setProfile(DEFAULT_PROFILE);
                        setEditing(false);
                      }}
                    >
                      放弃修改
                    </Button>
                    <Button size="sm" onClick={save} disabled={saving}>
                      {saving ? (
                        <span className="flex items-center gap-1">
                          <span className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                          保存中
                        </span>
                      ) : (
                        <>
                          <Save className="mr-1.5 size-4" aria-hidden="true" />
                          保存修改
                        </>
                      )}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 安全 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">账户安全</CardTitle>
                <CardDescription>
                  建议开启两步验证,并定期检查登录设备。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <CheckboxRow
                  id="2fa"
                  label="两步验证 (2FA)"
                  description="使用身份验证器应用,登录时需输入动态码"
                  checked={security.twoFactor}
                  onChange={(v) =>
                    setSecurity((s) => ({ ...s, twoFactor: v }))
                  }
                />
                <CheckboxRow
                  id="login-alerts"
                  label="新设备登录提醒"
                  description="非常用设备登录时,发送邮件 + 应用内通知"
                  checked={security.loginAlerts}
                  onChange={(v) =>
                    setSecurity((s) => ({ ...s, loginAlerts: v }))
                  }
                />
                <Separator />
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm">
                    <KeyRound className="mr-1.5 size-4" aria-hidden="true" />
                    修改密码
                  </Button>
                  <Button variant="outline" size="sm">
                    <ShieldCheck className="mr-1.5 size-4" aria-hidden="true" />
                    查看登录设备 (3 台)
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* 危险区 */}
            <Card className="border-rose-200/60 bg-rose-50/40 dark:border-rose-900/40 dark:bg-rose-950/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base text-rose-700 dark:text-rose-300">
                  <Shield className="size-4" aria-hidden="true" />
                  危险操作
                </CardTitle>
                <CardDescription>
                  注销仅关闭会话;删除账户将永久清除数据,且不可恢复。
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm">
                  <Lock className="mr-1.5 size-4" aria-hidden="true" />
                  注销所有设备
                </Button>
                <Button
                  asChild
                  variant="outline"
                  size="sm"
                  className="border-rose-300 text-rose-700 hover:bg-rose-100 dark:border-rose-800 dark:text-rose-300 dark:hover:bg-rose-950/40"
                >
                  <Link href="/jobseeker/account/delete-account">
                    <Trash2 className="mr-1.5 size-4" aria-hidden="true" />
                    永久删除账户
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </div>

          {/* 侧栏:快速入口 + 数据 */}
          <aside className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">设置</CardTitle>
                <CardDescription>常用设置快捷入口</CardDescription>
              </CardHeader>
              <CardContent className="space-y-1.5 p-2">
                <QuickLink
                  href="/jobseeker/account/notifications-prefs"
                  icon={Bell}
                  title="通知偏好"
                  description="分类 × 优先级 × 通道"
                  tone="indigo"
                />
                <QuickLink
                  href="/jobseeker/account/privacy"
                  icon={ShieldCheck}
                  title="隐私设置"
                  description="GDPR · Cookie · 数据可见性"
                  tone="emerald"
                />
                <QuickLink
                  href="/jobseeker/account/feedback-history"
                  icon={Sparkles}
                  title="反馈历史"
                  description="NPS / 问卷 / 主动反馈"
                  tone="amber"
                />
                <QuickLink
                  href="/jobseeker/subscriptions"
                  icon={Bell}
                  title="订阅管理"
                  description="求职订阅规则 CRUD"
                  tone="sky"
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">数据与导出</CardTitle>
                <CardDescription>你随时可以拿回自己的数据</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <Button asChild variant="outline" size="sm" className="w-full">
                  <Link href="/jobseeker/account/export-data">
                    <Download className="mr-1.5 size-4" aria-hidden="true" />
                    申请数据导出
                  </Link>
                </Button>
                <p className="text-[11px] text-muted-foreground">
                  导出文件包含你的档案、消息、订阅、反馈,通常 24 小时内通过邮件发送。
                </p>
              </CardContent>
            </Card>
          </aside>
        </div>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function Field({
  id,
  label,
  value,
  onChange,
  type = "text",
  disabled,
  icon: Icon,
  className,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  disabled?: boolean;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id} className="text-sm font-medium">
        {label}
      </Label>
      <div className="relative">
        {Icon && (
          <Icon
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
        )}
        <Input
          id={id}
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={cn(Icon && "pl-9")}
        />
      </div>
    </div>
  );
}

function CheckboxRow({
  id,
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      htmlFor={id}
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors",
        checked
          ? "border-primary/30 bg-primary/[0.025] dark:border-primary/30 dark:bg-primary/[0.04]"
          : "border-border hover:bg-muted/40",
        disabled && "cursor-not-allowed opacity-70",
      )}
    >
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(v) => onChange(v === true)}
        disabled={disabled}
        className="mt-0.5"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-snug">{label}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
    </label>
  );
}

function QuickLink({
  href,
  icon: Icon,
  title,
  description,
  tone,
}: {
  href: string;
  icon: LucideIcon;
  title: string;
  description: string;
  tone: "indigo" | "emerald" | "amber" | "sky";
}) {
  const toneCls: Record<typeof tone, string> = {
    indigo: "bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-300",
    emerald:
      "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300",
    amber: "bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300",
    sky: "bg-sky-50 text-sky-600 dark:bg-sky-950/40 dark:text-sky-300",
  };
  return (
    <Link
      href={href}
      className="group flex items-center gap-3 rounded-lg p-2.5 transition-colors hover:bg-muted/60"
    >
      <span
        className={cn(
          "grid size-9 place-items-center rounded-lg",
          toneCls[tone],
        )}
        aria-hidden="true"
      >
        <Icon className="size-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium leading-tight">{title}</span>
        <span className="block text-[11px] text-muted-foreground">
          {description}
        </span>
      </span>
      <ChevronRight
        className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5"
        aria-hidden="true"
      />
    </Link>
  );
}

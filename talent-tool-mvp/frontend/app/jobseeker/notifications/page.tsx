"use client";

/**
 * v9.1 — 求职者通知中心.
 *
 * 功能:
 *  - 通知列表 (匹配 / 面试 / Offer / 订阅 / 系统 / 营销)
 *  - 顶部 KPI (未读 / 紧急 / 今日)
 *  - 类型筛选 (Tabs) + 状态筛选 (全部/未读/已读)
 *  - 批量操作 (全部已读 / 批量删除)
 *  - 单条操作 (标为已读 / 删除 / 跳转)
 *  - 顶部 CTA 进入「通知偏好」页
 *  - 空状态 / 加载态 / 错误态
 *
 * 设计:
 *  - 中文为主,使用 lucide-react 图标
 *  - 移动优先,sm / lg 断点
 *  - ARIA: listitem / role=status / aria-live
 *  - 客户端状态,localStorage 持久化
 */

import * as React from "react";
import Link from "next/link";
import {
  Bell,
  Check,
  CheckCheck,
  Filter,
  Inbox,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  Briefcase,
  Calendar,
  Gift,
  Megaphone,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { EmptyState } from "@/components/shared/EmptyState";

// ---------------------------------------------------------------------------
// 类型 & Mock 数据
// ---------------------------------------------------------------------------

type NotificationCategory =
  | "matching"
  | "interview"
  | "offer"
  | "subscription"
  | "system"
  | "marketing";

type NotificationPriority = "urgent" | "high" | "normal" | "low";

interface AppNotification {
  id: string;
  category: NotificationCategory;
  title: string;
  body: string;
  createdAt: string; // ISO
  read: boolean;
  priority: NotificationPriority;
  href?: string;
  actor?: string;
}

const CATEGORY_META: Record<
  NotificationCategory,
  { label: string; icon: LucideIcon; tone: string; ring: string }
> = {
  matching: {
    label: "匹配",
    icon: Sparkles,
    tone: "bg-indigo-50 text-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-300",
    ring: "ring-indigo-200/60 dark:ring-indigo-900",
  },
  interview: {
    label: "面试",
    icon: Calendar,
    tone: "bg-sky-50 text-sky-600 dark:bg-sky-950/40 dark:text-sky-300",
    ring: "ring-sky-200/60 dark:ring-sky-900",
  },
  offer: {
    label: "Offer",
    icon: Gift,
    tone: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300",
    ring: "ring-emerald-200/60 dark:ring-emerald-900",
  },
  subscription: {
    label: "订阅",
    icon: Briefcase,
    tone: "bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300",
    ring: "ring-amber-200/60 dark:ring-amber-900",
  },
  system: {
    label: "系统",
    icon: ShieldAlert,
    tone: "bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-300",
    ring: "ring-rose-200/60 dark:ring-rose-900",
  },
  marketing: {
    label: "营销",
    icon: Megaphone,
    tone: "bg-slate-50 text-slate-600 dark:bg-slate-900/40 dark:text-slate-300",
    ring: "ring-slate-200/60 dark:ring-slate-800",
  },
};

const PRIORITY_META: Record<
  NotificationPriority,
  { label: string; cls: string }
> = {
  urgent: { label: "紧急", cls: "bg-rose-600 text-white" },
  high: { label: "高", cls: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300" },
  normal: { label: "常规", cls: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" },
  low: { label: "低", cls: "bg-slate-50 text-slate-500 dark:bg-slate-900 dark:text-slate-400" },
};

const SEED: AppNotification[] = [
  {
    id: "n-001",
    category: "matching",
    title: "新增 3 个高匹配岗位",
    body: "基于你近 7 天更新的技能画像,Acme AI 招聘的「高级前端工程师」综合得分 92。",
    createdAt: "2026-07-13T08:12:00Z",
    read: false,
    priority: "high",
    href: "/match",
    actor: "AI 匹配引擎",
  },
  {
    id: "n-002",
    category: "interview",
    title: "Lina · 招聘顾问 邀请你 1:1 视频沟通",
    body: "时间:07/14 (周二) 15:00 - 15:30 · 议题:为你推荐的 Senior Frontend 岗位。",
    createdAt: "2026-07-12T22:30:00Z",
    read: false,
    priority: "urgent",
    href: "/interview",
    actor: "Lina Chen",
  },
  {
    id: "n-003",
    category: "offer",
    title: "Bluefin 发送了 Offer 草稿",
    body: "Base £85k + RSU 1,200 · 请在 7 天内确认或协商。",
    createdAt: "2026-07-12T14:08:00Z",
    read: false,
    priority: "high",
    href: "/offers",
    actor: "Bluefin Talent",
  },
  {
    id: "n-004",
    category: "subscription",
    title: "你的「伦敦 · React 远程」订阅新增 2 个匹配",
    body: "Northern Stack · Mid-Senior 远程岗位,综合得分 88。",
    createdAt: "2026-07-11T09:15:00Z",
    read: true,
    priority: "normal",
    href: "/jobseeker/subscriptions",
  },
  {
    id: "n-005",
    category: "system",
    title: "账户安全提示",
    body: "你的账户在新设备 (Mac · London) 登录。如非本人操作请立即修改密码。",
    createdAt: "2026-07-10T03:42:00Z",
    read: true,
    priority: "high",
    href: "/jobseeker/account",
  },
  {
    id: "n-006",
    category: "marketing",
    title: "本周精选:英国 Tech 行业薪资报告",
    body: "2026 H1 英国中位薪资同比 +6.2%,Frontend 涨幅领先。",
    createdAt: "2026-07-09T11:00:00Z",
    read: true,
    priority: "low",
  },
  {
    id: "n-007",
    category: "matching",
    title: "档案完整度达到 92%",
    body: "再补充 1 项「期望薪资」即可解锁「高级匹配」特权。",
    createdAt: "2026-07-08T07:20:00Z",
    read: true,
    priority: "low",
    href: "/jobseeker/profile",
  },
  {
    id: "n-008",
    category: "subscription",
    title: "「苏黎世 · 后端 · €120k+」订阅已暂停",
    body: "因 30 天内无匹配,系统自动暂停以节省推送额度。可在订阅页恢复。",
    createdAt: "2026-07-07T18:00:00Z",
    read: false,
    priority: "normal",
    href: "/jobseeker/subscriptions",
  },
];

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

const STORAGE_KEY = "v9.1.jobseeker.notifications";

function formatRelative(iso: string, now: number): string {
  const t = new Date(iso).getTime();
  const diff = Math.max(0, now - t);
  const m = Math.floor(diff / 60_000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
  });
}

function isToday(iso: string, now: number): boolean {
  const a = new Date(iso);
  const b = new Date(now);
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

type FilterTab = "all" | "unread" | NotificationCategory;

export default function NotificationsPage() {
  // 客户端 state;首次渲染用 SEED,挂载后从 localStorage 合并
  const [items, setItems] = React.useState<AppNotification[]>(SEED);
  const [hydrated, setHydrated] = React.useState(false);
  const [filter, setFilter] = React.useState<FilterTab>("all");
  const [query, setQuery] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  // 渲染时的"当前时间"快照,确保多次渲染结果一致 (符合 React 19 纯函数规则)
  const [now] = React.useState<number>(() => Date.now());

  React.useEffect(() => {
    try {
      const raw =
        typeof window !== "undefined"
          ? window.localStorage.getItem(STORAGE_KEY)
          : null;
      if (raw) {
        const parsed = JSON.parse(raw) as AppNotification[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setItems(parsed);
        }
      }
    } catch {
      /* ignore */
    } finally {
      setHydrated(true);
    }
  }, []);

  React.useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {
      /* ignore quota */
    }
  }, [items, hydrated]);

  // 派生统计
  const stats = React.useMemo(() => {
    const unread = items.filter((i) => !i.read).length;
    const urgent = items.filter(
      (i) => !i.read && (i.priority === "urgent" || i.priority === "high"),
    ).length;
    const today = items.filter((i) => isToday(i.createdAt, now)).length;
    return { unread, urgent, today, total: items.length };
  }, [items, now]);

  // 过滤
  const visible = React.useMemo(() => {
    let list = items;
    if (filter === "unread") list = list.filter((i) => !i.read);
    else if (filter !== "all") list = list.filter((i) => i.category === filter);
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter(
        (i) =>
          i.title.toLowerCase().includes(q) ||
          i.body.toLowerCase().includes(q) ||
          (i.actor?.toLowerCase().includes(q) ?? false),
      );
    }
    return list;
  }, [items, filter, query]);

  // 操作
  const markRead = React.useCallback((id: string, read: boolean) => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, read } : i)));
  }, []);

  const remove = React.useCallback((id: string) => {
    setItems((prev) => prev.filter((i) => i.id !== id));
    setSelected((s) => {
      if (!s.has(id)) return s;
      const n = new Set(s);
      n.delete(id);
      return n;
    });
  }, []);

  const markAllRead = React.useCallback(() => {
    setItems((prev) => prev.map((i) => ({ ...i, read: true })));
  }, []);

  const clearRead = React.useCallback(() => {
    setItems((prev) => prev.filter((i) => !i.read));
  }, []);

  const toggleSelect = React.useCallback((id: string) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }, []);

  const bulkMarkRead = React.useCallback(() => {
    setItems((prev) =>
      prev.map((i) => (selected.has(i.id) ? { ...i, read: true } : i)),
    );
    setSelected(new Set());
  }, [selected]);

  const bulkDelete = React.useCallback(() => {
    setItems((prev) => prev.filter((i) => !selected.has(i.id)));
    setSelected(new Set());
  }, [selected]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
      {/* 顶部 */}
      <header className="mb-6 sm:mb-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              <Bell className="size-3.5" aria-hidden="true" />
              通知中心
            </div>
            <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
              你的消息
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              集中查看来自匹配、面试、Offer、订阅和系统的所有通知。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href="/jobseeker/account/notifications-prefs">
                <Settings2 className="mr-1.5 size-4" aria-hidden="true" />
                通知偏好
              </Link>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={markAllRead}
              disabled={stats.unread === 0}
            >
              <CheckCheck className="mr-1.5 size-4" aria-hidden="true" />
              全部已读
            </Button>
          </div>
        </div>
      </header>

      {/* KPI 卡 */}
      <section
        aria-label="通知统计概览"
        className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4"
      >
        <KpiTile
          label="未读"
          value={stats.unread}
          tone="indigo"
          icon={Inbox}
        />
        <KpiTile
          label="紧急 / 重要"
          value={stats.urgent}
          tone="rose"
          icon={ShieldAlert}
        />
        <KpiTile
          label="今日新增"
          value={stats.today}
          tone="emerald"
          icon={Bell}
        />
        <KpiTile
          label="累计"
          value={stats.total}
          tone="slate"
          icon={Sparkles}
        />
      </section>

      {/* 筛选 + 搜索 */}
      <Card className="mb-4">
        <CardContent className="space-y-4 p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 sm:max-w-xs">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索标题、内容或发送人"
                className="pl-9"
                aria-label="搜索通知"
              />
            </div>
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <Filter className="size-3.5" aria-hidden="true" />
              <span>共 {visible.length} 条 · 已选 {selected.size} 条</span>
              {selected.size > 0 && (
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={bulkMarkRead}
                    className="h-7 px-2"
                  >
                    <Check className="mr-1 size-3.5" aria-hidden="true" />
                    标为已读
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={bulkDelete}
                    className="h-7 px-2 text-rose-600 hover:text-rose-700"
                  >
                    <Trash2 className="mr-1 size-3.5" aria-hidden="true" />
                    删除
                  </Button>
                </>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={clearRead}
                className="h-7 px-2"
                disabled={stats.total - stats.unread === 0}
              >
                清理已读
              </Button>
            </div>
          </div>

          <Tabs
            value={filter}
            onValueChange={(v) => setFilter(v as FilterTab)}
            className="w-full"
          >
            <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1 bg-transparent p-0">
              <FilterChip value="all" label="全部" count={items.length} />
              <FilterChip
                value="unread"
                label="未读"
                count={stats.unread}
                accent
              />
              <FilterChip
                value="matching"
                label={CATEGORY_META.matching.label}
                count={items.filter((i) => i.category === "matching").length}
                icon={CATEGORY_META.matching.icon}
              />
              <FilterChip
                value="interview"
                label={CATEGORY_META.interview.label}
                count={items.filter((i) => i.category === "interview").length}
                icon={CATEGORY_META.interview.icon}
              />
              <FilterChip
                value="offer"
                label={CATEGORY_META.offer.label}
                count={items.filter((i) => i.category === "offer").length}
                icon={CATEGORY_META.offer.icon}
              />
              <FilterChip
                value="subscription"
                label={CATEGORY_META.subscription.label}
                count={
                  items.filter((i) => i.category === "subscription").length
                }
                icon={CATEGORY_META.subscription.icon}
              />
              <FilterChip
                value="system"
                label={CATEGORY_META.system.label}
                count={items.filter((i) => i.category === "system").length}
                icon={CATEGORY_META.system.icon}
              />
              <FilterChip
                value="marketing"
                label={CATEGORY_META.marketing.label}
                count={items.filter((i) => i.category === "marketing").length}
                icon={CATEGORY_META.marketing.icon}
              />
            </TabsList>
          </Tabs>
        </CardContent>
      </Card>

      {/* 列表 */}
      {!hydrated ? (
        <SkeletonList />
      ) : visible.length === 0 ? (
        <EmptyState
          title="这里很安静"
          description="没有匹配的通知。可以调整上方筛选,或去订阅页设置推送偏好。"
          icon={<Bell className="size-6" />}
          action={
            <Button asChild>
              <Link href="/jobseeker/account/notifications-prefs">
                <Settings2 className="mr-1.5 size-4" aria-hidden="true" />
                调整通知偏好
              </Link>
            </Button>
          }
        />
      ) : (
        <ul className="space-y-2.5" role="list" aria-label="通知列表">
          {visible.map((n) => (
            <NotificationItem
              key={n.id}
              item={n}
              now={now}
              checked={selected.has(n.id)}
              onToggleSelect={() => toggleSelect(n.id)}
              onMarkRead={(read) => markRead(n.id, read)}
              onRemove={() => remove(n.id)}
            />
          ))}
        </ul>
      )}

      <Separator className="my-8" />

      {/* 页脚提示 */}
      <Card className="border-dashed bg-muted/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">通知太频繁?</CardTitle>
          <CardDescription>
            前往「通知偏好」可按 类别 × 优先级 × 通道 精细控制,也能设置免打扰时间。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link href="/jobseeker/account/notifications-prefs">
              打开通知偏好
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href="/jobseeker/subscriptions">管理订阅</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function KpiTile({
  label,
  value,
  tone,
  icon: Icon,
}: {
  label: string;
  value: number;
  tone: "indigo" | "rose" | "emerald" | "slate";
  icon: LucideIcon;
}) {
  const toneCls: Record<typeof tone, string> = {
    indigo:
      "bg-indigo-50 text-indigo-700 ring-indigo-200/60 dark:bg-indigo-950/40 dark:text-indigo-300 dark:ring-indigo-900",
    rose: "bg-rose-50 text-rose-700 ring-rose-200/60 dark:bg-rose-950/40 dark:text-rose-300 dark:ring-rose-900",
    emerald:
      "bg-emerald-50 text-emerald-700 ring-emerald-200/60 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900",
    slate:
      "bg-slate-50 text-slate-700 ring-slate-200/60 dark:bg-slate-900/40 dark:text-slate-300 dark:ring-slate-800",
  };
  return (
    <div
      className={cn(
        "rounded-xl p-3 ring-1 sm:p-4",
        toneCls[tone],
      )}
      role="status"
      aria-label={`${label}: ${value}`}
    >
      <div className="flex items-center justify-between text-xs sm:text-sm">
        <span className="font-medium opacity-80">{label}</span>
        <Icon className="size-4 opacity-70" aria-hidden="true" />
      </div>
      <p className="mt-1.5 text-2xl font-bold tabular-nums sm:text-3xl">
        {value}
      </p>
    </div>
  );
}

function FilterChip({
  value,
  label,
  count,
  icon: Icon,
  accent,
}: {
  value: FilterTab;
  label: string;
  count: number;
  icon?: LucideIcon;
  accent?: boolean;
}) {
  return (
    <TabsTrigger
      value={value}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-full border border-transparent bg-muted px-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/80 data-[state=active]:border-primary/40 data-[state=active]:bg-primary/10 data-[state=active]:text-primary",
        accent &&
          "data-[state=active]:bg-rose-100 data-[state=active]:text-rose-700 data-[state=active]:border-rose-300/60",
      )}
    >
      {Icon ? <Icon className="size-3.5" aria-hidden="true" /> : null}
      <span>{label}</span>
      <span
        className={cn(
          "ml-0.5 rounded-full bg-background/60 px-1.5 py-0.5 text-[10px] tabular-nums",
          "group-data-[state=active]:bg-background/80",
        )}
      >
        {count}
      </span>
    </TabsTrigger>
  );
}

function NotificationItem({
  item,
  now,
  checked,
  onToggleSelect,
  onMarkRead,
  onRemove,
}: {
  item: AppNotification;
  now: number;
  checked: boolean;
  onToggleSelect: () => void;
  onMarkRead: (read: boolean) => void;
  onRemove: () => void;
}) {
  const meta = CATEGORY_META[item.category];
  const prio = PRIORITY_META[item.priority];
  const Icon = meta.icon;

  const handleOpen = () => {
    onMarkRead(true);
    if (item.href && typeof window !== "undefined") {
      window.location.href = item.href;
    }
  };

  return (
    <li
      role="listitem"
      className={cn(
        "group relative flex gap-3 rounded-xl border bg-card p-3 transition-colors sm:p-4",
        !item.read
          ? "border-primary/30 bg-primary/[0.025] dark:border-primary/30 dark:bg-primary/[0.04]"
          : "border-border hover:bg-muted/30",
      )}
    >
      {/* 未读小红点 */}
      <span
        className={cn(
          "absolute left-1.5 top-1/2 size-2 -translate-y-1/2 rounded-full transition-opacity sm:left-2",
          item.read ? "opacity-0" : "bg-primary opacity-100",
        )}
        aria-hidden="true"
      />

      {/* 类别图标 */}
      <div
        className={cn(
          "grid size-10 shrink-0 place-items-center rounded-full ring-1 sm:size-11",
          meta.tone,
          meta.ring,
        )}
        aria-hidden="true"
      >
        <Icon className="size-4 sm:size-5" />
      </div>

      {/* 主体 */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
            {meta.label}
          </Badge>
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-medium",
              prio.cls,
            )}
          >
            {prio.label}
          </span>
          <span className="text-xs text-muted-foreground">
            {formatRelative(item.createdAt, now)}
          </span>
        </div>
        <h3
          className={cn(
            "mt-1.5 text-sm font-semibold sm:text-base",
            !item.read && "text-foreground",
          )}
        >
          {item.title}
        </h3>
        <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground sm:text-sm">
          {item.body}
        </p>
        {item.actor && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            来自 · {item.actor}
          </p>
        )}
      </div>

      {/* 操作 */}
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <label className="flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground sm:hidden">
          <input
            type="checkbox"
            checked={checked}
            onChange={onToggleSelect}
            className="size-3.5 accent-primary"
            aria-label={`选中「${item.title}」`}
          />
        </label>
        <label className="hidden cursor-pointer items-center gap-1 text-[11px] text-muted-foreground sm:flex">
          <input
            type="checkbox"
            checked={checked}
            onChange={onToggleSelect}
            className="size-3.5 accent-primary"
            aria-label={`选中「${item.title}」`}
          />
          选中
        </label>
        <div className="flex gap-1">
          {!item.read && (
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              onClick={() => onMarkRead(true)}
              aria-label="标为已读"
              title="标为已读"
            >
              <Check className="size-3.5" aria-hidden="true" />
            </Button>
          )}
          {item.href && (
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              onClick={handleOpen}
              aria-label="查看详情"
              title="查看详情"
            >
              <span className="text-xs">查看</span>
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            className="size-7 text-rose-600 hover:text-rose-700"
            onClick={onRemove}
            aria-label="删除通知"
            title="删除"
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </li>
  );
}

function SkeletonList() {
  return (
    <ul className="space-y-2.5" aria-label="加载中" aria-busy="true">
      {Array.from({ length: 5 }).map((_, i) => (
        <li
          key={i}
          className="flex gap-3 rounded-xl border bg-card p-3 sm:p-4"
        >
          <Skeleton className="size-10 rounded-full sm:size-11" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-full" />
          </div>
        </li>
      ))}
    </ul>
  );
}

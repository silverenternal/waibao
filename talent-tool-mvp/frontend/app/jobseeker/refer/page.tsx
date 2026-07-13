"use client";

/**
 * 求职者 — 内部推荐 (v9.1 Jobseeker 辅助模块)
 *
 * 功能:
 *   - 推荐候选人表单 (姓名 / 邮箱 / 岗位 / 渠道 / 推荐理由)
 *   - 积分 & 奖金展示 (累计推荐 / 成功入职 / 总积分 / 累计奖励)
 *   - 推荐达人榜
 *   - 奖励规则说明 (现金 + 积分 + 加成)
 *   - 中文精致排版 · 响应式 · 可访问
 */

import * as React from "react";
import {
  AlertCircle,
  ArrowLeft,
  Award,
  CheckCircle2,
  CircleDollarSign,
  Gift,
  Loader2,
  Mail,
  Send,
  Sparkles,
  Star,
  Trophy,
  User as UserIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ReferralLeaderboard } from "@/components/referrals/ReferralLeaderboard";
import {
  createReferral,
  fetchMyReferrals,
  type MyReferrals,
  REFERRAL_STATUS_LABEL,
  REFERRAL_STATUS_COLOR,
} from "@/lib/api-referrals";

interface FormState {
  candidate_email: string;
  candidate_name: string;
  job_title: string;
  channel: "wechat" | "linkedin" | "referral" | "other";
  notes: string;
}

const CHANNEL_LABEL: Record<FormState["channel"], string> = {
  wechat: "微信",
  linkedin: "LinkedIn",
  referral: "朋友介绍",
  other: "其他",
};

const BONUS_TIERS = [
  {
    icon: <CircleDollarSign className="size-5 text-emerald-600" />,
    title: "入职现金奖",
    amount: "¥5,000",
    desc: "候选人通过试用期后,奖金随当月工资发放。",
  },
  {
    icon: <Sparkles className="size-5 text-amber-600" />,
    title: "即时积分",
    amount: "+100 分",
    desc: "提交推荐即得。面试推进、Offer 阶段有额外加成。",
  },
  {
    icon: <Trophy className="size-5 text-violet-600" />,
    title: "年度排行",
    amount: "Top 10",
    desc: "全年推荐积分 Top 10 享额外团建基金 + 神秘大奖。",
  },
];

export default function ReferPage() {
  const [summary, setSummary] = React.useState<MyReferrals | null>(null);
  const [form, setForm] = React.useState<FormState>({
    candidate_email: "",
    candidate_name: "",
    job_title: "",
    channel: "wechat",
    notes: "",
  });
  const [submitting, setSubmitting] = React.useState(false);
  const [feedback, setFeedback] = React.useState<
    | { kind: "success"; message: string }
    | { kind: "error"; message: string }
    | null
  >(null);

  const refresh = React.useCallback(async () => {
    try {
      setSummary(await fetchMyReferrals());
    } catch (e) {
      console.error(e);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const emailValid = React.useMemo(() => {
    if (!form.candidate_email) return null;
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.candidate_email.trim());
  }, [form.candidate_email]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    if (!form.candidate_email || emailValid === false) {
      setFeedback({ kind: "error", message: "请填写有效的候选人邮箱" });
      return;
    }
    setSubmitting(true);
    try {
      await createReferral({
        candidate_email: form.candidate_email.trim(),
        candidate_name: form.candidate_name.trim() || undefined,
        job_title: form.job_title.trim() || undefined,
        notes: `${CHANNEL_LABEL[form.channel]} · ${form.notes}`.trim(),
      });
      setFeedback({
        kind: "success",
        message: "推荐已提交!立即到账 +100 积分,候选人入职后再获 ¥5,000 奖金。",
      });
      setForm({
        candidate_email: "",
        candidate_name: "",
        job_title: "",
        channel: "wechat",
        notes: "",
      });
      void refresh();
    } catch (e: unknown) {
      setFeedback({
        kind: "error",
        message: e instanceof Error ? e.message : "提交失败,请稍后重试",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50">
      {/* 顶部 */}
      <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => history.back()}
            aria-label="返回上一页"
          >
            <ArrowLeft className="size-4" />
          </Button>
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
              <span
                aria-hidden
                className="inline-flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-rose-500 text-white shadow-sm"
              >
                <Gift className="size-4" />
              </span>
              推荐候选人
            </h1>
            <p className="text-xs text-slate-500">
              成功推荐入职 — 立得积分 + 入职奖金双重奖励
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:py-8">
        {/* ============== Hero: 三层奖励 ============== */}
        <section
          aria-labelledby="bonus-heading"
          className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="bonus-heading" className="flex items-center gap-2 text-base font-semibold text-slate-900">
              <Award className="size-4 text-amber-500" />
              奖励机制
            </h2>
            <Badge variant="secondary" className="gap-1">
              <Star className="size-3 text-amber-500" /> 限时双倍积分
            </Badge>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {BONUS_TIERS.map((tier) => (
              <div
                key={tier.title}
                className="rounded-xl border border-slate-200/70 bg-gradient-to-br from-white to-slate-50 p-4 transition-shadow hover:shadow-sm"
              >
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="inline-flex size-9 items-center justify-center rounded-lg bg-slate-100"
                  >
                    {tier.icon}
                  </span>
                  <h3 className="text-sm font-semibold text-slate-800">
                    {tier.title}
                  </h3>
                </div>
                <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
                  {tier.amount}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">
                  {tier.desc}
                </p>
              </div>
            ))}
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* ============== 表单 ============== */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Send className="size-4 text-blue-500" />
                  推荐一位候选人
                </CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={submit} className="space-y-4" noValidate>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {/* Email */}
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="email">
                        候选人邮箱 <span className="text-rose-500">*</span>
                      </Label>
                      <div className="relative">
                        <Mail
                          aria-hidden
                          className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                        />
                        <Input
                          id="email"
                          type="email"
                          required
                          value={form.candidate_email}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              candidate_email: e.target.value,
                            }))
                          }
                          className="pl-8"
                          placeholder="name@example.com"
                          aria-invalid={emailValid === false}
                          aria-describedby="email-help"
                        />
                      </div>
                      <p
                        id="email-help"
                        className={cn(
                          "text-xs",
                          emailValid === false
                            ? "text-rose-600"
                            : "text-slate-400",
                        )}
                      >
                        {emailValid === false
                          ? "邮箱格式不正确"
                          : "我们会通过邮件联系候选人,请确保可送达"}
                      </p>
                    </div>

                    {/* Name */}
                    <div className="space-y-1.5">
                      <Label htmlFor="name">候选人姓名</Label>
                      <div className="relative">
                        <UserIcon
                          aria-hidden
                          className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                        />
                        <Input
                          id="name"
                          value={form.candidate_name}
                          onChange={(e) =>
                            setForm((f) => ({
                              ...f,
                              candidate_name: e.target.value,
                            }))
                          }
                          className="pl-8"
                          placeholder="选填,便于 HR 称呼"
                        />
                      </div>
                    </div>

                    {/* Job Title */}
                    <div className="space-y-1.5">
                      <Label htmlFor="job">推荐岗位</Label>
                      <Input
                        id="job"
                        value={form.job_title}
                        onChange={(e) =>
                          setForm((f) => ({
                            ...f,
                            job_title: e.target.value,
                          }))
                        }
                        placeholder="如:高级前端工程师"
                      />
                    </div>
                  </div>

                  {/* Channel */}
                  <fieldset className="space-y-2">
                    <legend className="text-sm font-medium text-slate-700">
                      推荐渠道
                    </legend>
                    <div className="flex flex-wrap gap-2">
                      {(Object.keys(CHANNEL_LABEL) as FormState["channel"][]).map(
                        (c) => (
                          <label
                            key={c}
                            className={cn(
                              "inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors",
                              form.channel === c
                                ? "border-slate-900 bg-slate-900 text-white"
                                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300",
                            )}
                          >
                            <input
                              type="radio"
                              name="channel"
                              value={c}
                              checked={form.channel === c}
                              onChange={() =>
                                setForm((f) => ({ ...f, channel: c }))
                              }
                              className="sr-only"
                            />
                            {CHANNEL_LABEL[c]}
                          </label>
                        ),
                      )}
                    </div>
                  </fieldset>

                  {/* Notes */}
                  <div className="space-y-1.5">
                    <Label htmlFor="notes">推荐理由</Label>
                    <Textarea
                      id="notes"
                      rows={4}
                      value={form.notes}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, notes: e.target.value }))
                      }
                      placeholder="为什么推荐?亮点 / 项目 / 性格 / 与岗位的匹配度……"
                      maxLength={2000}
                      className="resize-y"
                    />
                    <p className="text-right text-[11px] text-slate-400 tabular-nums">
                      {form.notes.length} / 2000
                    </p>
                  </div>

                  {/* Feedback */}
                  {feedback && (
                    <div
                      role="alert"
                      className={cn(
                        "flex items-start gap-2 rounded-lg border p-3 text-sm",
                        feedback.kind === "success"
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                          : "border-rose-200 bg-rose-50 text-rose-700",
                      )}
                    >
                      {feedback.kind === "success" ? (
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
                      ) : (
                        <AlertCircle className="mt-0.5 size-4 shrink-0" />
                      )}
                      <span>{feedback.message}</span>
                    </div>
                  )}

                  <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
                    <p className="text-xs text-slate-400">
                      提交后 HR 会在 3 个工作日内联系候选人
                    </p>
                    <Button
                      type="submit"
                      disabled={submitting || emailValid === false}
                      className="min-w-[140px] gap-1.5"
                    >
                      {submitting ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Send className="size-4" />
                      )}
                      {submitting ? "提交中…" : "提交推荐"}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            {/* 我的推荐数据 */}
            {summary && (
              <Card className="mt-6">
                <CardHeader>
                  <CardTitle className="text-base">我的推荐数据</CardTitle>
                </CardHeader>
                <CardContent>
                  <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <SummaryStat
                      label="累计推荐"
                      value={summary.total_referrals}
                      tone="default"
                    />
                    <SummaryStat
                      label="成功入职"
                      value={summary.successful_hires}
                      tone="success"
                    />
                    <SummaryStat
                      label="总积分"
                      value={summary.total_points}
                      suffix="分"
                      tone="warning"
                    />
                    <SummaryStat
                      label="累计奖励"
                      value={`¥${summary.rewards_earned.toLocaleString()}`}
                      tone="primary"
                    />
                  </dl>

                  {Object.keys(summary.status_breakdown ?? {}).length > 0 && (
                    <div className="mt-4 border-t border-slate-100 pt-3">
                      <p className="mb-2 text-xs font-medium text-slate-500">
                        状态分布
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(summary.status_breakdown).map(
                          ([status, count]) => (
                            <Badge
                              key={status}
                              variant="outline"
                              className={cn(
                                "border gap-1",
                                REFERRAL_STATUS_COLOR[status] ?? "bg-slate-100 text-slate-700",
                              )}
                            >
                              {REFERRAL_STATUS_LABEL[status] ?? status}
                              <span className="ml-1 opacity-70 tabular-nums">
                                {count}
                              </span>
                            </Badge>
                          ),
                        )}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          {/* ============== 侧栏: 排行榜 + 流程 ============== */}
          <aside className="space-y-6">
            <ReferralLeaderboard />

            <Card>
              <CardHeader>
                <CardTitle className="text-base">推荐流程</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="space-y-3 text-sm">
                  {[
                    { t: "提交推荐", d: "立即获得 +100 积分" },
                    { t: "HR 初筛", d: "3 个工作日内反馈" },
                    { t: "面试推进", d: "每通过一轮 +50 分" },
                    { t: "发放 offer", d: "额外 +200 分" },
                    { t: "成功入职", d: "¥5,000 现金奖 + 500 分" },
                  ].map((s, i) => (
                    <li key={s.t} className="flex gap-3">
                      <span
                        aria-hidden
                        className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700"
                      >
                        {i + 1}
                      </span>
                      <div className="min-w-0">
                        <p className="font-medium text-slate-800">{s.t}</p>
                        <p className="text-xs text-slate-500">{s.d}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </aside>
        </div>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function SummaryStat({
  label,
  value,
  suffix,
  tone,
}: {
  label: string;
  value: string | number;
  suffix?: string;
  tone: "default" | "success" | "warning" | "primary";
}) {
  const toneClass = {
    default: "text-slate-900",
    success: "text-emerald-600",
    warning: "text-amber-600",
    primary: "text-blue-600",
  }[tone];

  return (
    <div className="rounded-lg border border-slate-200/70 bg-white px-3 py-2.5">
      <dt className="text-[11px] uppercase tracking-wide text-slate-400">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 text-2xl font-bold tabular-nums tracking-tight",
          toneClass,
        )}
      >
        {value}
        {suffix && (
          <span className="ml-0.5 text-sm font-medium text-slate-500">
            {suffix}
          </span>
        )}
      </dd>
    </div>
  );
}
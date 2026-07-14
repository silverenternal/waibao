"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ReferralLeaderboard } from "@/components/referrals/ReferralLeaderboard";
import {
  createReferral,
  fetchMyReferrals,
  type MyReferrals,
} from "@/lib/api-referrals";

/**
 * 员工推荐候选人 — 我的推荐 + 提交流程 (T2405).
 */
export default function ReferPage() {
  const [summary, setSummary] = React.useState<MyReferrals | null>(null);
  const [form, setForm] = React.useState({
    candidate_email: "",
    candidate_name: "",
    job_title: "",
    notes: "",
  });
  const [submitting, setSubmitting] = React.useState(false);
  const [success, setSuccess] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    try {
      setSummary(await fetchMyReferrals());
    } catch (e) {
      console.error(e);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const submit = async () => {
    setError(null);
    setSuccess(false);
    if (!form.candidate_email) {
      setError("候选人邮箱必填");
      return;
    }
    setSubmitting(true);
    try {
      await createReferral(form);
      setSuccess(true);
      setForm({ candidate_email: "", candidate_name: "", job_title: "", notes: "" });
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ErrorBoundary>(<div className="container mx-auto p-6 space-y-6">
        <h1 className="text-2xl font-bold">推荐候选人</h1>
        <p className="text-sm text-slate-500">
          成功推荐入职, 您将获得 ¥5,000 现金 + 100 积分奖励。
        </p>
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>推荐候选人</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <label className="text-sm text-slate-700 block mb-1">
                    候选人邮箱 *
                  </label>
                  <input
                    type="email"
                    value={form.candidate_email}
                    onChange={(e) => setForm((f) => ({ ...f, candidate_email: e.target.value }))}
                    className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
                    placeholder="name@example.com"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-700 block mb-1">候选人姓名</label>
                  <input
                    type="text"
                    value={form.candidate_name}
                    onChange={(e) => setForm((f) => ({ ...f, candidate_name: e.target.value }))}
                    className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-700 block mb-1">推荐岗位</label>
                  <input
                    type="text"
                    value={form.job_title}
                    onChange={(e) => setForm((f) => ({ ...f, job_title: e.target.value }))}
                    className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
                    placeholder="如: 高级前端工程师"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-700 block mb-1">推荐理由</label>
                  <textarea
                    rows={3}
                    value={form.notes}
                    onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                    className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
                    placeholder="为什么推荐? 亮点 / 项目 / 性格…"
                  />
                </div>

                {error && (
                  <p className="text-sm text-rose-600 bg-rose-50 px-3 py-2 rounded">{error}</p>
                )}
                {success && (
                  <p className="text-sm text-emerald-600 bg-emerald-50 px-3 py-2 rounded">
                    推荐提交成功, 已奖励 +5 积分。
                  </p>
                )}

                <Button disabled={submitting} onClick={submit}>
                  {submitting ? "提交中…" : "提交推荐"}
                </Button>
              </CardContent>
            </Card>

            {summary && (
              <Card>
                <CardHeader>
                  <CardTitle>我的推荐数据</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <p className="text-slate-500 text-xs">累计推荐</p>
                      <p className="text-2xl font-bold">{summary.total_referrals}</p>
                    </div>
                    <div>
                      <p className="text-slate-500 text-xs">成功入职</p>
                      <p className="text-2xl font-bold text-emerald-600">{summary.successful_hires}</p>
                    </div>
                    <div>
                      <p className="text-slate-500 text-xs">总积分</p>
                      <p className="text-2xl font-bold text-amber-600">{summary.total_points}</p>
                    </div>
                    <div>
                      <p className="text-slate-500 text-xs">累计奖励</p>
                      <p className="text-2xl font-bold">¥{summary.rewards_earned.toLocaleString()}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          <div>
            <ReferralLeaderboard />
          </div>
        </div>
      </div>)</ErrorBoundary>
  );
}

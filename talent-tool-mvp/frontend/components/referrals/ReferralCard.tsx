"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  REFERRAL_STATUS_COLOR,
  REFERRAL_STATUS_LABEL,
  reviewReferral,
  type ReferralItem,
} from "@/lib/api-referrals";

export interface ReferralCardProps {
  referral: ReferralItem;
  hrView?: boolean;
  onReviewed?: (referralId: string, targetStatus: string) => void;
}

/**
 * 单条推荐卡片.
 */
export function ReferralCard({ referral, hrView, onReviewed }: ReferralCardProps) {
  const [busy, setBusy] = React.useState<string | null>(null);

  const nextStatuses = hrView
    ? ["reviewed", "interview", "offered", "hired", "rewarded", "rejected"]
    : [];

  const advance = async (target: string) => {
    setBusy(target);
    try {
      await reviewReferral(referral.id, target);
      onReviewed?.(referral.id, target);
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">
            {referral.candidate_name || referral.candidate_email}
          </CardTitle>
          <span
            className={`px-2 py-1 rounded text-xs font-medium ${REFERRAL_STATUS_COLOR[referral.status]}`}
          >
            {REFERRAL_STATUS_LABEL[referral.status]}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-slate-600">{referral.candidate_email}</p>
        {referral.job_title && (
          <p className="text-slate-500 text-xs">岗位: {referral.job_title}</p>
        )}
        {referral.referrer_name && hrView && (
          <p className="text-xs text-slate-500">推荐人: {referral.referrer_name}</p>
        )}
        <p className="text-xs text-slate-400">
          提交时间: {new Date(referral.created_at).toLocaleString("zh-CN")}
        </p>
        {referral.bonus_amount && referral.bonus_amount > 0 && (
          <p className="text-sm font-medium text-emerald-600">
            奖励: ¥{referral.bonus_amount.toLocaleString()}
          </p>
        )}
        {hrView && nextStatuses.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-2">
            {nextStatuses.map((s) => (
              <Button
                key={s}
                size="sm"
                variant="outline"
                disabled={busy === s}
                onClick={() => advance(s)}
              >
                {REFERRAL_STATUS_LABEL[s]}
              </Button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

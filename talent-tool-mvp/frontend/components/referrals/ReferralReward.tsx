"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { rewardReferral } from "@/lib/api-referrals";

export interface ReferralRewardProps {
  referralId: string;
  defaultAmount?: number;
  onRewarded?: () => void;
}

/**
 * 推荐奖励卡片 — 现金 + 积分 (T2405).
 */
export function ReferralReward({
  referralId,
  defaultAmount = 5000,
  onRewarded,
}: ReferralRewardProps) {
  const [amount, setAmount] = React.useState(defaultAmount);
  const [busy, setBusy] = React.useState(false);
  const [done, setDone] = React.useState(false);

  const claim = async () => {
    setBusy(true);
    try {
      await rewardReferral(referralId, amount);
      setDone(true);
      onRewarded?.();
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <Card>
        <CardContent className="py-6 text-center">
          <p className="text-lg font-semibold text-emerald-600">奖励已发放</p>
          <p className="text-sm text-slate-500 mt-1">¥{amount.toLocaleString()} + 100 积分</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">推荐奖励</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-slate-600">
          候选人已入职, 您将获得以下奖励:
        </p>
        <ul className="text-sm space-y-1 text-slate-700">
          <li>现金: ¥{amount.toLocaleString()}</li>
          <li>积分: +100 (可兑换)</li>
        </ul>
        <div className="flex items-center gap-2 pt-2">
          <label className="text-xs text-slate-500">调整金额:</label>
          <input
            type="number"
            value={amount}
            min={0}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="w-24 rounded border border-slate-300 px-2 py-1 text-sm"
          />
        </div>
        <Button disabled={busy} onClick={claim}>
          {busy ? "发放中…" : "确认发放"}
        </Button>
      </CardContent>
    </Card>
  );
}

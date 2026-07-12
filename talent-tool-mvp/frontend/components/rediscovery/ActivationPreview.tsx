"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { activateCandidate, type ActivationPreview } from "@/lib/api-rediscovery";

export interface ActivationPreviewProps {
  candidateId: string;
  initialPreview?: ActivationPreview;
  onActivated?: () => void;
}

/**
 * 激活预览 — 渲染 LLM 生成的消息草稿, 允许 HR 微调后激活.
 */
export function ActivationPreview({
  candidateId,
  initialPreview,
  onActivated,
}: ActivationPreviewProps) {
  const [strategy, setStrategy] = React.useState(
    initialPreview?.suggested_strategy ?? "standard",
  );
  const [channel, setChannel] = React.useState("im");
  const [message, setMessage] = React.useState(initialPreview?.preview_message ?? "");
  const [busy, setBusy] = React.useState(false);
  const [sent, setSent] = React.useState(false);

  const handleSend = async () => {
    setBusy(true);
    try {
      await activateCandidate(candidateId, { strategy, channel, message });
      setSent(true);
      onActivated?.();
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">激活预览</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {sent ? (
          <p className="text-emerald-600 text-sm">激活消息已发送</p>
        ) : (
          <>
            <div className="flex items-center gap-2 text-xs">
              <label className="text-slate-500">策略:</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="rounded border border-slate-300 px-2 py-1"
              >
                <option value="conservative">保守</option>
                <option value="standard">标准</option>
                <option value="aggressive">激进</option>
              </select>
              <label className="text-slate-500 ml-2">通道:</label>
              <select
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                className="rounded border border-slate-300 px-2 py-1"
              >
                <option value="im">IM</option>
                <option value="email">邮件</option>
                <option value="sms">短信</option>
                <option value="dingtalk">钉钉</option>
              </select>
            </div>
            <textarea
              rows={5}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <Button disabled={busy || !message} onClick={handleSend}>
              {busy ? "发送中…" : "发送激活消息"}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

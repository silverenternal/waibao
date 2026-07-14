"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * 求职者 — 删除账户 (二次确认 + 真正删除).
 *
 * Step 1: 显示后果警告 + 必读确认
 * Step 2: 输入 "DELETE" 确认 + 最终确认按钮
 * Step 3: 调用 DELETE /api/gdpr/all-data + 清空本地 token
 */

import * as React from "react";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2, Trash2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function DeleteAccountPage() {
  const locale = useLocale();
  const router = useRouter();
  const lang = locale.toLowerCase().startsWith("zh")
    ? "zh"
    : locale.toLowerCase().startsWith("ja")
      ? "ja"
      : "en";

  const [step, setStep] = React.useState<1 | 2 | 3>(1);
  const [confirmText, setConfirmText] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const requiredWord = "DELETE";

  const handleFinalDelete = async () => {
    if (confirmText.trim().toUpperCase() !== requiredWord) {
      setError(
        lang === "zh"
          ? `请输入 ${requiredWord} 以确认`
          : lang === "ja"
            ? `${requiredWord} と入力してください`
            : `Please type ${requiredWord} to confirm`,
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const res = await fetch("/api/gdpr/all-data", {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // 清空本地
      localStorage.removeItem("sb_token");
      localStorage.removeItem("waibao_consent_v1");
      setStep(3);
      setTimeout(() => router.push("/"), 3000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-xl space-y-6 px-4 py-8 sm:px-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight text-destructive">
            {lang === "zh" ? "删除账户" : lang === "ja" ? "アカウント削除" : "Delete account"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {lang === "zh"
              ? "本操作不可撤销,请仔细阅读。"
              : lang === "ja"
                ? "この操作は取り消せません。"
                : "This action is irreversible. Please read carefully."}
          </p>
        </header>
        {step === 1 && (
          <Card className="border-rose-300/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="size-4 text-rose-600" />
                {lang === "zh"
                  ? "删除后会发生什么?"
                  : lang === "ja"
                    ? "削除後の影響"
                    : "What happens after deletion?"}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-foreground/90">
              <ul className="ml-5 list-disc space-y-1.5">
                <li>
                  {lang === "zh"
                    ? "账户立即停用,30 天后全部数据物理删除"
                    : lang === "ja"
                      ? "アカウントは即時停止、30日後にデータ完全削除"
                      : "Account disabled immediately; data fully erased after 30 days"}
                </li>
                <li>
                  {lang === "zh"
                    ? "您的简历将被匿名化(保留统计,抹去 PII)"
                    : lang === "ja"
                      ? "履歴書は匿名化されます(統計は保持、PII は削除)"
                      : "Your resume will be anonymized (PII removed, statistics kept)"}
                </li>
                <li>
                  {lang === "zh"
                    ? "所有协作房间、消息、决策记录全部清除"
                    : lang === "ja"
                      ? "すべての协作ルーム、メッセージ、決定記録が削除されます"
                      : "All collaboration rooms, messages, and decisions are purged"}
                </li>
                <li>
                  {lang === "zh"
                    ? "已开发票的财务记录按法律要求保留 5 年"
                    : lang === "ja"
                      ? "発行済み請求書は法令により5年保管されます"
                      : "Issued invoices are retained for 5 years per legal requirements"}
                </li>
                <li>
                  {lang === "zh"
                    ? "订阅将立即取消,已支付费用原则上不予退还"
                    : lang === "ja"
                      ? "サブスクリプションは即時解約、支払い済みの料金は返金されません"
                      : "Subscription cancelled immediately; paid fees are non-refundable"}
                </li>
              </ul>
              <div className="flex justify-end gap-2 pt-3">
                <Button variant="ghost" onClick={() => router.back()}>
                  {lang === "zh" ? "取消" : lang === "ja" ? "キャンセル" : "Cancel"}
                </Button>
                <Button variant="destructive" onClick={() => setStep(2)}>
                  {lang === "zh" ? "我已知悉,继续" : lang === "ja" ? "了解した上で続行" : "I understand, continue"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
        {step === 2 && (
          <Card className="border-rose-300/60">
            <CardHeader>
              <CardTitle className="text-base">
                {lang === "zh" ? "最终确认" : lang === "ja" ? "最終確認" : "Final confirmation"}
              </CardTitle>
              <CardDescription>
                {lang === "zh"
                  ? `请输入 ${requiredWord} 以确认删除`
                  : lang === "ja"
                    ? `削除を確認するため ${requiredWord} と入力してください`
                    : `Type ${requiredWord} to confirm deletion`}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={requiredWord}
                autoFocus
                className={cn(
                  "font-mono",
                  confirmText.trim().toUpperCase() === requiredWord && "border-rose-400",
                )}
              />
              {error && (
                <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
                  {error}
                </div>
              )}
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setStep(1)} disabled={submitting}>
                  {lang === "zh" ? "上一步" : lang === "ja" ? "戻る" : "Back"}
                </Button>
                <Button
                  variant="destructive"
                  disabled={
                    submitting || confirmText.trim().toUpperCase() !== requiredWord
                  }
                  onClick={handleFinalDelete}
                >
                  {submitting ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Trash2 className="size-4" />
                  )}
                  {lang === "zh"
                    ? "永久删除账户"
                    : lang === "ja"
                      ? "アカウントを永久削除"
                      : "Permanently delete"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
        {step === 3 && (
          <Card className="border-emerald-300/60 bg-emerald-50/50">
            <CardHeader>
              <CardTitle className="text-base text-emerald-700">
                {lang === "zh"
                  ? "账户已删除"
                  : lang === "ja"
                    ? "アカウント削除完了"
                    : "Account deleted"}
              </CardTitle>
              <CardDescription>
                {lang === "zh"
                  ? "感谢您的使用,正在跳转到首页..."
                  : lang === "ja"
                    ? "ご利用ありがとうございました。ホームページに移動します..."
                    : "Thanks for using waibao. Redirecting to home..."}
              </CardDescription>
            </CardHeader>
          </Card>
        )}
      </div>)</ErrorBoundary>
  );
}
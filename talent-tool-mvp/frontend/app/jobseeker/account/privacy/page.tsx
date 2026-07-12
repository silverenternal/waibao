"use client";

/**
 * 求职者 — 隐私设置页面.
 *
 * 展示 + 撤回各 category 同意.
 */

import * as React from "react";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { Loader2, ShieldCheck, ShieldOff } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ConsentStatus {
  user_id: string;
  has_record: boolean;
  decisions: Record<string, boolean>;
  withdrawn_at: string | null;
  created_at?: string;
  updated_at?: string;
  source?: string;
}

const CATEGORY_LABELS: Record<string, { zh: string; en: string; ja: string; description: string }> = {
  necessary: {
    zh: "必要 Cookie",
    en: "Necessary",
    ja: "必須",
    description: "登录会话、防伪令牌",
  },
  functional: {
    zh: "功能偏好",
    en: "Functional",
    ja: "機能",
    description: "语言、主题等偏好",
  },
  analytics: {
    zh: "匿名分析",
    en: "Analytics",
    ja: "分析",
    description: "页面访问统计(匿名)",
  },
  marketing: {
    zh: "营销",
    en: "Marketing",
    ja: "マーケティング",
    description: "个性化推荐广告",
  },
  cross_border: {
    zh: "跨境传输",
    en: "Cross-border transfer",
    ja: "クロスボーダー転送",
    description: "海外职位匹配功能",
  },
};

export default function PrivacyPage() {
  const locale = useLocale();
  const router = useRouter();
  const lang = locale.toLowerCase().startsWith("zh")
    ? "zh"
    : locale.toLowerCase().startsWith("ja")
      ? "ja"
      : "en";
  const [status, setStatus] = React.useState<ConsentStatus | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [submitting, setSubmitting] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const fetchStatus = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const res = await fetch("/api/gdpr/consent", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        if (res.status === 401) {
          router.push("/login");
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const data = (await res.json()) as ConsentStatus;
      setStatus(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [router]);

  // 用 useRef 跟踪是否已首次加载,避免 setState-in-effect
  const initialLoadStarted = React.useRef(false);
  if (!initialLoadStarted.current && typeof window !== "undefined") {
    initialLoadStarted.current = true;
    void fetchStatus();
  }

  const updateConsent = async (category: string, granted: boolean) => {
    setSubmitting(category);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const res = await fetch("/api/gdpr/consent/quick", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ consent_type: category, granted }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchStatus();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(null);
    }
  };

  const withdrawAll = async () => {
    if (
      !confirm(
        lang === "zh"
          ? "确定要撤回所有非必要同意吗?"
          : lang === "ja"
            ? "すべての非必須同意を撤回しますか?"
            : "Withdraw all non-essential consent?",
      )
    )
      return;
    setSubmitting("__all__");
    try {
      const token = localStorage.getItem("sb_token") || "";
      // 逐条撤回
      const cats = ["functional", "analytics", "marketing", "cross_border"];
      for (const c of cats) {
        await fetch("/api/gdpr/consent/withdraw", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ consent_type: c, granted: false }),
        });
      }
      await fetchStatus();
    } finally {
      setSubmitting(null);
    }
  };

  if (loading && !status) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">
          {lang === "zh" ? "隐私设置" : lang === "ja" ? "プライバシー設定" : "Privacy Settings"}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {lang === "zh"
            ? "查看并管理您对 Cookie / 数据处理的同意。"
            : lang === "ja"
              ? "Cookie / データ処理の同意を管理します。"
              : "View and manage your consent for cookies and data processing."}
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {status?.withdrawn_at && (
        <Card className="border-amber-300/60 bg-amber-50/40">
          <CardContent className="flex items-start gap-3 p-4 text-sm">
            <ShieldOff className="mt-0.5 size-4 text-amber-700" />
            <div>
              <p className="font-medium">
                {lang === "zh"
                  ? "您已撤回所有同意"
                  : lang === "ja"
                    ? "すべての同意を撤回済み"
                    : "All consent withdrawn"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {lang === "zh"
                  ? "撤回时间:"
                  : lang === "ja"
                    ? "撤回日時:"
                    : "Withdrawn at:"}{" "}
                {new Date(status.withdrawn_at).toLocaleString(lang === "zh" ? "zh-CN" : lang === "ja" ? "ja-JP" : "en-US")}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {lang === "zh" ? "同意偏好" : lang === "ja" ? "同意設定" : "Consent preferences"}
          </CardTitle>
          <CardDescription>
            {lang === "zh"
              ? "每项可单独开启 / 关闭;关闭后将立即生效。"
              : lang === "ja"
                ? "各項目を個別にオン / オフできます。"
                : "Toggle each category independently; changes apply immediately."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {Object.entries(CATEGORY_LABELS).map(([code, label]) => {
            const granted = status?.decisions?.[code] ?? false;
            const required = code === "necessary";
            return (
              <div
                key={code}
                className={cn(
                  "flex items-center justify-between gap-3 rounded-lg border p-3 text-sm",
                  granted && !required && "border-primary/30 bg-primary/5",
                )}
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      {label[lang as keyof typeof label]}
                    </span>
                    {required && (
                      <Badge variant="secondary" className="text-[10px]">
                        {lang === "zh" ? "必要" : lang === "ja" ? "必須" : "Required"}
                      </Badge>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {label.description}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={granted}
                  disabled={required || submitting === code}
                  onClick={() => updateConsent(code, !granted)}
                  className={cn(
                    "relative h-6 w-11 shrink-0 rounded-full transition-colors",
                    granted ? "bg-primary" : "bg-muted",
                    required && "cursor-not-allowed opacity-60",
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 size-5 rounded-full bg-white transition-transform",
                      granted ? "left-5" : "left-0.5",
                    )}
                  />
                </button>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={withdrawAll} disabled={submitting === "__all__"}>
          {submitting === "__all__" ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <ShieldOff className="size-4" />
          )}
          {lang === "zh"
            ? "撤回所有非必要同意"
            : lang === "ja"
              ? "すべて撤回"
              : "Withdraw all non-essential"}
        </Button>
        <Button onClick={() => router.push("/legal/privacy")} variant="ghost">
          <ShieldCheck className="size-4" />
          {lang === "zh" ? "查看完整隐私政策" : lang === "ja" ? "全文を表示" : "View full policy"}
        </Button>
      </div>
    </div>
  );
}
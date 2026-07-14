"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * 求职者 — 隐私偏好中心 v2 (T2603)
 *
 * Backed by ``/api/gdpr-v2/*``:
 *   - GET  /legal-basis/{region}     region-aware lawful basis
 *   - GET  /processing-register      Art. 30 register of activities
 *   - POST /dsr                      create data subject request
 *   - GET  /dsr                      list my DSRs
 *   - POST /forget /rectify /portability /restrict /object
 *
 * 三区域:EU (GDPR) / CN (PIPL) / CA (CCPA) — each has a tailored copy.
 */

import * as React from "react";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import {
  Download,
  Eraser,
  FileText,
  Globe,
  Loader2,
  ScrollText,
  Shield,
  ShieldCheck,
  ShieldOff,
} from "lucide-react";

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
import { Checkbox } from "@/components/ui/checkbox";
import {
  ConsentSwitch,
  type PurposeDefinition,
} from "@/components/privacy/ConsentSwitch";

type Locale = "zh" | "en" | "ja";

interface ConsentState {
  user_id: string;
  purposes: Record<
    string,
    {
      granted: boolean;
      version: string;
      granted_at: string | null;
      withdrawn_at: string | null;
      source: string;
    }
  >;
  region: string;
  policy_version: string;
}

interface LegalBasis {
  region: string;
  template: {
    code: string;
    name: string;
    lawful_bases: Array<{
      code: string;
      label: string;
      description: string;
      withdrawable: boolean;
    }>;
    transfer_safeguards: string[];
    sla_days: number;
    breach_notification_hours: number;
    cross_border_declaration?: Record<string, unknown>;
  };
}

const i18n = {
  zh: {
    title: "隐私偏好中心",
    subtitle: "管理您的同意、行使 GDPR / PIPL / CCPA 权利、查看数据处理活动。",
    region: "当前法律区域",
    consent: "逐项同意",
    consentDesc: "每一类数据处理都可以单独授权或撤回。撤回不影响您之前的合法处理。",
    processingRegister: "数据处理活动 (Art. 30)",
    rights: "您的权利",
    rightsDesc: "一键行使您的法定权利 — 我们承诺 30 天内回复。",
    requestExport: "数据导出",
    requestForget: "被遗忘权",
    requestRectify: "数据更正",
    requestRestrict: "限制处理",
    requestObject: "反对处理",
    save: "保存",
    saved: "已保存",
    saving: "保存中…",
    withdrawAll: "撤回所有非必要同意",
    confirmWithdrawAll: "确定要撤回所有非必要同意吗?",
    dsrHistory: "我的请求历史",
    dsrEmpty: "暂无请求",
    slaDays: "回复 SLA",
    hours: "小时",
    lawfulBasis: "法律依据",
  },
  en: {
    title: "Privacy preference centre",
    subtitle: "Manage per-purpose consent, exercise GDPR / PIPL / CCPA rights, browse our processing register.",
    region: "Active legal region",
    consent: "Per-purpose consent",
    consentDesc: "Each processing purpose can be granted or withdrawn independently. Withdrawal does not affect prior lawful processing.",
    processingRegister: "Processing activities (Art. 30)",
    rights: "Your rights",
    rightsDesc: "Exercise your statutory rights in one click — we commit to a 30-day SLA.",
    requestExport: "Data export",
    requestForget: "Right to be forgotten",
    requestRectify: "Rectification",
    requestRestrict: "Restriction",
    requestObject: "Object",
    save: "Save",
    saved: "Saved",
    saving: "Saving…",
    withdrawAll: "Withdraw all non-essential consent",
    confirmWithdrawAll: "Withdraw all non-essential consent?",
    dsrHistory: "My request history",
    dsrEmpty: "No requests yet",
    slaDays: "Reply SLA",
    hours: "hours",
    lawfulBasis: "Lawful basis",
  },
  ja: {
    title: "プライバシー設定センター",
    subtitle: "GDPR / PIPL / CCPA に基づく同意管理と権利行使。",
    region: "適用法域",
    consent: "目的別同意",
    consentDesc: "各処理目的ごとに個別に同意 / 撤回できます。",
    processingRegister: "処理活動 (Art. 30)",
    rights: "あなたの権利",
    rightsDesc: "ワンクリックで法的権利を行使 — 30 日以内に返信します。",
    requestExport: "データエクスポート",
    requestForget: "忘れられる権利",
    requestRectify: "訂正",
    requestRestrict: "処理制限",
    requestObject: "処理拒否",
    save: "保存",
    saved: "保存済み",
    saving: "保存中…",
    withdrawAll: "すべての非必須同意を撤回",
    confirmWithdrawAll: "すべての非必須同意を撤回しますか?",
    dsrHistory: "リクエスト履歴",
    dsrEmpty: "リクエストはありません",
    slaDays: "返信 SLA",
    hours: "時間",
    lawfulBasis: "法的根拠",
  },
} as const;

const PURPOSE_CATALOG: PurposeDefinition[] = [
  {
    code: "necessary",
    label_zh: "必要 Cookie / 登录会话",
    label_en: "Strictly necessary",
    description_zh: "登录会话、防伪令牌、安全防护。无法关闭。",
    description_en: "Login session, CSRF tokens, security. Cannot be disabled.",
    required: true,
    lawful_basis: { EU: "gdpr_contract", CN: "pipl_contract_necessary" },
  },
  {
    code: "functional",
    label_zh: "功能偏好",
    label_en: "Functional",
    description_zh: "记住语言、主题、推荐偏好。",
    description_en: "Remember language, theme, and recommendation preferences.",
    required: false,
    lawful_basis: { EU: "gdpr_consent", CN: "pipl_consent" },
  },
  {
    code: "analytics",
    label_zh: "匿名分析",
    label_en: "Analytics",
    description_zh: "页面访问统计(匿名化),帮助我们改进产品。",
    description_en: "Anonymous usage telemetry to improve the product.",
    required: false,
    lawful_basis: { EU: "gdpr_consent", CN: "pipl_consent" },
  },
  {
    code: "marketing",
    label_zh: "邮件营销",
    label_en: "Marketing emails",
    description_zh: "个性化推荐、活动邀请、产品更新。",
    description_en: "Personalised recommendations, event invites, product updates.",
    required: false,
    lawful_basis: { EU: "gdpr_consent", CN: "pipl_consent" },
  },
  {
    code: "marketing_sms",
    label_zh: "营销短信",
    label_en: "Marketing SMS",
    description_zh: "短信通知 + 验证码 + 营销。",
    description_en: "SMS notifications, OTPs, and marketing messages.",
    required: false,
    lawful_basis: { EU: "gdpr_consent", CN: "pipl_consent" },
  },
  {
    code: "coaching",
    label_zh: "AI 面试辅导",
    label_en: "AI coaching",
    description_zh: "AI 模拟面试官、简历润色、面试准备助手。",
    description_en: "AI mock interviewer, resume polishing, prep assistant.",
    required: false,
    lawful_basis: { EU: "gdpr_consent", CN: "pipl_consent" },
  },
  {
    code: "ai_training",
    label_zh: "AI 模型训练",
    label_en: "AI model training",
    description_zh: "使用您的匿名化数据改进我们的 AI 模型。",
    description_en: "Use your anonymised data to improve our AI models.",
    required: false,
    lawful_basis: { EU: "gdpr_legitimate_interest", CN: "pipl_consent" },
  },
  {
    code: "cross_border",
    label_zh: "数据出境",
    label_en: "Cross-border transfer",
    description_zh: "同意将数据传输至您所在区域之外的服务器(用于国际匹配功能)。",
    description_en: "Allow data transfer to servers outside your home region.",
    required: false,
    lawful_basis: { EU: "gdpr_consent", CN: "pipl_consent" },
  },
];

export default function PrivacyV2Page() {
  const localeHook = useLocale();
  const router = useRouter();
  const lang: Locale = localeHook.toLowerCase().startsWith("zh")
    ? "zh"
    : localeHook.toLowerCase().startsWith("ja")
      ? "ja"
      : "en";
  const t = i18n[lang];

  const [region, setRegion] = React.useState<string>("EU");
  const [consent, setConsent] = React.useState<ConsentState | null>(null);
  const [legalBasis, setLegalBasis] = React.useState<LegalBasis | null>(null);
  const [processingItems, setProcessingItems] = React.useState<
    Array<{ id: string; processing_purpose: string; lawful_basis: string; retention_period_days: number }>
  >([]);
  const [dsrList, setDsrList] = React.useState<
    Array<{ id: string; request_type: string; status: string; created_at: string }>
  >([]);
  const [loading, setLoading] = React.useState(true);
  const [pending, setPending] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const tokenHeader = React.useCallback((): Record<string, string> => {
    if (typeof window === "undefined") return {};
    const token = localStorage.getItem("sb_token") || "";
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, []);

  const detectRegion = React.useCallback(async (): Promise<string> => {
    try {
      const res = await fetch("/api/gdpr-v2/legal-basis", {
        headers: tokenHeader(),
      });
      if (!res.ok) return "EU";
      const data = (await res.json()) as { regions: string[] };
      // try browser timezone
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
      if (tz.startsWith("Asia/Shanghai") || tz.startsWith("Asia/Chongqing")) return "CN";
      if (tz.startsWith("America/Los_Angeles") || tz.startsWith("America/Vancouver")) return "CA";
      return data.regions.includes("EU") ? "EU" : "GLOBAL";
    } catch {
      return "EU";
    }
  }, [tokenHeader]);

  const loadAll = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await detectRegion();
      setRegion(r);
      const [basis, register, dsr] = await Promise.all([
        fetch(`/api/gdpr-v2/legal-basis/${r}`, { headers: tokenHeader() }),
        fetch("/api/gdpr-v2/processing-register", { headers: tokenHeader() }),
        fetch("/api/gdpr-v2/dsr", { headers: tokenHeader() }),
      ]);
      if (basis.ok) {
        setLegalBasis((await basis.json()) as LegalBasis);
      }
      if (register.ok) {
        const data = (await register.json()) as { items: typeof processingItems };
        setProcessingItems(data.items || []);
      }
      if (dsr.ok) {
        const data = (await dsr.json()) as { items: typeof dsrList };
        setDsrList(data.items || []);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [detectRegion, tokenHeader]);

  const initialLoadStarted = React.useRef(false);
  if (!initialLoadStarted.current && typeof window !== "undefined") {
    initialLoadStarted.current = true;
    void loadAll();
  }

  const togglePurpose = async (code: string, granted: boolean) => {
    setPending(code);
    try {
      const res = await fetch("/api/gdpr-v2/consent", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...tokenHeader(),
        },
        body: JSON.stringify({ purpose: code, granted }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // refetch consent state from canonical store
      const refreshed = await fetch("/api/gdpr-v2/consent", { headers: tokenHeader() });
      if (refreshed.ok) {
        setConsent((await refreshed.json()) as ConsentState);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setPending(null);
    }
  };

  const withdrawAll = async () => {
    if (!window.confirm(t.confirmWithdrawAll)) return;
    setPending("__all__");
    try {
      const codes = PURPOSE_CATALOG.filter((p) => !p.required).map((p) => p.code);
      await Promise.all(
        codes.map((code) =>
          fetch("/api/gdpr-v2/consent", {
            method: "POST",
            headers: { "Content-Type": "application/json", ...tokenHeader() },
            body: JSON.stringify({ purpose: code, granted: false }),
          }),
        ),
      );
      await loadAll();
    } finally {
      setPending(null);
    }
  };

  const requestRight = async (kind: "portability" | "forget" | "rectify" | "restrict" | "object") => {
    setPending(kind);
    try {
      const endpoint =
        kind === "forget"
          ? "/api/gdpr-v2/forget"
          : kind === "rectify"
            ? "/api/gdpr-v2/rectify"
            : kind === "restrict"
              ? "/api/gdpr-v2/restrict"
              : kind === "object"
                ? "/api/gdpr-v2/object"
                : "/api/gdpr-v2/portability";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...tokenHeader() },
        body: kind === "rectify" ? JSON.stringify({ field: "name", new_value: "" }) : "{}",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setPending(null);
    }
  };

  if (loading && !legalBasis) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
        <header className="space-y-2">
          <div className="flex items-center gap-2">
            <Shield className="size-5 text-primary" />
            <h1 className="text-2xl font-bold tracking-tight">{t.title}</h1>
          </div>
          <p className="text-sm text-muted-foreground">{t.subtitle}</p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Badge variant="outline" className="text-[10px]">
              <Globe className="mr-1 size-3" />
              {t.region}: {legalBasis?.template?.code ?? region}
            </Badge>
            {legalBasis && (
              <Badge variant="secondary" className="text-[10px]">
                {t.slaDays}: {legalBasis.template.sla_days} d
              </Badge>
            )}
            {legalBasis && (
              <Badge variant="secondary" className="text-[10px]">
                Breach notify: {legalBasis.template.breach_notification_hours} {t.hours}
              </Badge>
            )}
          </div>
        </header>
        {error && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}
        {/* Per-purpose consent */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <ShieldCheck className="size-4" />
                  {t.consent}
                </CardTitle>
                <CardDescription>{t.consentDesc}</CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void withdrawAll()}
                disabled={pending === "__all__"}
              >
                <ShieldOff className="mr-2 size-4" />
                {t.withdrawAll}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {PURPOSE_CATALOG.map((p) => {
              const purposeState = consent?.purposes?.[p.code];
              const granted = p.required || Boolean(purposeState?.granted);
              return (
                <ConsentSwitch
                  key={p.code}
                  purpose={p}
                  granted={granted}
                  withdrawnAt={purposeState?.withdrawn_at ?? null}
                  locale={lang}
                  pending={pending === p.code}
                  onChange={(next) => void togglePurpose(p.code, next)}
                />
              );
            })}
          </CardContent>
        </Card>
        {/* Processing register */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ScrollText className="size-4" />
              {t.processingRegister}
            </CardTitle>
            <CardDescription>{legalBasis?.template.name}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y" data-testid="processing-register-list">
              {processingItems.map((item) => (
                <li key={item.id} className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-medium">{item.processing_purpose}</p>
                    <p className="text-xs text-muted-foreground">
                      {t.lawfulBasis}: <code className="font-mono">{item.lawful_basis}</code>
                    </p>
                  </div>
                  <Badge variant="outline" className="text-[10px]">
                    {item.retention_period_days} d
                  </Badge>
                </li>
              ))}
              {processingItems.length === 0 && (
                <li className="py-4 text-sm text-muted-foreground">
                  {legalBasis?.template.code === "CN"
                    ? "暂无记录 — 将在 30 天内补充"
                    : legalBasis?.template.code === "CA"
                      ? "No records yet — populated within 45 days"
                      : "暂无记录 — 将在 30 天内补充"}
                </li>
              )}
            </ul>
          </CardContent>
        </Card>
        {/* Rights */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t.rights}</CardTitle>
            <CardDescription>{t.rightsDesc}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void requestRight("portability")}
              disabled={pending === "portability"}
              data-testid="gdpr-action-export"
            >
              <Download className="mr-2 size-4" /> {t.requestExport}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void requestRight("rectify")}
              disabled={pending === "rectify"}
            >
              <FileText className="mr-2 size-4" /> {t.requestRectify}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void requestRight("restrict")}
              disabled={pending === "restrict"}
            >
              {t.requestRestrict}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void requestRight("object")}
              disabled={pending === "object"}
            >
              {t.requestObject}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void requestRight("forget")}
              disabled={pending === "forget"}
              data-testid="gdpr-action-forget"
            >
              <Eraser className="mr-2 size-4" /> {t.requestForget}
            </Button>
          </CardContent>
        </Card>
        {/* DSR history */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t.dsrHistory}</CardTitle>
          </CardHeader>
          <CardContent>
            {dsrList.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t.dsrEmpty}</p>
            ) : (
              <ul className="divide-y" data-testid="dsr-list">
                {dsrList.map((d) => (
                  <li key={d.id} className="flex items-center justify-between py-2 text-sm">
                    <span className="font-mono text-xs">{d.id.slice(0, 8)}</span>
                    <span>{d.request_type}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {d.status}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {new Date(d.created_at).toLocaleDateString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}

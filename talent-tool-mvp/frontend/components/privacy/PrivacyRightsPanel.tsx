"use client";

/**
 * PrivacyRightsPanel — v10.0 T5016
 *
 * The upgraded privacy control surface for Art. 15 / 17 / 20 (GDPR) +
 * CCPA Do-Not-Sell.  Backed by:
 *
 *   GET  /api/gdpr-v2/access             Art. 15 structured export (JSON bundle)
 *   POST /api/gdpr-v2/ccpa/opt-out       CCPA / CPRA Do-Not-Sell + Do-Not-Share
 *   GET  /api/gdpr-v2/ccpa/status        current opt-out preference
 *   POST /api/gdpr-v2/ccpa/request       open a verifiable consumer request
 *
 * The component is region-aware: the "Do Not Sell / Share" toggle only renders
 * for CCPA/CPRA jurisdictions (CA), and the export button surfaces the PIPL
 * cross-border declaration banner when the subject is in a PIPL region (CN).
 */
import * as React from "react";
import {
  Ban,
  Download,
  Eraser,
  FileDown,
  Loader2,
  MegaphoneOff,
  ShieldAlert,
} from "lucide-react";

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
import { toast } from "sonner";

export interface PrivacyRightsPanelProps {
  /** ISO region: EU | CN | CA | GLOBAL */
  region: string;
  /** bearer-token injector (reads localStorage in the host page) */
  tokenHeader: () => Record<string, string>;
}

interface CCPAStatus {
  do_not_sell: boolean;
  do_not_share: boolean;
  asserted_at: string;
  source: string;
}

const COPY: Record<"zh" | "en", Record<string, string>> = {
  zh: {
    rightsTitle: "数据权利 (Art. 15 / 17 / 20)",
    rightsDesc: "导出您的全部数据、申请删除、或行使 CCPA 选择退出。",
    export: "下载我的数据 (Art. 15/20)",
    exportHint: "结构化 JSON 包,含 PIPL 出境声明 (CN 区域)",
    forget: "申请删除 (Art. 17)",
    forgetConfirm: "确认申请删除您的全部个人数据?此操作不可逆。",
    forgetting: "提交中…",
    ccpaTitle: "不出售 / 不共享 (CCPA)",
    ccpaDesc: "选择退出后,我们不会出售您的个人信息,也不会用于跨上下文行为广告。",
    doNotSell: "请勿出售我的个人信息",
    doNotShare: "请勿共享 (跨上下文广告)",
    saleOn: "允许出售/共享",
    saleOff: "已选择退出",
    piplBanner: "您的数据包将包含 PIPL 数据出境处理声明。",
    openingRequest: "请求中…",
    exportDone: "数据包已生成并下载",
    optOutSaved: "偏好已保存",
    error: "操作失败,请重试",
  },
  en: {
    rightsTitle: "Data rights (Art. 15 / 17 / 20)",
    rightsDesc: "Export all your data, request deletion, or exercise CCPA opt-out.",
    export: "Download my data (Art. 15/20)",
    exportHint: "Structured JSON bundle, with PIPL cross-border declaration (CN region)",
    forget: "Request deletion (Art. 17)",
    forgetConfirm: "Confirm deletion of all your personal data? This is irreversible.",
    forgetting: "Submitting…",
    ccpaTitle: "Do Not Sell / Share (CCPA)",
    ccpaDesc: "Once opted out, we will not sell your personal information nor use it for cross-context behavioural advertising.",
    doNotSell: "Do Not Sell My Personal Information",
    doNotShare: "Do Not Share (cross-context advertising)",
    saleOn: "Sale / share permitted",
    saleOff: "Opted out",
    piplBanner: "Your data bundle will include a PIPL cross-border transfer declaration.",
    openingRequest: "Requesting…",
    exportDone: "Data bundle generated and downloaded",
    optOutSaved: "Preference saved",
    error: "Operation failed, please retry",
  },
};

function pickLang(): "zh" | "en" {
  if (typeof navigator === "undefined") return "en";
  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

function isCCPARegion(region: string): boolean {
  return region.toUpperCase() === "CA";
}
function isPIPLRegion(region: string): boolean {
  return ["CN", "HK", "MO", "TW"].includes(region.toUpperCase());
}

export function PrivacyRightsPanel({ region, tokenHeader }: PrivacyRightsPanelProps) {
  const lang = pickLang();
  const t = COPY[lang];

  const [busy, setBusy] = React.useState<string | null>(null);
  const [ccpa, setCcpa] = React.useState<CCPAStatus | null>(null);

  const loadCCPA = React.useCallback(async () => {
    try {
      const res = await fetch("/api/gdpr-v2/ccpa/status", { headers: tokenHeader() });
      if (res.ok) setCcpa((await res.json()) as CCPAStatus);
    } catch {
      /* non-CCPA region or unauthenticated — silently ignore */
    }
  }, [tokenHeader]);

  React.useEffect(() => {
    void loadCCPA();
  }, [loadCCPA]);

  const doExport = async () => {
    setBusy("export");
    try {
      const res = await fetch("/api/gdpr-v2/access", { headers: tokenHeader() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const bundle = await res.blob();
      const url = URL.createObjectURL(bundle);
      const a = document.createElement("a");
      a.href = url;
      a.download = `waibao-data-export-${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(t.exportDone);
    } catch {
      toast.error(t.error);
    } finally {
      setBusy(null);
    }
  };

  const doForget = async () => {
    if (!window.confirm(t.forgetConfirm)) return;
    setBusy("forget");
    try {
      const res = await fetch("/api/gdpr-v2/forget", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...tokenHeader() },
        body: "{}",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      toast.success(lang === "zh" ? "已提交删除申请" : "Deletion request submitted");
    } catch {
      toast.error(t.error);
    } finally {
      setBusy(null);
    }
  };

  const toggleOptOut = async (field: "do_not_sell" | "do_not_share", value: boolean) => {
    setBusy(field);
    try {
      // Merge the two flags so toggling one does not reset the other.
      const next = {
        do_not_sell: field === "do_not_sell" ? value : ccpa?.do_not_sell ?? true,
        do_not_share: field === "do_not_share" ? value : ccpa?.do_not_share ?? true,
        source: "web",
      };
      const res = await fetch("/api/gdpr-v2/ccpa/opt-out", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...tokenHeader() },
        body: JSON.stringify(next),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated = (await res.json()) as CCPAStatus;
      setCcpa(updated);
      toast.success(t.optOutSaved);
    } catch {
      toast.error(t.error);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4" data-testid="privacy-rights-panel">
      {/* Art. 15 / 17 / 20 export + delete */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <FileDown className="size-4" />
            {t.rightsTitle}
          </CardTitle>
          <CardDescription>{t.rightsDesc}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {isPIPLRegion(region) && (
            <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-300">
              <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
              <span>{t.piplBanner}</span>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void doExport()}
              disabled={busy === "export"}
              data-testid="privacy-action-export"
            >
              {busy === "export" ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Download className="mr-2 size-4" />
              )}
              {t.export}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void doForget()}
              disabled={busy === "forget"}
              data-testid="privacy-action-forget"
            >
              {busy === "forget" ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Eraser className="mr-2 size-4" />
              )}
              {busy === "forget" ? t.forgetting : t.forget}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">{t.exportHint}</p>
        </CardContent>
      </Card>

      {/* CCPA / CPRA Do Not Sell / Share — only in CA region */}
      {isCCPARegion(region) && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <MegaphoneOff className="size-4" />
              {t.ccpaTitle}
            </CardTitle>
            <CardDescription>{t.ccpaDesc}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4" data-testid="ccpa-opt-out">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <p className="text-sm font-medium">{t.doNotSell}</p>
                <p className="text-[11px] text-muted-foreground">
                  {ccpa?.do_not_sell ? t.saleOff : t.saleOn}
                </p>
              </div>
              <Checkbox
                checked={ccpa?.do_not_sell ?? false}
                onCheckedChange={(v) => void toggleOptOut("do_not_sell", Boolean(v))}
                disabled={busy === "do_not_sell"}
                aria-label={t.doNotSell}
                data-testid="ccpa-do-not-sell"
              />
            </div>
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <p className="text-sm font-medium">{t.doNotShare}</p>
                <p className="text-[11px] text-muted-foreground">
                  {ccpa?.do_not_share ? t.saleOff : t.saleOn}
                </p>
              </div>
              <Checkbox
                checked={ccpa?.do_not_share ?? false}
                onCheckedChange={(v) => void toggleOptOut("do_not_share", Boolean(v))}
                disabled={busy === "do_not_share"}
                aria-label={t.doNotShare}
                data-testid="ccpa-do-not-share"
              />
            </div>
            {ccpa?.source === "gpc_header" && (
              <Badge variant="secondary" className="text-[10px]">
                <Ban className="mr-1 size-3" />
                {lang === "zh" ? "已通过 GPC 标头自动选择退出" : "Auto-opted out via GPC header"}
              </Badge>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default PrivacyRightsPanel;

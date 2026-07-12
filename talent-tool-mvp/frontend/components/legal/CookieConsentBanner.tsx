"use client";

/**
 * CookieConsentBanner — T1201 GDPR + 中国合规 双模式.
 *
 * - EU/UK/全球:GPC 信号自动开启最小模式;显示底部 banner
 * - 中国:顶部居中;默认仅必要,跨境传输单独勾选
 *
 * 提交:POST /api/gdpr/consent/quick 逐条;成功写入 localStorage
 * 关闭后 12 个月内不重复弹
 */

import * as React from "react";
import { useLocale } from "next-intl";
import { X, ChevronDown, Shield, Globe2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

import { ConsentPreferences } from "./ConsentPreferences";

export interface ConsentCategory {
  code: string;
  name: string;
  required: boolean;
  default: boolean;
  description?: string;
}

export interface ConsentBannerData {
  title: string;
  description: string;
  categories: ConsentCategory[];
  policy_version: string;
  locale: string;
  privacy_url?: string;
}

const STORAGE_KEY = "waibao_consent_v1";

interface PersistedConsent {
  version: string;
  decisions: Record<string, boolean>;
  at: number;
}

function readPersisted(): PersistedConsent | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedConsent;
  } catch {
    return null;
  }
}

function writePersisted(value: PersistedConsent): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

function detectGpc(): boolean {
  if (typeof navigator === "undefined") return false;
  return Boolean(
    (navigator as unknown as { globalPrivacyControl?: boolean })
      .globalPrivacyControl,
  );
}

function detectChineseLocale(locale: string): boolean {
  return locale.toLowerCase().startsWith("zh");
}

async function postConsent(
  decisions: Array<{ consent_type: string; granted: boolean }>,
): Promise<void> {
  const token =
    typeof window !== "undefined"
      ? window.localStorage.getItem("sb_token") || ""
      : "";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  for (const d of decisions) {
    try {
      await fetch("/api/gdpr/consent/quick", {
        method: "POST",
        headers,
        body: JSON.stringify(d),
      }).catch(() => undefined);
    } catch {
      /* ignore */
    }
  }
}

function defaultDecisionsFor(
  banner: ConsentBannerData,
  isZh: boolean,
  gpc: boolean,
): Record<string, boolean> {
  const init: Record<string, boolean> = {};
  for (const c of banner.categories) {
    if (gpc && !c.required) {
      init[c.code] = false;
    } else {
      init[c.code] = c.required || (c.default && !isZh);
      if (isZh && !c.required) init[c.code] = false;
    }
  }
  return init;
}

export function CookieConsentBanner({
  initialData,
  forceShow = false,
}: {
  initialData?: ConsentBannerData | null;
  forceShow?: boolean;
}) {
  const locale = useLocale();
  const isZh = detectChineseLocale(locale);
  const gpc = React.useMemo(() => detectGpc(), []);
  const [banner, setBanner] = React.useState<ConsentBannerData | null>(
    initialData ?? null,
  );
  const [persisted, setPersisted] = React.useState<PersistedConsent | null>(null);
  const [now, setNow] = React.useState<number>(0);

  // 客户端初始化(读 localStorage + 拉 banner + 初始化 now)
  React.useEffect(() => {
    setNow(Date.now());
    const stored = readPersisted();
    if (stored) setPersisted(stored);
    if (!banner) {
      void (async () => {
        try {
          const res = await fetch(`/api/gdpr/banner?lang=${locale}`);
          if (!res.ok) return;
          const data = (await res.json()) as ConsentBannerData;
          setBanner(data);
        } catch {
          /* ignore */
        }
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const twelveMonthsMs = 365 * 24 * 60 * 60 * 1000;
  const decided =
    !!persisted &&
    now > 0 &&
    now - persisted.at < twelveMonthsMs &&
    persisted.version === banner?.policy_version;

  const decisions = React.useMemo(() => {
    if (!banner) return {};
    if (decided && persisted) return persisted.decisions;
    return defaultDecisionsFor(banner, isZh, gpc);
  }, [banner, decided, persisted, isZh, gpc]);

  if (!banner || decided) return null;

  const persist = async (next: Record<string, boolean>) => {
    const payload: PersistedConsent = {
      version: banner.policy_version ?? "v1",
      decisions: next,
      at: Date.now(),
    };
    writePersisted(payload);
    setPersisted(payload);
    const arr = Object.entries(next).map(([consent_type, granted]) => ({
      consent_type,
      granted,
    }));
    await postConsent(arr);
  };

  const handleAcceptAll = async () => {
    const next: Record<string, boolean> = {};
    for (const c of banner.categories) next[c.code] = true;
    await persist(next);
  };

  const handleRejectAll = async () => {
    const next: Record<string, boolean> = {};
    for (const c of banner.categories) next[c.code] = c.required;
    await persist(next);
  };

  const wrapperClass = isZh
    ? "fixed top-4 left-1/2 z-50 w-[min(640px,calc(100vw-2rem))] -translate-x-1/2 rounded-2xl border bg-background shadow-2xl"
    : "fixed bottom-4 left-4 right-4 z-50 mx-auto max-w-3xl rounded-2xl border bg-background shadow-2xl md:left-1/2 md:right-auto md:-translate-x-1/2";

  return (
    <ConsentBannerContent
      banner={banner}
      isZh={isZh}
      wrapperClass={wrapperClass}
      defaultDecisions={decisions}
      onAcceptAll={handleAcceptAll}
      onRejectAll={handleRejectAll}
    />
  );
}

function ConsentBannerContent({
  banner,
  isZh,
  wrapperClass,
  defaultDecisions,
  onAcceptAll,
  onRejectAll,
}: {
  banner: ConsentBannerData;
  isZh: boolean;
  wrapperClass: string;
  defaultDecisions: Record<string, boolean>;
  onAcceptAll: () => Promise<void>;
  onRejectAll: () => Promise<void>;
}) {
  const [showCustomize, setShowCustomize] = React.useState(false);
  const [localDecisions, setLocalDecisions] =
    React.useState<Record<string, boolean>>(defaultDecisions);

  // 自定义面板打开时初始化一次
  const onToggleCustomize = () => {
    if (!showCustomize && Object.keys(localDecisions).length === 0) {
      setLocalDecisions(defaultDecisions);
    }
    setShowCustomize((v) => !v);
  };

  const handleSaveCustom = async () => {
    // 写持久化层
    if (typeof window !== "undefined") {
      const payload = {
        version: banner.policy_version ?? "v1",
        decisions: localDecisions,
        at: Date.now(),
      };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      } catch {
        /* ignore */
      }
      // 同步后端
      const token = window.localStorage.getItem("sb_token") || "";
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      for (const [code, granted] of Object.entries(localDecisions)) {
        fetch("/api/gdpr/consent/quick", {
          method: "POST",
          headers,
          body: JSON.stringify({ consent_type: code, granted }),
        }).catch(() => undefined);
      }
      // 关闭 banner
      window.dispatchEvent(new StorageEvent("storage", { key: STORAGE_KEY }));
      setShowCustomize(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label={banner.title}
      className={wrapperClass}
    >
      <div className="flex items-start gap-3 p-5">
        <div className="grid size-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
          {isZh ? <Globe2 className="size-4" /> : <Shield className="size-4" />}
        </div>
        <div className="flex-1 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-base font-semibold">{banner.title}</h2>
            <button
              type="button"
              aria-label="close"
              className="rounded-md p-1 text-muted-foreground hover:bg-muted"
            >
              <X className="size-4" />
            </button>
          </div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {banner.description}
          </p>

          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            onClick={onToggleCustomize}
          >
            {isZh ? "自定义设置" : "Customize"}
            <ChevronDown
              className={cn(
                "size-3.5 transition-transform",
                showCustomize && "rotate-180",
              )}
            />
          </button>

          {showCustomize && (
            <ConsentPreferences
              categories={banner.categories}
              decisions={localDecisions}
              onChange={(code, val) =>
                setLocalDecisions((d) => ({ ...d, [code]: val }))
              }
            />
          )}

          <div className="flex flex-wrap items-center gap-2 pt-2">
            <Button size="sm" onClick={onAcceptAll}>
              {isZh ? "同意全部" : "Accept all"}
            </Button>
            <Button size="sm" variant="outline" onClick={onRejectAll}>
              {isZh ? "仅必要" : "Reject all"}
            </Button>
            {showCustomize && (
              <Button size="sm" variant="secondary" onClick={handleSaveCustom}>
                {isZh ? "保存我的选择" : "Save preferences"}
              </Button>
            )}
            {banner.privacy_url && (
              <a
                href={banner.privacy_url}
                className="ml-auto text-xs text-muted-foreground hover:underline"
              >
                {isZh ? "查看隐私政策" : "Privacy policy"}
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default CookieConsentBanner;
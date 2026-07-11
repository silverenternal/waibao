/**
 * next-intl 配置 (T801).
 *
 * 关键约定:
 *   - 默认 zh-CN
 *   - 支持 en-US / ja-JP,经 locale cookie 同步(URL 不加前缀)
 *   - 缺失 key 时 fallback 到 en-US
 *
 * 用法:
 *   // app/layout.tsx
 *   import { NextIntlClientProvider } from "next-intl";
 *   import { getMessages } from "next-intl/server";
 *
 *   const messages = await getMessages();
 *   <NextIntlClientProvider messages={messages}>...</NextIntlClientProvider>
 *
 *   // component
 *   const t = useTranslations("common");
 *   <button>{t("save")}</button>
 */

import { notFound } from "next/navigation";
import { getRequestConfig } from "next-intl/server";
import { createNavigation } from "next-intl/navigation";
import createMiddleware from "next-intl/middleware";

export const locales = ["zh-CN", "en-US", "ja-JP"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "zh-CN";

/** 按 key 顺序回退: 当前 locale → en-US → 原 key 字符串. */
export const fallbackLocale: Locale = "en-US";

/** locale 显示名(用 UI 切换器). */
export const localeDisplayName: Record<Locale, string> = {
  "zh-CN": "简体中文",
  "en-US": "English",
  "ja-JP": "日本語",
};

export const localeCookieName = "waibao_locale";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = (locales as readonly string[]).includes(requested ?? "")
    ? (requested as Locale)
    : defaultLocale;

  let messages: Record<string, unknown>;
  try {
    messages = (await import(`./messages/${locale}.json`)).default;
  } catch {
    notFound();
  }

  // 缺失 key 用 fallbackLocale 补齐(只补一级,深度合并)
  let fallback: Record<string, unknown> = {};
  if (locale !== fallbackLocale) {
    try {
      fallback = (await import(`./messages/${fallbackLocale}.json`)).default;
    } catch {
      fallback = {};
    }
  }

  return {
    locale,
    messages: mergeMissing(messages, fallback),
    timeZone: "Asia/Shanghai",
    now: new Date(),
    formats: {
      dateTime: {
        short: { year: "numeric", month: "2-digit", day: "2-digit" },
        long: {
          year: "numeric",
          month: "long",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        },
      },
    },
  };
});

function mergeMissing(
  primary: Record<string, unknown>,
  fallback: Record<string, unknown>,
): Record<string, unknown> {
  if (!fallback || Object.keys(fallback).length === 0) return primary;
  const out: Record<string, unknown> = { ...primary };
  for (const [k, v] of Object.entries(fallback)) {
    if (!(k in out)) {
      out[k] = v;
    } else if (typeof v === "object" && v && typeof out[k] === "object" && out[k]) {
      out[k] = mergeMissing(
        out[k] as Record<string, unknown>,
        v as Record<string, unknown>,
      );
    }
  }
  return out;
}

/** next-intl 中间件:cookie 驱动 locale,URL 不加前缀. */
export const intlMiddleware = createMiddleware({
  locales: [...locales],
  defaultLocale,
  localePrefix: "never",
  localeCookie: {
    name: localeCookieName,
    maxAge: 60 * 60 * 24 * 365,
  },
});

/** 类型安全的 Link/redirect/useRouter/usePathname(保留供后续接入). */
export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation({
    locales: [...locales],
    defaultLocale,
    localePrefix: "never",
  });

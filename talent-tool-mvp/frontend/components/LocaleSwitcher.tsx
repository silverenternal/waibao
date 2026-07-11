"use client";

/**
 * LocaleSwitcher (T801).
 *
 * 三语切换: zh-CN / en-US / ja-JP
 * - 通过 next-intl 的 hook 切换,会更新 cookie 并触发服务端重新渲染.
 * - 不改 URL 路径(我们用 `localePrefix: 'never'`).
 */

import * as React from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter, usePathname } from "next/navigation";
import {
  locales,
  localeDisplayName,
  type Locale,
  localeCookieName,
} from "@/i18n";

function setLocaleCookie(locale: Locale) {
  if (typeof document === "undefined") return;
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie = `${localeCookieName}=${locale}; path=/; max-age=${oneYear}; samesite=lax`;
}

export function LocaleSwitcher({ className }: { className?: string }) {
  const current = useLocale() as Locale;
  const router = useRouter();
  const pathname = usePathname();
  const t = useTranslations("common");
  const [open, setOpen] = React.useState(false);

  const handleSelect = (next: Locale) => {
    if (next === current) {
      setOpen(false);
      return;
    }
    setLocaleCookie(next);
    // 强制刷新以让服务端读取新 cookie 并重新渲染 messages.
    router.refresh();
    setOpen(false);
  };

  return (
    <div className={className ? `relative ${className}` : "relative"}>
      <button
        type="button"
        aria-label={t("language")}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
        data-testid="locale-switcher"
      >
        <span aria-hidden="true">🌐</span>
        <span>{localeDisplayName[current]}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <ul
          role="listbox"
          aria-label={t("language")}
          className="absolute right-0 z-50 mt-1 min-w-[8rem] overflow-hidden rounded-md border border-slate-200 bg-white py-1 shadow-lg"
        >
          {locales.map((loc) => (
            <li key={loc} role="option" aria-selected={loc === current}>
              <button
                type="button"
                onClick={() => handleSelect(loc)}
                className={`flex w-full items-center justify-between px-3 py-1.5 text-sm hover:bg-slate-50 ${
                  loc === current ? "font-semibold text-blue-600" : "text-slate-700"
                }`}
              >
                <span>{localeDisplayName[loc]}</span>
                {loc === current && <span aria-hidden="true">✓</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default LocaleSwitcher;

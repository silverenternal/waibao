"use client";

/**
 * ConsentPreferences — T1201 细分同意: 必要 / 功能 / 分析 / 营销 / 跨境传输.
 */

import * as React from "react";

import { cn } from "@/lib/utils";
import type { ConsentCategory } from "./CookieConsentBanner";

export interface ConsentPreferencesProps {
  categories: ConsentCategory[];
  decisions: Record<string, boolean>;
  onChange: (code: string, granted: boolean) => void;
}

const I18N: Record<
  string,
  Record<string, { name: string; description: string }>
> = {
  necessary: {
    zh: { name: "必要 Cookie", description: "登录会话、防伪令牌等基础功能,不可关闭。" },
    en: { name: "Necessary", description: "Login session, CSRF tokens. Cannot be disabled." },
    ja: { name: "必須", description: "ログインセッション、CSRF トークン等。無効化不可。" },
  },
  functional: {
    zh: { name: "功能 Cookie", description: "记住您的语言、主题等偏好。" },
    en: { name: "Functional", description: "Remember your language and theme preferences." },
    ja: { name: "機能", description: "言語やテーマ設定を記憶します。" },
  },
  analytics: {
    zh: { name: "分析 Cookie", description: "匿名统计页面访问,用于改进产品。" },
    en: { name: "Analytics", description: "Anonymous usage statistics for product improvement." },
    ja: { name: "分析", description: "製品改善のための匿名統計。" },
  },
  marketing: {
    zh: { name: "营销 Cookie", description: "个性化推荐广告投放(暂未启用)。" },
    en: { name: "Marketing", description: "Personalized advertising (not yet enabled)." },
    ja: { name: "マーケティング", description: "パーソナライズ広告(現在未提供)。" },
  },
  cross_border: {
    zh: {
      name: "跨境传输",
      description: "同意将去标识化数据用于海外职位匹配等跨境场景。",
    },
    en: {
      name: "Cross-border transfer",
      description: "Allow de-identified data to be used for overseas job matching.",
    },
    ja: {
      name: "クロスボーダー転送",
      description: "海外求人マッチング等に個人データを送信します。",
    },
  },
};

function labelFor(category: ConsentCategory, lang: string) {
  const key = lang.toLowerCase().startsWith("zh") ? "zh" : lang.toLowerCase().startsWith("ja") ? "ja" : "en";
  const dict = I18N[category.code] ?? {};
  return dict[key] ?? { name: category.name, description: category.description ?? "" };
}

export function ConsentPreferences({
  categories,
  decisions,
  onChange,
}: ConsentPreferencesProps) {
  const lang =
    typeof document !== "undefined" ? document.documentElement.lang || "en" : "en";

  return (
    <div className="mt-2 space-y-2 rounded-xl border bg-muted/40 p-3">
      {categories.map((c) => {
        const { name, description } = labelFor(c, lang);
        const checked = decisions[c.code] ?? c.default ?? false;
        return (
          <label
            key={c.code}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-lg p-2 text-sm transition-colors hover:bg-background",
              c.required && "cursor-not-allowed opacity-80",
            )}
          >
            <input
              type="checkbox"
              className="mt-0.5 size-4 accent-primary"
              checked={checked}
              disabled={c.required}
              onChange={(e) => onChange(c.code, e.target.checked)}
              aria-label={name}
            />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{name}</span>
                {c.required && (
                  <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
                    {lang.startsWith("zh") ? "必要" : lang.startsWith("ja") ? "必須" : "Required"}
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                {description}
              </p>
            </div>
          </label>
        );
      })}
    </div>
  );
}

export default ConsentPreferences;
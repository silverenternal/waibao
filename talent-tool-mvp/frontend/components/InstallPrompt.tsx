"use client";

/**
 * T1205 — PWA 安装提示组件.
 *
 * 使用 beforeinstallprompt 事件,捕获后用户点击"安装"按钮触发原生安装.
 * 安装成功后,5 分钟内不再显示.
 */
import { useCallback, useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

const STORAGE_KEY = "waibao-pwa-install-dismissed";
const DISMISS_TTL_MS = 5 * 60 * 1000; // 5 min

export function InstallPrompt() {
  const [evt, setEvt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState<boolean>(false);
  const [dismissed, setDismissed] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      setEvt(e as BeforeInstallPromptEvent);
    };
    const onInstalled = () => setInstalled(true);

    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);

    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const ts = Number(stored);
      if (Date.now() - ts < DISMISS_TTL_MS) setDismissed(true);
    }

    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const onInstall = useCallback(async () => {
    if (!evt) return;
    try {
      await evt.prompt();
      const choice = await evt.userChoice;
      if (choice.outcome === "accepted") setInstalled(true);
      setEvt(null);
    } catch (err) {
      console.warn("[pwa] install failed", err);
    }
  }, [evt]);

  const onDismiss = useCallback(() => {
    setDismissed(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, String(Date.now()));
    }
  }, []);

  if (installed || dismissed || !evt) return null;

  return (
    <div
      role="dialog"
      aria-label="Install waibao app"
      data-testid="install-prompt"
      className="fixed bottom-4 left-4 right-4 z-50 mx-auto max-w-md rounded-xl border border-slate-200 bg-white p-4 shadow-lg"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 flex-none items-center justify-center rounded-lg bg-blue-100 text-blue-600">
          P
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-slate-900">安装 waibao</h3>
          <p className="mt-1 text-xs text-slate-500">
            添加到主屏幕,离线访问画像/工单,无需打开浏览器.
          </p>
        </div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          稍后
        </button>
        <button
          type="button"
          onClick={onInstall}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
          data-testid="install-button"
        >
          安装
        </button>
      </div>
    </div>
  );
}

export default InstallPrompt;
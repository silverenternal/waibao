"use client";

/**
 * T1205 — OfflineBanner 组件.
 *
 * 显示顶部黄色横幅:
 *   - 离线时:"您已离线 — 显示的是缓存数据"
 *   - 恢复时短暂显示:"已恢复连接"
 */
import { useEffect } from "react";
import { useOnline } from "@/hooks/use-online";

export function OfflineBanner() {
  const { isOnline, wasOffline } = useOnline();

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.dataset["network"] = isOnline ? "online" : "offline";
  }, [isOnline]);

  if (isOnline && !wasOffline) return null;

  if (!isOnline) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-2 bg-amber-500 px-4 py-2 text-sm font-medium text-white shadow-md"
        data-testid="offline-banner"
      >
        <span className="h-2 w-2 rounded-full bg-white" />
        您已离线 — 显示的是缓存数据
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-2 bg-emerald-500 px-4 py-2 text-sm font-medium text-white shadow-md"
      data-testid="online-banner"
    >
      <span className="h-2 w-2 rounded-full bg-white" />
      已恢复连接
    </div>
  );
}

export default OfflineBanner;
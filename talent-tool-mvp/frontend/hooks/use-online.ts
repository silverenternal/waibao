"use client";

/**
 * T1205 — 检测在线/离线状态 hook.
 *
 * 用法:
 *   const { isOnline, wasOffline } = useOnline();
 *   if (!isOnline) return <OfflineBanner />;
 */
import { useEffect, useState } from "react";

export interface UseOnlineResult {
  isOnline: boolean;
  wasOffline: boolean; // 之前是否曾离线 (用于显示 "已恢复连接")
  lastChange: number | null;
}

export function useOnline(): UseOnlineResult {
  const [isOnline, setIsOnline] = useState<boolean>(() =>
    typeof navigator === "undefined" ? true : navigator.onLine
  );
  const [wasOffline, setWasOffline] = useState<boolean>(false);
  const [lastChange, setLastChange] = useState<number | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const onOnline = () => {
      setIsOnline(true);
      setLastChange(Date.now());
      // 3 秒后清除 wasOffline 标记
      window.setTimeout(() => setWasOffline(false), 3000);
    };
    const onOffline = () => {
      setIsOnline(false);
      setWasOffline(true);
      setLastChange(Date.now());
    };

    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  return { isOnline, wasOffline, lastChange };
}

export default useOnline;
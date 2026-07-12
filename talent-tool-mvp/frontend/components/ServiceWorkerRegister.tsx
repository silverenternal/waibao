"use client";

/**
 * T1205 — 注册 service worker.
 *
 * 仅生产环境 + 浏览器环境注册;开发环境跳过避免 SW 干扰 HMR.
 */
import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    if (process.env["NODE_ENV"] !== "production") {
      // 开发模式:跳过注册,但保留调试接口
      // eslint-disable-next-line no-console
      console.info("[pwa] dev mode — service worker disabled");
      return;
    }
    const onLoad = () => {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then((reg) => {
          // 监听 SW 更新
          reg.addEventListener("updatefound", () => {
            const newSw = reg.installing;
            if (!newSw) return;
            newSw.addEventListener("statechange", () => {
              if (newSw.state === "installed" && navigator.serviceWorker.controller) {
                // 新版本可用,提示用户刷新
                console.info("[pwa] new service worker available");
              }
            });
          });
        })
        .catch((err) => console.warn("[pwa] register failed", err));
    };
    if (document.readyState === "complete") onLoad();
    else window.addEventListener("load", onLoad);
    return () => window.removeEventListener("load", onLoad);
  }, []);

  return null;
}

export default ServiceWorkerRegister;
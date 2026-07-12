/**
 * T1205 — 离线 fallback 页面.
 *
 * Service Worker 在 network 失败时 fallback 到这个页面.
 */
export const dynamic = "force-static";
export const dynamicParams = true;
// 跳过 Supabase client 的初始化,避免在 prerender 时因缺 env 报错.
export const fetchCache = "force-no-store";

export default function OfflinePage() {
  return (
    <main className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <div className="mb-6 text-6xl" aria-hidden>
        ?
      </div>
      <h1 className="text-2xl font-semibold text-slate-900">
        您已离线
      </h1>
      <p className="mt-3 max-w-md text-sm text-slate-600">
        当前没有可用的网络连接。请检查您的网络后重试。
        部分页面 (画像/政策/工单) 仍然可以从缓存中查看。
      </p>
      <a
        href="/"
        className="mt-6 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        返回首页
      </a>
    </main>
  );
}
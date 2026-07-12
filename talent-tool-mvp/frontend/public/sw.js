/* T1205 — waibao PWA Service Worker.
 *
 * 缓存策略:
 *   画像 / 政策 / 工单列表 (stale-while-revalidate)
 *   战略地图 (cache-first)
 *   智能对话 (network-only, 失败 → 离线提示)
 *   静态资源 (cache-first, 长 TTL)
 *   页面 shell (Network-first, fallback cache)
 */

const VERSION = 'waibao-v4.0.0';
const STATIC_CACHE = `${VERSION}-static`;
const RUNTIME_CACHE = `${VERSION}-runtime`;
const STRATEGY_CACHE = `${VERSION}-strategy`;
const API_CACHE = `${VERSION}-api`;

const PRECACHE_URLS = [
  '/',
  '/tickets',
  '/strategy',
  '/profile',
  '/policy',
  '/chat',
  '/manifest.json',
  '/offline',
];

// ------------------------------------------------------------------
// install — precache app shell
// ------------------------------------------------------------------
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// ------------------------------------------------------------------
// activate — clean old caches
// ------------------------------------------------------------------
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => !k.startsWith(VERSION))
          .map((k) => caches.delete(k))
      );
      await self.clients.claim();
    })()
  );
});

// ------------------------------------------------------------------
// fetch — route to strategy
// ------------------------------------------------------------------
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // 静态资源 (Next.js /_next/static + /icons)
  if (
    url.pathname.startsWith('/_next/static') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.woff2')
  ) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // 战略地图 — cache-first
  if (url.pathname.startsWith('/api/strategy') || url.pathname === '/strategy') {
    event.respondWith(cacheFirst(request, STRATEGY_CACHE));
    return;
  }

  // 智能对话 — network-only, 失败抛错
  if (url.pathname.startsWith('/api/chat') || url.pathname === '/chat') {
    event.respondWith(networkOnly(request));
    return;
  }

  // 画像 / 政策 / 工单列表 — stale-while-revalidate
  if (
    url.pathname.startsWith('/api/profile') ||
    url.pathname.startsWith('/api/policy') ||
    url.pathname.startsWith('/api/tickets') ||
    url.pathname === '/profile' ||
    url.pathname === '/policy' ||
    url.pathname === '/tickets'
  ) {
    event.respondWith(staleWhileRevalidate(request, API_CACHE));
    return;
  }

  // API 默认 — network-first, 失败 cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, RUNTIME_CACHE));
    return;
  }

  // 页面导航 — network-first, 失败 fallback /offline
  if (request.mode === 'navigate') {
    event.respondWith(navigationStrategy(request));
    return;
  }
});

// ------------------------------------------------------------------
// Strategies
// ------------------------------------------------------------------
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const fresh = await fetch(request);
    if (fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  } catch (err) {
    return new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((res) => {
      if (res.ok) cache.put(request, res.clone());
      return res;
    })
    .catch(() => null);
  return cached || (await networkPromise) || new Response(JSON.stringify({ offline: true }), {
    status: 503,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const fresh = await fetch(request);
    if (fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: 'offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function networkOnly(request) {
  try {
    return await fetch(request);
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: 'offline',
        message: '智能对话需要联网 — please reconnect and retry.',
      }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

async function navigationStrategy(request) {
  try {
    return await fetch(request);
  } catch (err) {
    const cache = await caches.open(STATIC_CACHE);
    const offline = await cache.match('/offline');
    return offline || new Response('Offline', { status: 503 });
  }
}

// ------------------------------------------------------------------
// message — client can trigger skipWaiting
// ------------------------------------------------------------------
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});
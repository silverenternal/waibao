/**
 * T1803 — 前端漏斗埋点 SDK.
 *
 * 关键事件:
 *   sourced / applied / screened / interviewed / offered / hired
 *
 * 设计:
 * - 在浏览器侧维护一个 in-memory 队列 + sessionStorage 持久化(避免刷新丢失)
 * - 上报使用 `navigator.sendBeacon` (失败时降级到 fetch keepalive)
 * - 用户未登录也允许埋点 (candidate_id 临时用 sessionStorage UUID 兜底)
 */

import { apiClient } from "@/lib/api-client";

const QUEUE_KEY = "funnel:queue:v1";
const SESSION_UUID_KEY = "funnel:session:uuid";
const ANON_CANDIDATE_KEY = "funnel:anon:candidate_id";

export type FunnelStageName =
  | "sourced"
  | "applied"
  | "screened"
  | "interviewed"
  | "offered"
  | "hired";

export interface FunnelTrackPayload {
  stage: FunnelStageName;
  source?: string;
  candidate_id?: string;
  role_id?: string;
  cost_cents?: number;
  metadata?: Record<string, unknown>;
}

interface QueuedEvent extends FunnelTrackPayload {
  occurred_at: string;
  candidate_id: string;
  session_id: string;
}

function getOrCreateUUID(key: string): string {
  if (typeof window === "undefined") return "";
  let v = window.sessionStorage.getItem(key);
  if (!v) {
    v =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `anon-${Math.random().toString(36).slice(2)}-${Date.now()}`;
    window.sessionStorage.setItem(key, v);
  }
  return v;
}

function loadQueue(): QueuedEvent[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(QUEUE_KEY);
    return raw ? (JSON.parse(raw) as QueuedEvent[]) : [];
  } catch {
    return [];
  }
}

function saveQueue(q: QueuedEvent[]): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(QUEUE_KEY, JSON.stringify(q));
  } catch {
    /* quota exceeded — drop */
  }
}

/**
 * 入队一个埋点事件。立刻触发 flush (best effort)。
 */
export function trackFunnelEvent(payload: FunnelTrackPayload): void {
  if (typeof window === "undefined") return;

  const sessionId = getOrCreateUUID(SESSION_UUID_KEY);
  const candidateId =
    payload.candidate_id ||
    (typeof window !== "undefined"
      ? window.sessionStorage.getItem(ANON_CANDIDATE_KEY) ||
        getOrCreateUUID(ANON_CANDIDATE_KEY)
      : "anon");

  const event: QueuedEvent = {
    ...payload,
    candidate_id: candidateId,
    session_id: sessionId,
    occurred_at: new Date().toISOString(),
  };

  const queue = loadQueue();
  queue.push(event);
  // 限制队列大小
  while (queue.length > 200) queue.shift();
  saveQueue(queue);

  void flushFunnelQueue();
}

/**
 * 把队列里的事件 POST 给后端。
 */
export async function flushFunnelQueue(): Promise<void> {
  if (typeof window === "undefined") return;
  const queue = loadQueue();
  if (queue.length === 0) return;

  try {
    await apiClient.analytics.recordFunnelEvents(
      queue.map((e) => ({
        candidate_id: e.candidate_id,
        stage: e.stage,
        source: e.source ?? "frontend",
        role_id: e.role_id,
        cost_cents: e.cost_cents ?? 0,
        metadata: { ...(e.metadata ?? {}), session_id: e.session_id },
        occurred_at: e.occurred_at,
      })),
    );
    // 成功后清空队列
    saveQueue([]);
  } catch (err) {
    console.warn("[funnel-tracker] flush failed", err);
  }
}

/**
 * 在页面关闭/隐藏时尝试 sendBeacon 上报(兜底)。
 */
export function installUnloadFlush(): void {
  if (typeof window === "undefined") return;
  const handler = () => {
    const queue = loadQueue();
    if (queue.length === 0) return;
    const blob = new Blob([JSON.stringify({ events: queue })], {
      type: "application/json",
    });
    try {
      navigator.sendBeacon?.("/api/analytics/funnel/events", blob);
    } catch {
      /* ignore */
    }
  };
  window.addEventListener("pagehide", handler);
  window.addEventListener("beforeunload", handler);
}

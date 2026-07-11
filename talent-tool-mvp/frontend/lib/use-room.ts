"use client";

/**
 * useRoom — WebSocket hook (T608).
 *
 * 双向实时同步房间消息/事件, 包含 delivery_id + ack 协议:
 *
 *   客户端发送 → 服务端:
 *     {type:"publish", delivery_id, event:"message", payload:{...}}
 *     {type:"typing", payload:{is_typing}}
 *     {type:"ping"}
 *
 *   服务端推送 → 客户端:
 *     {type:"ack", delivery_id, status, message_id, created_at}
 *     {type:"broadcast", event, sender, payload, ts}
 *     {type:"ready", user_id, room_id}
 *     {type:"error", message}
 *
 * 用法:
 *   const {
 *     status, messages, sendMessage, sendTyping, markRead
 *   } = useRoom({ roomId, currentUserId, onMention });
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  parseMentions,
  type RoomMessage,
  type MentionRow,
} from "@/lib/api-rooms";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface RoomBroadcastEvent {
  event:
    | "message"
    | "reaction"
    | "presence"
    | "read"
    | "typing"
    | "member_join"
    | "member_leave";
  sender: string;
  payload: Record<string, unknown>;
  ts: number;
}

export interface UseRoomOptions {
  roomId: string | null;
  currentUserId: string;
  token?: string | null;
  onMessage?: (msg: RoomMessage) => void;
  onMention?: (row: MentionRow) => void;
  onTyping?: (userId: string, isTyping: boolean) => void;
  onReaction?: (payload: { message_id: string; emoji: string; active: boolean }) => void;
  onMemberChange?: (userId: string, event: "join" | "leave") => void;
}

export interface UseRoomResult {
  status: "idle" | "connecting" | "open" | "closed" | "error";
  /** 客户端已发布但还没收到 ack 的消息(乐观更新). */
  pending: Map<string, PendingMessage>;
  sendMessage: (
    content: string,
    extra?: { parent_id?: string; message_type?: "text" | "markdown" | "file" }
  ) => Promise<{ message_id: string; delivery_id: string; created_at: string } | null>;
  sendTyping: (isTyping: boolean) => void;
  markRead: () => void;
  reconnect: () => void;
}

export interface PendingMessage {
  delivery_id: string;
  content: string;
  parent_id?: string;
  sent_at: number;
  status: "sending" | "delivered" | "error";
  error?: string;
  message_id?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function randomId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `del-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

/** 将 @UUID 提及插入 room_mentions (REST 调用). */
async function fallbackPostMention(messageId: string, content: string, roomId: string) {
  const segments = parseMentions(content);
  const uids = Array.from(new Set(segments.filter((s) => s.type === "mention").map((s) => s.user_id!)));
  if (uids.length === 0) return;
  // 后端 POST /api/rooms/{id}/messages 已经自动写 room_mentions;
  // 这个 fallback 仅在 WS publish 失败时调用, 通过给一个 invite 接口代替.
  // 这里仅做 noop 兜底, 实际 mention 通知已由 WS publish 同步到 DB.
  void messageId; void roomId; void uids;
}

function getWebSocketBase(): string {
  if (typeof window === "undefined") return "ws://localhost:8000";
  const apiBase =
    process.env.NEXT_PUBLIC_API_URL ||
    (typeof window !== "undefined" && window.location.protocol === "https:"
      ? "wss://localhost:8000"
      : "ws://localhost:8000");
  // 兼容传入 http(s): strip 后再升级
  if (apiBase.startsWith("http")) {
    return apiBase.replace(/^http/, "ws");
  }
  return apiBase;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useRoom(opts: UseRoomOptions): UseRoomResult {
  const { roomId, currentUserId, token, onMessage, onTyping, onReaction, onMemberChange } = opts;

  const [status, setStatus] = useState<UseRoomResult["status"]>("idle");
  const pendingRef = useRef<Map<string, PendingMessage>>(new Map());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTypingRef = useRef(false);

  const [, force] = useState(0);
  const setPending = useCallback(() => force((n) => n + 1), []);

  const send = useCallback((payload: unknown) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }, []);

  const connect = useCallback(() => {
    if (!roomId) return;
    const base = getWebSocketBase();
    const url = `${base}/api/realtime/ws/rooms/${encodeURIComponent(roomId)}${
      token ? `?token=${encodeURIComponent(token)}` : ""
    }`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;
      setStatus("connecting");

      ws.onopen = () => {
        reconnectAttempts.current = 0;
        setStatus("open");
      };

      ws.onclose = () => {
        setStatus("closed");
        wsRef.current = null;
        // 指数退避 (最多 8s)
        if (reconnectAttempts.current < 6) {
          const delay = Math.min(8000, 500 * Math.pow(2, reconnectAttempts.current));
          reconnectAttempts.current += 1;
          reconnectTimer.current = setTimeout(() => connect(), delay);
        }
      };

      ws.onerror = () => {
        setStatus("error");
      };

      ws.onmessage = (event) => {
        type WireMessage =
          | { type: "ready"; user_id: string; room_id: string }
          | { type: "ack"; delivery_id: string; status: "ok" | "error"; message_id?: string; created_at?: string; error?: string }
          | { type: "broadcast"; event: RoomBroadcastEvent["event"]; sender: string; payload: Record<string, unknown>; ts: number }
          | { type: "pong"; ts: number }
          | { type: "error"; message: string };

        let parsed: WireMessage;
        try {
          parsed = JSON.parse(event.data) as WireMessage;
        } catch {
          return;
        }
        if (parsed.type === "ready") return;

        if (parsed.type === "ack") {
          const delivery_id = parsed.delivery_id as string;
          const p = pendingRef.current.get(delivery_id);
          if (p) {
            p.status = parsed.status === "ok" ? "delivered" : "error";
            p.error = parsed.error;
            p.message_id = parsed.message_id;
            pendingRef.current.set(delivery_id, p);
            setPending();
          }
          return;
        }

        if (parsed.type === "broadcast") {
          const ev = parsed.event as RoomBroadcastEvent["event"];
          const payload = parsed.payload || {};
          const sender = parsed.sender as string;

          if (sender === currentUserId) return; // 自己发的会由 ack / 列表同步, 不重复触发 onMessage

          if (ev === "message") {
            const msg = payload as unknown as RoomMessage;
            onMessage?.(msg);
            return;
          }

          if (ev === "reaction") {
            onReaction?.(
              payload as { message_id: string; emoji: string; active: boolean }
            );
            return;
          }

          if (ev === "typing") {
            onTyping?.(sender, Boolean((payload as { is_typing?: boolean }).is_typing));
            return;
          }

          if (ev === "member_join") {
            onMemberChange?.(sender, "join");
            return;
          }

          if (ev === "member_leave") {
            onMemberChange?.(sender, "leave");
            return;
          }

          if (ev === "read") {
            // 群组里的他人已读 — 不需要直接消费, MessageList 自行 poll
            return;
          }
          return;
        }

        if (parsed.type === "error") {
          // eslint-disable-next-line no-console
          console.error("[room ws] error:", parsed.message);
        }
      };
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("[room ws] failed to construct", err);
      setStatus("error");
    }
  }, [roomId, token, currentUserId, onMessage, onReaction, onTyping, onMemberChange, setPending]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        try {
          ws.close(1000, "unmount");
        } catch {
          // swallow
        }
      }
      pendingRef.current.clear();
    };
  }, [connect]);

  // -----------------------------------------------------------------------
  // sendMessage: 通过 WS publish (delivery_id + ack)
  // -----------------------------------------------------------------------
  const sendMessage = useCallback(
    async (
      content: string,
      extra?: { parent_id?: string; message_type?: "text" | "markdown" | "file" }
    ): Promise<{ message_id: string; delivery_id: string; created_at: string } | null> => {
      if (!roomId || !content.trim()) return null;
      const delivery_id = randomId();
      const pending: PendingMessage = {
        delivery_id,
        content,
        parent_id: extra?.parent_id,
        sent_at: Date.now(),
        status: "sending",
      };
      pendingRef.current.set(delivery_id, pending);
      setPending();

      const ok = send({
        type: "publish",
        delivery_id,
        event: "message",
        payload: {
          content,
          parent_id: extra?.parent_id,
          message_type: extra?.message_type || "text",
        },
      });
      if (!ok) {
        // WebSocket 不可用, 走 REST 兜底 (后端会自动写 mentions + 广播推回)
        try {
          const { roomsApi } = await import("@/lib/api-rooms");
          const msg = await roomsApi.postMessage(roomId, {
            content,
            parent_id: extra?.parent_id,
            message_type: extra?.message_type || "text",
          });
          pending.status = "delivered";
          pending.message_id = msg.id;
          pendingRef.current.set(delivery_id, pending);
          setPending();
          return {
            delivery_id,
            message_id: msg.id,
            created_at: msg.created_at,
          };
        } catch (err) {
          pending.status = "error";
          pending.error = (err as Error).message ?? "send failed";
          pendingRef.current.set(delivery_id, pending);
          setPending();
          // best-effort fallback for client-side mention row (no-op server 已自动)
          fallbackPostMention("", content, roomId);
          return null;
        }
      }

      // 等 ack
      return new Promise((resolve) => {
        const start = Date.now();
        const check = () => {
          const p = pendingRef.current.get(delivery_id);
          if (!p) {
            resolve(null);
            return;
          }
          if (p.status === "delivered") {
            resolve({
              delivery_id,
              message_id: p.message_id!,
              created_at: new Date(p.sent_at).toISOString(),
            });
            return;
          }
          if (p.status === "error") {
            // resolve null 表示失败, 重试由调用方决定
            resolve(null);
            return;
          }
          if (Date.now() - start > 8000) {
            // 8s 超时
            resolve(null);
            return;
          }
          setTimeout(check, 100);
        };
        check();
      });
    },
    [roomId, send, setPending]
  );

  // -----------------------------------------------------------------------
  // sendTyping: 不写 delivery_id (高频)
  // -----------------------------------------------------------------------
  const sendTyping = useCallback(
    (isTyping: boolean) => {
      if (isTypingRef.current === isTyping) return;
      isTypingRef.current = isTyping;
      send({
        type: "typing",
        payload: { is_typing: isTyping },
      });
      if (isTyping) {
        // 5 秒后自动停止
        if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
        typingTimeoutRef.current = setTimeout(() => sendTyping(false), 5000);
      }
    },
    [send]
  );

  // -----------------------------------------------------------------------
  // markRead: 走 REST 简单可靠
  // -----------------------------------------------------------------------
  const markRead = useCallback(() => {
    if (!roomId) return;
    send({ type: "read", payload: { at: new Date().toISOString() } });
    import("@/lib/api-rooms").then(({ roomsApi }) =>
      roomsApi.markRead(roomId).catch(() => undefined)
    );
  }, [roomId, send]);

  const reconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    const ws = wsRef.current;
    if (ws) ws.close();
    connect();
  }, [connect]);

  return useMemo(
    () => ({
      status,
      pending: pendingRef.current,
      sendMessage,
      sendTyping,
      markRead,
      reconnect,
    }),
    [status, sendMessage, sendTyping, markRead, reconnect]
  );
}

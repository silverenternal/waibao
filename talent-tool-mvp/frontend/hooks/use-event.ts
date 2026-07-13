"use client";

/**
 * useEvent — front-end subscriber for the waibao EventBus.
 *
 * Opens an SSE connection to GET /api/events/stream?topics=foo,bar and
 * returns the latest event payload received for the given topic. The
 * hook is automatically cleaned up on unmount.
 *
 * Usage:
 *
 *     const profile = useEvent("profile.updated", { token });
 *
 * `profile` is `{ event: Event | null, lastEventId: string | null }`.
 *
 * In React components, pair it with a refetch:
 *
 *     const { event } = useEvent("profile.updated");
 *     React.useEffect(() => { if (event) refetch(); }, [event]);
 *
 * SSE is supported in all evergreen browsers; if EventSource is
 * missing, the hook no-ops cleanly.
 */

import * as React from "react";

export interface WbEvent {
  name: string;
  payload: Record<string, unknown>;
  source?: string;
  correlation_id?: string | null;
  event_id: string;
  timestamp: number;
}

export interface UseEventResult {
  event: WbEvent | null;
  lastEventId: string | null;
  error: Error | null;
  connected: boolean;
}

export interface UseEventOptions {
  /** Optional bearer token (forwarded to the API). */
  token?: string;
  /** Disable the connection (e.g. when not in the right persona). */
  enabled?: boolean;
  /** Reconnect delay (ms). Default 1500. */
  reconnectMs?: number;
}

export function useEvent(
  topic: string,
  options: UseEventOptions = {},
): UseEventResult {
  const { token, enabled = true, reconnectMs = 1500 } = options;
  const [event, setEvent] = React.useState<WbEvent | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [connected, setConnected] = React.useState(false);

  React.useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    if (typeof EventSource === "undefined") {
      setError(new Error("EventSource not supported in this browser"));
      return;
    }

    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const open = () => {
      const url = `/api/events/stream?topics=${encodeURIComponent(topic)}`;
      try {
        es = token
          ? new EventSource(url, { withCredentials: true } as any)
          : new EventSource(url);
      } catch (err) {
        setError(err as Error);
        return;
      }

      es.addEventListener("open", () => setConnected(true));
      es.addEventListener("error", () => {
        setConnected(false);
        if (cancelled) return;
        reconnectTimer = setTimeout(open, reconnectMs);
      });

      es.addEventListener(topic, (raw: MessageEvent) => {
        try {
          const data: WbEvent = JSON.parse(raw.data);
          setEvent(data);
          setError(null);
        } catch (err) {
          setError(err as Error);
        }
      });

      // Generic "message" events still arrive when backend uses a single
      // SSE channel with a `topic` field in the payload.
      es.addEventListener("message", (raw: MessageEvent) => {
        try {
          const data: WbEvent = JSON.parse(raw.data);
          if (data?.name !== topic) return;
          setEvent(data);
          setError(null);
        } catch {
          // ignore malformed
        }
      });
    };

    open();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (es) {
        es.close();
        setConnected(false);
      }
    };
  }, [topic, token, enabled, reconnectMs]);

  return {
    event,
    lastEventId: event?.event_id ?? null,
    error,
    connected,
  };
}

export interface UseEventBusOptions extends UseEventOptions {
  /** Optional whitelist; events not in this list are ignored. */
  filterTopics?: string[];
}

export interface UseEventBus extends UseEventResult {
  topic: string | null;
  /**
   * Subscribe to incoming events for a specific topic. Returns an
   * unsubscribe function. Works whether or not the bus is bound to a
   * topic whitelist at construction time.
   */
  subscribe: (
    topic: string,
    handler: (evt: WbEvent) => void
  ) => () => void;
}

/**
 * Listen to multiple topics at once. Returns the latest event of any of
 * the supplied topics. The `topics` argument is optional — callers that
 * only need a generic `subscribe` API can omit it.
 */
export function useEventBus(
  topics?: string[],
  options: UseEventBusOptions = {},
): UseEventBus {
  const topicList = topics ?? [];
  const joined = topicList.join(",");
  const { token, enabled = true } = options;
  const [event, setEvent] = React.useState<WbEvent | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [connected, setConnected] = React.useState(false);
  const handlersRef = React.useRef<Map<string, Set<(evt: WbEvent) => void>>>(
    new Map()
  );

  React.useEffect(() => {
    if (!enabled || topicList.length === 0 || typeof window === "undefined") {
      return;
    }
    if (typeof EventSource === "undefined") {
      setError(new Error("EventSource not supported"));
      return;
    }

    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const open = () => {
      const url = `/api/events/stream?topics=${encodeURIComponent(joined)}`;
      es = new EventSource(url);
      es.addEventListener("open", () => setConnected(true));
      es.addEventListener("error", () => {
        setConnected(false);
        if (!cancelled) reconnectTimer = setTimeout(open, 1500);
      });
      es.addEventListener("message", (raw: MessageEvent) => {
        try {
          const data: WbEvent = JSON.parse(raw.data);
          if (!topicList.includes(data.name)) return;
          if (
            options.filterTopics &&
            !options.filterTopics.includes(data.name)
          ) {
            return;
          }
          setEvent(data);
          setError(null);
          // Dispatch to subscribers (used by useFeatureFlag, useServiceToggle).
          const subs = handlersRef.current.get(data.name);
          if (subs) {
            for (const fn of subs) {
              try {
                fn(data);
              } catch {
                /* swallow subscriber errors */
              }
            }
          }
        } catch {
          /* ignore malformed */
        }
      });
    };

    open();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (es) {
        es.close();
        setConnected(false);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined, token, enabled]);

  const subscribe = React.useCallback(
    (topic: string, handler: (evt: WbEvent) => void) => {
      let set = handlersRef.current.get(topic);
      if (!set) {
        set = new Set();
        handlersRef.current.set(topic, set);
      }
      set.add(handler);
      return () => {
        set?.delete(handler);
        if (set && set.size === 0) {
          handlersRef.current.delete(topic);
        }
      };
    },
    []
  );

  return {
    event,
    lastEventId: event?.event_id ?? null,
    error,
    connected,
    topic: event?.name ?? null,
    subscribe,
  };
}

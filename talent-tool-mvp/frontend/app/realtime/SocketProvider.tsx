"use client";

import { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";

type Message = {
  type: "ready" | "start" | "chunk" | "done" | "error";
  text?: string;
  agent?: string;
  artifacts?: Record<string, unknown>;
  request_id?: string;
  message?: string;
};

type AgentContext = {
  connected: boolean;
  invoke: (text: string, agentName?: string, context?: Record<string, unknown>) => Promise<string>;
  streaming: boolean;
  currentChunk: string;
};

const Ctx = createContext<AgentContext | null>(null);

export function SocketProvider({ children, token }: { children: ReactNode; token: string }) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [currentChunk, setCurrentChunk] = useState("");
  const resolvers = useRef<Map<string, (text: string) => void>>(new Map());

  useEffect(() => {
    if (!token) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.hostname}:8000/api/realtime/ws/invoke?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (e) => {
      try {
        const msg: Message = JSON.parse(e.data);
        if (msg.type === "start") {
          setStreaming(true);
          setCurrentChunk("");
        } else if (msg.type === "chunk") {
          setCurrentChunk((c) => c + (msg.text || ""));
        } else if (msg.type === "done") {
          setStreaming(false);
          const r = resolvers.current.get(msg.request_id || "");
          if (r) {
            r(currentChunkRef.current);
            resolvers.current.delete(msg.request_id || "");
          }
          setCurrentChunk("");
        } else if (msg.type === "error") {
          setStreaming(false);
          const r = resolvers.current.get(msg.request_id || "");
          if (r) {
            r("[ERROR] " + (msg.message || ""));
            resolvers.current.delete(msg.request_id || "");
          }
        }
      } catch {}
    };
    return () => ws.close();
  }, [token]);

  const currentChunkRef = useRef("");
  useEffect(() => {
    currentChunkRef.current = currentChunk;
  }, [currentChunk]);

  const invoke = async (text: string, agentName?: string, context?: Record<string, unknown>) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket 未连接");
    }
    return new Promise<string>((resolve) => {
      const reqId = Math.random().toString(36).slice(2, 14);
      resolvers.current.set(reqId, resolve);
      wsRef.current!.send(JSON.stringify({
        text,
        agent_name: agentName || "",
        context: context || {},
        request_id: reqId,
      }));
    });
  };

  return (
    <Ctx.Provider value={{ connected, invoke, streaming, currentChunk }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAgent() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAgent must be inside SocketProvider");
  return ctx;
}
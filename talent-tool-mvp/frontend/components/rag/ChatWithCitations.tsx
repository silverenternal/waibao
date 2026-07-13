"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, MessageSquare, Send, ExternalLink, FileText } from "lucide-react";

export interface Citation {
  document_id: string;
  chunk_id: string;
  document_name: string;
  position: number;
  snippet: string;
  score: number;
  rerank_score?: number | null;
  token: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  retrieval_ms?: number;
  generation_ms?: number;
  total_ms?: number;
  timestamp: number;
}

export interface ChatWithCitationsProps {
  collectionId: string;
  apiBase?: string;
  topK?: number;
  mode?: "vector" | "bm25" | "hybrid";
  placeholder?: string;
  onCitationClick?: (citation: Citation) => void;
}

const CITATION_REGEX = /\[([0-9a-f]{8}):([0-9a-f]{8})\]/g;

function renderWithCitations(
  text: string,
  citations: Citation[] | undefined,
  onClick?: (c: Citation) => void,
): React.ReactNode {
  if (!citations || citations.length === 0) return text;
  const byToken = new Map<string, Citation>();
  for (const c of citations) byToken.set(c.token, c);

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = CITATION_REGEX.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    const citation = byToken.get(token);
    parts.push(
      <button
        key={`cit-${key++}`}
        type="button"
        onClick={() => citation && onClick?.(citation)}
        className={
          "mx-0.5 inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium transition " +
          (citation
            ? "bg-primary/10 text-primary hover:bg-primary/20"
            : "bg-muted text-muted-foreground")
        }
        title={citation?.document_name ?? token}
      >
        <FileText className="mr-1 h-3 w-3" />
        {token}
      </button>,
    );
    lastIndex = match.index + token.length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return <>{parts}</>;
}

export function ChatWithCitations({
  collectionId,
  apiBase = "/api/rag",
  topK = 5,
  mode = "hybrid",
  placeholder = "问我任何关于该知识库的问题 ...",
  onCitationClick,
}: ChatWithCitationsProps) {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

  const send = React.useCallback(async () => {
    const q = input.trim();
    if (!q || busy) return;
    setError(null);
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: q,
      timestamp: Date.now(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch(`${apiBase}/query`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          collection_id: collectionId,
          top_k: topK,
          mode,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Query failed (${res.status})`);
      }
      const data = await res.json();
      const assistant: ChatMessage = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: data.answer,
        citations: data.citations,
        retrieval_ms: data.retrieval_ms,
        generation_ms: data.generation_ms,
        total_ms: data.total_ms,
        timestamp: Date.now(),
      };
      setMessages((m) => [...m, assistant]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Query failed");
    } finally {
      setBusy(false);
    }
  }, [apiBase, busy, collectionId, input, mode, topK]);

  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, busy]);

  return (
    <Card className="flex h-[600px] flex-col">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5" />
          知识库对话 (带引用)
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3 overflow-hidden p-0">
        <ScrollArea className="flex-1 px-4 py-3" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="mt-12 text-center text-sm text-muted-foreground">
              <p>开始对话 — 答案将自动附带来源引用。</p>
              <p className="mt-1 text-xs">
                Top-K = {topK} · 模式 = {mode.toUpperCase()}
              </p>
            </div>
          )}
          <div className="space-y-4">
            {messages.map((m) => (
              <div
                key={m.id}
                className={
                  m.role === "user" ? "flex justify-end" : "flex justify-start"
                }
              >
                <div
                  className={
                    "max-w-[85%] rounded-lg px-3 py-2 text-sm " +
                    (m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted")
                  }
                >
                  <div className="whitespace-pre-wrap leading-relaxed">
                    {renderWithCitations(m.content, m.citations, onCitationClick)}
                  </div>
                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {m.citations.map((c) => (
                        <button
                          key={c.chunk_id}
                          type="button"
                          onClick={() => onCitationClick?.(c)}
                          className="inline-flex items-center gap-1 rounded bg-background/60 px-1.5 py-0.5 text-[10px] hover:bg-background"
                        >
                          <ExternalLink className="h-3 w-3" />
                          {c.document_name} #{c.position}
                        </button>
                      ))}
                    </div>
                  )}
                  {m.role === "assistant" && m.total_ms != null && (
                    <div className="mt-1 text-[10px] text-muted-foreground">
                      检索 {m.retrieval_ms}ms · 生成 {m.generation_ms}ms · 总 {m.total_ms}ms
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在检索 + 生成 ...
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        {error && (
          <div className="mx-4 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}

        <div className="border-t p-3">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={placeholder}
              className="flex-1 rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              disabled={busy}
            />
            <Button type="submit" disabled={busy || !input.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
          <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground">
            <Badge variant="outline">LlamaIndex</Badge>
            <Badge variant="outline">Qdrant</Badge>
            <Badge variant="outline">BGE-reranker</Badge>
            <span>· 来源 token: [doc8:chunk8]</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default ChatWithCitations;

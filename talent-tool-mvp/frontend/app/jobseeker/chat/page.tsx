"use client";

/**
 * v9.1 · 求职者 AI 聊天 (Open WebUI 风格)
 * --------------------------------------------------------------------
 * 三栏:会话列表 / 消息流 / 输入区。会话来自 mock,消息走 SSE 适配
 * (lib/sse.ts 风格)。语音输入走 Web Speech API;附件走 base64 inline。
 *
 * 兼容性:若稍后出现 components/jobseeker/* 同名导出,可被自然替换,
 * 此处不直接 import 以避免循环依赖。
 */

import * as React from "react";
import {
  ArrowDown,
  Check,
  FileText,
  Mic,
  MicOff,
  Paperclip,
  Pencil,
  Plus,
  Search,
  Send,
  Sparkles,
  Square,
  Trash2,
  Volume2,
  X,
} from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { MessageList } from "@/components/shared/MessageList";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { streamSSE } from "@/lib/sse";
import { cn } from "@/lib/utils";

// --------------------------------------------------------------------
// 1. 类型
// --------------------------------------------------------------------

interface Session {
  id: string;
  title: string;
  preview: string;
  updatedAt: string;
  pinned?: boolean;
  unread?: number;
}

interface PendingAttachment {
  id: string;
  name: string;
  size: number;
  mime: string;
  dataUrl: string;
}

const SUGGESTIONS = [
  {
    title: "复盘今天的 Tidewave 终面",
    prompt: "请复盘我今天 Tidewave 技术终面的表现,给三个改进点。",
  },
  {
    title: "起草英文感谢信",
    prompt: "帮我写一封 200 字以内的英文面试感谢信。",
  },
  {
    title: "Tidewave 议价 92k",
    prompt: "Tidewave 给我开了 82k,我想谈到 92k,给我一份议价话术。",
  },
  {
    title: "本周情绪总结",
    prompt: "整理我 7/7 – 7/13 的情绪和日记,给我一份周记。",
  },
];

// --------------------------------------------------------------------
// 2. Mock 会话 + 初始消息
// --------------------------------------------------------------------

const INITIAL_SESSIONS: Session[] = [
  {
    id: "s-1",
    title: "Tidewave 面试复盘",
    preview: "技术终面整体顺利,接下来聊薪资…",
    updatedAt: "刚刚",
    pinned: true,
  },
  {
    id: "s-2",
    title: "职业方向:Copilot 还是金融科技?",
    preview: "想听听 AI 的对比和过去 12 个月趋势",
    updatedAt: "2 小时前",
    unread: 1,
  },
  {
    id: "s-3",
    title: "简历润色 · Frontend Lead",
    preview: "请帮我把 2024 Q2 经历改写成故事化",
    updatedAt: "昨天",
  },
  {
    id: "s-4",
    title: "情绪周记 7/7 – 7/13",
    preview: "整理过去一周的日记和情绪,生成总结",
    updatedAt: "周一",
  },
  {
    id: "s-5",
    title: "和 Lily 顾问的议价建议",
    preview: "Tidewave 给我开了 82k,我想要 92k",
    updatedAt: "上周",
  },
];

const INITIAL_MESSAGES: Record<string, ChatMessage[]> = {
  "s-1": [
    {
      id: "m-1",
      role: "user",
      content: "今天 Tidewave 技术终面结束了,感觉算法题都做出来了,聊项目时被打断了几次,是不是扣分项?",
      author: "我",
      createdAt: "14:32",
    },
    {
      id: "m-2",
      role: "assistant",
      content:
        "面试官在技术环节打断通常是想**节约时间追问重点**,不是负面信号。\n\n可以做两件事:\n1. 面试结束后主动发一封**精简感谢信**(200 字内),把被打断的两个点用 1 句话补全结论。\n2. 趁热把你最满意的**项目例子**写下来,作为接下来议价和谈薪的素材。\n\n要不要我帮你起一份感谢信草稿?",
      author: "AI Copilot",
      createdAt: "14:32",
    },
    {
      id: "m-3",
      role: "user",
      content: "好,帮我写一封中文+英文双语,200 字以内。",
      author: "我",
      createdAt: "14:33",
    },
  ],
  "s-2": [
    {
      id: "m-1",
      role: "user",
      content: "Copilot 方向和金融科技方向,过去 12 个月哪个更稳?",
      author: "我",
      createdAt: "11:02",
    },
  ],
  "s-3": [
    {
      id: "m-1",
      role: "user",
      content: "请把我 2024 Q2 主导的设计系统迁移,改写成更故事化的版本。",
      author: "我",
      createdAt: "昨天 21:14",
    },
    {
      id: "m-2",
      role: "assistant",
      content:
        "可以,推荐用 **SCQA + 数字结果** 的结构。给你一版 90 字的精炼:\n\n> 2024 Q2,在 Tidewave 主导前端设计系统迁移(Situation-Complication)。面对 12 个仓库 / 5 套主题割裂(Complication),设计并交付 **v2 主题 + 88 个共享组件**,推动 9 支团队切换,首屏体积下降 38%(Answer)。",
      author: "AI Copilot",
      createdAt: "昨天 21:14",
    },
  ],
  "s-4": [],
  "s-5": [],
};

// 复用 shared ChatMessage 类型
type ChatMessage = import("@/components/shared/ChatBubble").ChatMessage;

// --------------------------------------------------------------------
// 3. 工具
// --------------------------------------------------------------------

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

// --------------------------------------------------------------------
// 4. 语音输入 hook(Web Speech API)
// --------------------------------------------------------------------

interface SpeechRecognitionLike {
  start: () => void;
  stop: () => void;
  abort: () => void;
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((e: { results: { transcript: string; isFinal?: boolean }[][] }) => void) | null;
  onerror: ((e: unknown) => void) | null;
  onend: (() => void) | null;
}

function useSpeechToText() {
  const [supported, setSupported] = React.useState(false);
  const [listening, setListening] = React.useState(false);
  const [transcript, setTranscript] = React.useState("");
  const recRef = React.useRef<SpeechRecognitionLike | null>(null);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const w = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) return;
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = "zh-CN";
    r.onresult = (e) => {
      const pieces = e.results
        .map((r) => r[0]?.transcript ?? "")
        .join("")
        .trim();
      setTranscript(pieces);
    };
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    recRef.current = r;
    setSupported(true);
  }, []);

  const start = React.useCallback(() => {
    if (!recRef.current) return;
    setTranscript("");
    try {
      recRef.current.start();
      setListening(true);
    } catch {
      // start() throws if already started — ignore
    }
  }, []);

  const stop = React.useCallback(() => {
    recRef.current?.stop();
    setListening(false);
  }, []);

  return { supported, listening, transcript, start, stop, setTranscript };
}

// --------------------------------------------------------------------
// 5. SSE 适配:模拟一个能"打字"的助手
// --------------------------------------------------------------------

/**
 * 把本地"打字机"效果包成 SSE 风格,让 lib/sse.ts 的 streamSSE 同样可用。
 * 真实接口会替换为 streamSSE<T>({ url: "/api/chat", body, onData, ... })
 *
 * 下面保留一个用 streamSSE 的引用,作为"接入示例"占位,避免 unused 警告。
 */
void streamSSE;

/**
 * 简单按字符分块,每 18ms 一个字,模拟打字节奏。
 */
function streamMockReply(
  text: string,
  onChunk: (delta: string) => void,
  onDone: () => void,
  signal?: AbortSignal,
) {
  const chunks = text.split(/(\s+)/); // 保留空格
  let i = 0;
  let cancelled = false;
  const handleAbort = () => {
    cancelled = true;
  };
  signal?.addEventListener("abort", handleAbort);
  const tick = () => {
    if (cancelled) return;
    if (i >= chunks.length) {
      signal?.removeEventListener("abort", handleAbort);
      onDone();
      return;
    }
    onChunk(chunks[i] ?? "");
    i += 1;
    setTimeout(tick, 18);
  };
  tick();
}

// --------------------------------------------------------------------
// 6. 页面
// --------------------------------------------------------------------

export default function JobseekerChatPage() {
  const [sessions, setSessions] = React.useState<Session[]>(INITIAL_SESSIONS);
  const [activeId, setActiveId] = React.useState<string>(INITIAL_SESSIONS[0].id);
  const [query, setQuery] = React.useState("");
  const [messagesBySession, setMessagesBySession] =
    React.useState<Record<string, ChatMessage[]>>(INITIAL_MESSAGES);
  const [draft, setDraft] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const [attachments, setAttachments] = React.useState<PendingAttachment[]>([]);
  const [showJump, setShowJump] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  const speech = useSpeechToText();

  // 会话切换时,合并"语音待发送文字"到草稿
  React.useEffect(() => {
    if (speech.transcript) setDraft((d) => d + speech.transcript);
  }, [speech.transcript]);

  // 监听流式消息 → 自动滚到底
  React.useEffect(() => {
    if (!showJump) {
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messagesBySession, streaming, showJump]);

  const activeSession = sessions.find((s) => s.id === activeId);
  const activeMessages = messagesBySession[activeId] ?? [];

  const filteredSessions = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.preview.toLowerCase().includes(q),
    );
  }, [sessions, query]);

  // -------- 文件附件 --------
  async function onPickFiles(files: FileList | null) {
    if (!files) return;
    const next: PendingAttachment[] = [];
    for (const f of Array.from(files).slice(0, 4)) {
      if (f.size > 4 * 1024 * 1024) continue; // 4MB 简单上限
      const dataUrl = await readFileAsDataUrl(f);
      next.push({
        id: `${f.name}-${f.size}-${Date.now()}`,
        name: f.name,
        size: f.size,
        mime: f.type,
        dataUrl,
      });
    }
    setAttachments((prev) => [...prev, ...next]);
  }

  // -------- 发送 --------
  function send() {
    const content = draft.trim();
    if (!content && attachments.length === 0) return;
    if (streaming) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content,
      author: "我",
      createdAt: new Date().toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      attachments: attachments.map((a) => ({
        id: a.id,
        type: a.mime.startsWith("image/")
          ? "image"
          : a.mime.startsWith("audio/")
            ? "audio"
            : a.mime.startsWith("video/")
              ? "video"
              : "file",
        url: a.dataUrl,
        name: a.name,
      })),
    };

    const assistantId = `a-${Date.now()}`;
    const placeholder: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      author: "AI Copilot",
      streaming: true,
      createdAt: new Date().toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };

    setMessagesBySession((prev) => ({
      ...prev,
      [activeId]: [...(prev[activeId] ?? []), userMsg, placeholder],
    }));
    setSessions((prev) =>
      prev.map((s) =>
        s.id === activeId
          ? {
              ...s,
              preview: content.slice(0, 40) || "(已发送附件)",
              updatedAt: "刚刚",
            }
          : s,
      ),
    );
    setDraft("");
    setAttachments([]);
    setStreaming(true);

    // 模拟生成式回答 —— 真实场景替换为 streamSSE
    const reply =
      "好的,我整理一下要点:\n\n1. 根据你刚才说的,我建议**先把最高优的事情收尾**。\n2. 同时我会结合你档案里的 `Tidewave` 经历来组织话术。\n3. 完成后给你一份可执行的 24 小时行动清单。\n\n需要我现在就动手吗?";
    abortRef.current = new AbortController();
    streamMockReply(
      reply,
      (delta) => {
        setMessagesBySession((prev) => {
          const list = prev[activeId] ?? [];
          return {
            ...prev,
            [activeId]: list.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + delta }
                : m,
            ),
          };
        });
      },
      () => {
        setMessagesBySession((prev) => {
          const list = prev[activeId] ?? [];
          return {
            ...prev,
            [activeId]: list.map((m) =>
              m.id === assistantId ? { ...m, streaming: false } : m,
            ),
          };
        });
        setStreaming(false);
      },
      abortRef.current.signal,
    );
  }

  function stopStreaming() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  function newSession() {
    const id = `s-${Date.now()}`;
    const next: Session = {
      id,
      title: "新对话",
      preview: "向 Copilot 提一个具体问题…",
      updatedAt: "刚刚",
    };
    setSessions((prev) => [next, ...prev]);
    setMessagesBySession((prev) => ({ ...prev, [id]: [] }));
    setActiveId(id);
  }

  function deleteSession(id: string) {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (id === activeId) {
      const remaining = sessions.filter((s) => s.id !== id);
      setActiveId(remaining[0]?.id ?? "");
    }
    setMessagesBySession((prev) => {
      const cp = { ...prev };
      delete cp[id];
      return cp;
    });
  }

  function renameSession(id: string) {
    const next = window.prompt(
      "重命名会话",
      sessions.find((s) => s.id === id)?.title,
    );
    if (!next) return;
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title: next } : s)),
    );
  }

  // -------- 渲染 --------
  return (
    <div className="flex h-[calc(100vh-4rem)] bg-background">
      {/* 左:会话列表 */}
      <aside className="hidden w-72 shrink-0 border-r bg-muted/20 lg:flex lg:flex-col">
        <div className="flex items-center justify-between px-4 py-3">
          <h2 className="text-sm font-semibold">对话</h2>
          <Button size="icon-sm" variant="ghost" onClick={newSession}>
            <Plus className="size-4" />
            <span className="sr-only">新建对话</span>
          </Button>
        </div>
        <div className="px-3 pb-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索对话"
              className="h-8 w-full rounded-md border bg-background pl-7 pr-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
            />
          </div>
        </div>
        <Separator />
        <ScrollArea className="flex-1">
          <ul className="space-y-0.5 p-2">
            {filteredSessions.map((s) => {
              const active = s.id === activeId;
              return (
                <li key={s.id} className="group relative">
                  <button
                    onClick={() => setActiveId(s.id)}
                    className={cn(
                      "flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                      active
                        ? "bg-primary/10 text-foreground"
                        : "hover:bg-muted",
                    )}
                  >
                    <div className="flex w-full items-center gap-1.5">
                      {s.pinned ? (
                        <Sparkles className="size-3 text-amber-500" />
                      ) : (
                        <MessageDot />
                      )}
                      <span className="truncate font-medium">{s.title}</span>
                      {s.unread ? (
                        <span className="ml-auto inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground">
                          {s.unread}
                        </span>
                      ) : null}
                    </div>
                    <span className="line-clamp-1 text-xs text-muted-foreground">
                      {s.preview}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {s.updatedAt}
                    </span>
                  </button>
                  <div className="absolute right-1 top-1 hidden gap-0.5 group-hover:flex">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        renameSession(s.id);
                      }}
                      className="rounded p-1 text-muted-foreground hover:bg-background"
                      aria-label="重命名"
                    >
                      <Pencil className="size-3" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteSession(s.id);
                      }}
                      className="rounded p-1 text-muted-foreground hover:bg-background"
                      aria-label="删除"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </div>
                </li>
              );
            })}
            {filteredSessions.length === 0 && (
              <li className="px-3 py-6 text-center text-xs text-muted-foreground">
                没找到匹配的对话
              </li>
            )}
          </ul>
        </ScrollArea>
        <div className="border-t p-3 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-2">
            <Avatar className="size-6">
              <AvatarFallback>我</AvatarFallback>
            </Avatar>
            <div>
              <p className="font-medium text-foreground">已登录</p>
              <p>档案完整度 86%</p>
            </div>
          </div>
        </div>
      </aside>

      {/* 中:消息流 */}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b px-4">
          <div className="flex min-w-0 items-center gap-2">
            <UserAvatar name="AI Copilot" status="online" className="size-7" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">
                {activeSession?.title ?? "新对话"}
              </p>
              <p className="text-[11px] text-muted-foreground">
                {streaming
                  ? "AI 正在生成回答…"
                  : "AI Copilot · 基于你的档案 + 近期日记"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <Badge variant="secondary" className="hidden sm:inline-flex">
              <Sparkles className="mr-1 size-3" />
              上下文已加载
            </Badge>
            <Button size="icon-sm" variant="ghost" aria-label="朗读">
              <Volume2 className="size-4" />
            </Button>
          </div>
        </header>

        <div
          className="relative flex-1 overflow-y-auto"
          onScroll={(e) => {
            const el = e.currentTarget;
            const nearBottom =
              el.scrollHeight - el.scrollTop - el.clientHeight < 120;
            setShowJump(!nearBottom);
          }}
        >
          <div className="mx-auto w-full max-w-3xl px-4 py-6">
            {activeMessages.length === 0 ? (
              <EmptyChatState onPick={(text) => setDraft(text)} />
            ) : (
              <MessageList
                messages={activeMessages}
                onLike={() => {}}
                onDislike={() => {}}
                onRegenerate={() => {}}
              />
            )}
            <div ref={endRef} />
          </div>

          {showJump && (
            <Button
              size="icon"
              variant="secondary"
              className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full shadow-md"
              onClick={() => {
                setShowJump(false);
                endRef.current?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              <ArrowDown className="size-4" />
            </Button>
          )}
        </div>

        {/* 输入区 */}
        <div className="border-t bg-background/80 px-4 py-3 backdrop-blur">
          <div className="mx-auto w-full max-w-3xl">
            {attachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {attachments.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-center gap-2 rounded-md border bg-muted/40 px-2 py-1 text-xs"
                  >
                    <FileText className="size-3.5 text-muted-foreground" />
                    <span className="max-w-[160px] truncate">{a.name}</span>
                    <span className="text-muted-foreground">
                      {formatSize(a.size)}
                    </span>
                    <button
                      onClick={() =>
                        setAttachments((prev) =>
                          prev.filter((p) => p.id !== a.id),
                        )
                      }
                      aria-label="移除附件"
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {speech.listening && (
              <div className="mb-2 inline-flex items-center gap-2 rounded-md bg-rose-500/10 px-2 py-1 text-xs text-rose-600">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-rose-500 opacity-75" />
                  <span className="relative inline-flex size-2 rounded-full bg-rose-500" />
                </span>
                正在听写 · 松开结束
              </div>
            )}

            <div className="flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => onPickFiles(e.target.files)}
              />
              <Button
                size="icon"
                variant="ghost"
                onClick={() => fileInputRef.current?.click()}
                aria-label="附件"
              >
                <Paperclip className="size-4" />
              </Button>
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="问问 Copilot …(Shift + Enter 换行)"
                rows={1}
                className="min-h-8 flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm shadow-none focus-visible:ring-0"
              />
              {speech.supported && (
                <Button
                  size="icon"
                  variant={speech.listening ? "default" : "ghost"}
                  onClick={() =>
                    speech.listening ? speech.stop() : speech.start()
                  }
                  aria-label={speech.listening ? "停止听写" : "开始听写"}
                >
                  {speech.listening ? (
                    <MicOff className="size-4" />
                  ) : (
                    <Mic className="size-4" />
                  )}
                </Button>
              )}
              {streaming ? (
                <Button
                  size="icon"
                  variant="destructive"
                  onClick={stopStreaming}
                  aria-label="停止生成"
                >
                  <Square className="size-4" />
                </Button>
              ) : (
                <Button
                  size="icon"
                  onClick={send}
                  disabled={!draft.trim() && attachments.length === 0}
                  aria-label="发送"
                >
                  <Send className="size-4" />
                </Button>
              )}
            </div>
            <p className="mt-1.5 text-center text-[11px] text-muted-foreground">
              AI 回答可能不准确,请核实重要信息。快捷键 ⌘/Ctrl + K
              唤起更多。
            </p>
          </div>
        </div>
      </main>

      {/* 右:上下文 / 提示 */}
      <aside className="hidden w-80 shrink-0 border-l bg-muted/20 xl:flex xl:flex-col">
        <div className="border-b p-4">
          <Card>
            <CardHeader className="space-y-1">
              <CardTitle className="text-sm">当前上下文</CardTitle>
              <CardDescription>
                Copilot 已自动加载以下信息,你可以手动管理。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <ContextRow label="基础档案" value="已加载" tone="ok" />
              <ContextRow label="最近 5 份推荐岗位" value="已加载" tone="ok" />
              <ContextRow label="本周日记 / 情绪" value="已加载" tone="ok" />
              <ContextRow label="Tidewave 面试记录" value="已加载" tone="ok" />
              <ContextRow label="顾问 Lily 最近消息" value="未启用" tone="off" />
            </CardContent>
          </Card>
        </div>
        <ScrollArea className="flex-1 px-4 py-4">
          <h3 className="mb-2 text-xs font-semibold text-muted-foreground">
            推荐提示词
          </h3>
          <ul className="space-y-2">
            {SUGGESTIONS.map((s) => (
              <li key={s.title}>
                <button
                  onClick={() => setDraft(s.prompt)}
                  className="w-full rounded-lg border bg-card p-3 text-left text-xs transition-colors hover:bg-muted/60"
                >
                  <p className="font-medium text-foreground">{s.title}</p>
                  <p className="mt-0.5 line-clamp-2 text-muted-foreground">
                    {s.prompt}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </ScrollArea>
      </aside>
    </div>
  );
}

// --------------------------------------------------------------------
// 7. 小组件
// --------------------------------------------------------------------

function MessageDot() {
  return (
    <span className="inline-block size-1.5 rounded-full bg-muted-foreground/60" />
  );
}

function ContextRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "ok" | "off";
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px]",
          tone === "ok"
            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
            : "border-slate-500/20 bg-slate-500/10 text-slate-500",
        )}
      >
        {tone === "ok" ? <Check className="size-2.5" /> : <X className="size-2.5" />}
        {value}
      </span>
    </div>
  );
}

function EmptyChatState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-white shadow-sm">
        <Sparkles className="size-6" />
      </div>
      <h2 className="text-lg font-semibold">开始和 Copilot 聊聊</h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        问我任何关于求职、面试、议价或情绪管理的问题。我已经知道你的档案、
        最近 7 天的日记和情绪趋势。
      </p>
      <div className="mt-6 grid w-full max-w-xl gap-2 sm:grid-cols-2">
        {SUGGESTIONS.slice(0, 4).map((s) => (
          <button
            key={s.title}
            onClick={() => onPick(s.prompt)}
            className="rounded-lg border bg-card p-3 text-left text-xs transition-colors hover:bg-muted/60"
          >
            <p className="font-medium text-foreground">{s.title}</p>
            <p className="mt-0.5 line-clamp-2 text-muted-foreground">
              {s.prompt}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

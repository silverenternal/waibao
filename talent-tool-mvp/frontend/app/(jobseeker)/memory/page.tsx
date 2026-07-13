"use client";

/**
 * 求职者 — 我的记忆 (T2702)
 *
 * Backed by ``/api/memory/memories``.  Users can:
 *   - browse their agent-managed memories
 *   - filter by type (fact / preference / event / task / episodic / summary)
 *   - edit content / confidence / metadata
 *   - delete individual memories or batch-forget by filter (GDPR)
 *   - run a semantic query against the store
 *
 * The timeline view (MemoryTimeline) is used to display the
 * chronological story of the user's interactions.
 */

import * as React from "react";
import { useLocale } from "next-intl";
import {
  AlertTriangle,
  Brain,
  Calendar,
  Edit3,
  Filter,
  Loader2,
  RefreshCcw,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { MemoryTimeline } from "@/components/memory/MemoryTimeline";

interface Memory {
  id: string;
  user_id: string;
  tenant_id: string;
  content: string;
  summary: string | null;
  source_agent: string;
  type: "fact" | "preference" | "event" | "summary" | "task" | "episodic";
  confidence: number;
  decay_score: number;
  access_count: number;
  last_accessed: string | null;
  metadata: Record<string, unknown>;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

const TYPE_LABEL: Record<Memory["type"], { en: string; zh: string; color: string }> = {
  fact: { en: "Fact", zh: "事实", color: "bg-blue-100 text-blue-800" },
  preference: { en: "Preference", zh: "偏好", color: "bg-pink-100 text-pink-800" },
  event: { en: "Event", zh: "事件", color: "bg-green-100 text-green-800" },
  summary: { en: "Summary", zh: "摘要", color: "bg-purple-100 text-purple-800" },
  task: { en: "Task", zh: "任务", color: "bg-amber-100 text-amber-800" },
  episodic: { en: "Episodic", zh: "情景", color: "bg-slate-100 text-slate-800" },
};

function classNames(...arr: Array<string | false | undefined>): string {
  return arr.filter(Boolean).join(" ");
}

export default function MemoryPage() {
  const locale = useLocale() as "en" | "zh" | "ja";
  const isZh = locale === "zh";

  const [memories, setMemories] = React.useState<Memory[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [queryText, setQueryText] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState<"all" | Memory["type"]>("all");
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingContent, setEditingContent] = React.useState("");
  const [pending, setPending] = React.useState(false);

  const fetchAll = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = new URL("/api/memory/memories", window.location.origin);
      url.searchParams.set("limit", "100");
      if (typeFilter !== "all") url.searchParams.set("types", typeFilter);
      const res = await fetch(url.toString(), { credentials: "include" });
      if (!res.ok) {
        throw new Error(`fetch memories failed: ${res.status}`);
      }
      const data: Memory[] = await res.json();
      setMemories(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  React.useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const handleQuery = async () => {
    if (!queryText.trim()) {
      void fetchAll();
      return;
    }
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/memory/memories/query", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query_text: queryText,
          top_k: 20,
          types: typeFilter === "all" ? [] : [typeFilter],
        }),
      });
      if (!res.ok) throw new Error(`query failed: ${res.status}`);
      const data: Memory[] = await res.json();
      setMemories(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(isZh ? "确定删除该记忆?" : "Delete this memory?")) return;
    try {
      const res = await fetch(`/api/memory/memories/${id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) throw new Error(`delete failed: ${res.status}`);
      setMemories((arr) => arr.filter((m) => m.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleSaveEdit = async (id: string) => {
    setPending(true);
    try {
      const res = await fetch(`/api/memory/memories/${id}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editingContent }),
      });
      if (!res.ok) throw new Error(`update failed: ${res.status}`);
      setMemories((arr) =>
        arr.map((m) =>
          m.id === id
            ? { ...m, content: editingContent, updated_at: new Date().toISOString() }
            : m
        )
      );
      setEditingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const handleForgetAll = async () => {
    if (
      !confirm(
        isZh
          ? "将删除所有当前过滤的记忆,此操作不可撤销。继续吗?"
          : "This will forget all currently filtered memories. Continue?"
      )
    ) {
      return;
    }
    setPending(true);
    try {
      const res = await fetch("/api/memory/memories/forget", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: typeFilter === "all" ? undefined : typeFilter,
        }),
      });
      if (!res.ok) throw new Error(`forget failed: ${res.status}`);
      const data = await res.json();
      alert(
        isZh
          ? `已删除 ${data.deleted ?? 0} 条记忆`
          : `Forgot ${data.deleted ?? 0} memories`
      );
      void fetchAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="container mx-auto max-w-5xl space-y-6 py-8">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            {isZh ? "我的记忆" : "My Memory"}
          </CardTitle>
          <CardDescription>
            {isZh
              ? "T2702 — 统一记忆库 (Mem0)。所有 Agent 跨场景共享。"
              : "T2702 — Unified memory store (Mem0). Shared across all agents."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex-1 min-w-[200px]">
              <Input
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                placeholder={isZh ? "语义查询 (例如:薪资期望)" : "Semantic query (e.g. salary expectations)"}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleQuery();
                }}
              />
            </div>
            <Select
              value={typeFilter}
              onValueChange={(v) => setTypeFilter(v as typeof typeFilter)}
            >
              <SelectTrigger className="w-[160px]">
                <Filter className="mr-2 h-4 w-4" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{isZh ? "全部类型" : "All types"}</SelectItem>
                <SelectItem value="fact">{TYPE_LABEL.fact.en}</SelectItem>
                <SelectItem value="preference">{TYPE_LABEL.preference.en}</SelectItem>
                <SelectItem value="event">{TYPE_LABEL.event.en}</SelectItem>
                <SelectItem value="summary">{TYPE_LABEL.summary.en}</SelectItem>
                <SelectItem value="task">{TYPE_LABEL.task.en}</SelectItem>
                <SelectItem value="episodic">{TYPE_LABEL.episodic.en}</SelectItem>
              </SelectContent>
            </Select>
            <Button onClick={handleQuery} disabled={pending}>
              {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              <span className="ml-2">{isZh ? "查询" : "Search"}</span>
            </Button>
            <Button variant="outline" onClick={() => void fetchAll()}>
              <RefreshCcw className="h-4 w-4" />
            </Button>
            <Button variant="destructive" onClick={handleForgetAll} disabled={pending}>
              <Trash2 className="h-4 w-4" />
              <span className="ml-2">{isZh ? "批量遗忘" : "Forget"}</span>
            </Button>
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              <AlertTriangle className="h-4 w-4" />
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-10 text-slate-500">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              {isZh ? "加载中..." : "Loading..."}
            </div>
          ) : memories.length === 0 ? (
            <div className="py-10 text-center text-slate-500">
              {isZh ? "暂无记忆。Agent 在对话中会自动写入。" : "No memories yet. Agents will populate them as you chat."}
            </div>
          ) : (
            <MemoryTimeline
              memories={memories}
              editingId={editingId}
              editingContent={editingContent}
              pending={pending}
              onStartEdit={(m) => {
                setEditingId(m.id);
                setEditingContent(m.content);
              }}
              onCancelEdit={() => setEditingId(null)}
              onChangeEditContent={setEditingContent}
              onSaveEdit={handleSaveEdit}
              onDelete={handleDelete}
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            {isZh ? "如何运作" : "How it works"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-600">
          <p>
            {isZh
              ? "每个 Agent 在每次 run() 时会自动把与你相关的记忆注入到 system prompt,形成跨 agent 上下文共享。"
              : "Every agent run() automatically injects relevant memories into the system prompt, creating cross-agent context sharing."}
          </p>
          <p>
            {isZh
              ? "记忆会随时间 decay;被反复访问的记忆 decay_score 会被拉回 1.0。"
              : "Memories decay over time; frequently accessed ones are pulled back toward 1.0."}
          </p>
          <p>
            {isZh
              ? "Mem0 vendor-in:把对话转成 fact / preference / event / task 四类结构化记忆,并维护 entity graph。"
              : "Mem0 vendor-in: extracts fact / preference / event / task from chats, plus an entity graph."}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

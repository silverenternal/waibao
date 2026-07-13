"use client";

/**
 * T2702 — MemoryTimeline
 *
 * Chronological list of memory items with inline edit / delete actions.
 * Used by the /memory page on the jobseeker persona.
 */

import * as React from "react";
import {
  Brain,
  Calendar,
  Edit3,
  Loader2,
  Save,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

export interface Memory {
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

interface MemoryTimelineProps {
  memories: Memory[];
  editingId: string | null;
  editingContent: string;
  pending: boolean;
  onStartEdit: (m: Memory) => void;
  onCancelEdit: () => void;
  onChangeEditContent: (v: string) => void;
  onSaveEdit: (id: string) => void;
  onDelete: (id: string) => void;
  className?: string;
}

const TYPE_BADGE: Record<Memory["type"], string> = {
  fact: "bg-blue-100 text-blue-800",
  preference: "bg-pink-100 text-pink-800",
  event: "bg-green-100 text-green-800",
  summary: "bg-purple-100 text-purple-800",
  task: "bg-amber-100 text-amber-800",
  episodic: "bg-slate-100 text-slate-800",
};

const TYPE_ICON: Record<Memory["type"], React.ReactNode> = {
  fact: <Brain className="h-3 w-3" />,
  preference: <Sparkles className="h-3 w-3" />,
  event: <Calendar className="h-3 w-3" />,
  summary: <Brain className="h-3 w-3" />,
  task: <Edit3 className="h-3 w-3" />,
  episodic: <Calendar className="h-3 w-3" />,
};

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function decayColor(score: number): string {
  if (score >= 0.7) return "text-green-700";
  if (score >= 0.4) return "text-amber-700";
  return "text-red-700";
}

export function MemoryTimeline({
  memories,
  editingId,
  editingContent,
  pending,
  onStartEdit,
  onCancelEdit,
  onChangeEditContent,
  onSaveEdit,
  onDelete,
  className,
}: MemoryTimelineProps) {
  return (
    <ol
      className={cn(
        "relative ml-2 border-l border-slate-200 pl-6",
        className
      )}
    >
      {memories.map((m) => (
        <li key={m.id} className="mb-6 last:mb-0">
          <span className="absolute -left-2 mt-2 h-3 w-3 rounded-full border-2 border-white bg-slate-400 shadow" />
          <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge className={cn("gap-1", TYPE_BADGE[m.type])}>
                {TYPE_ICON[m.type]}
                <span>{m.type}</span>
              </Badge>
              <Badge variant="outline" className="text-xs">
                agent: {m.source_agent}
              </Badge>
              <span
                className={cn(
                  "text-xs font-medium",
                  decayColor(m.decay_score)
                )}
                title="decay_score: memories fade over time when not accessed"
              >
                decay {m.decay_score.toFixed(2)}
              </span>
              <span className="text-xs text-slate-500">
                conf {m.confidence.toFixed(2)}
              </span>
              {m.is_archived && (
                <Badge variant="secondary" className="text-xs">
                  archived
                </Badge>
              )}
              <span className="ml-auto text-xs text-slate-400">
                {formatTime(m.created_at)}
              </span>
            </div>

            {editingId === m.id ? (
              <div className="space-y-2">
                <Textarea
                  value={editingContent}
                  onChange={(e) => onChangeEditContent(e.target.value)}
                  rows={3}
                  className="text-sm"
                />
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => onSaveEdit(m.id)}
                    disabled={pending}
                  >
                    {pending ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Save className="h-3 w-3" />
                    )}
                    <span className="ml-1">Save</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={onCancelEdit}
                  >
                    <X className="h-3 w-3" />
                    <span className="ml-1">Cancel</span>
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-sm text-slate-800">{m.content}</p>
                {m.summary && (
                  <p className="mt-1 text-xs italic text-slate-500">
                    {m.summary}
                  </p>
                )}
                <div className="mt-3 flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onStartEdit(m)}
                  >
                    <Edit3 className="h-3 w-3" />
                    <span className="ml-1">Edit</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-600 hover:bg-red-50"
                    onClick={() => onDelete(m.id)}
                  >
                    <Trash2 className="h-3 w-3" />
                    <span className="ml-1">Delete</span>
                  </Button>
                  <span className="ml-auto text-xs text-slate-400">
                    accessed {m.access_count}x
                    {m.last_accessed ? ` · last ${formatTime(m.last_accessed)}` : ""}
                  </span>
                </div>
              </>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

export default MemoryTimeline;

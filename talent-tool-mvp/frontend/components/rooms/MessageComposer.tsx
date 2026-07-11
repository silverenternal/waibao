"use client";

/**
 * MessageComposer — T608
 *
 * 输入框 + @ 自动补全.
 *
 * Props:
 *   - onSend(content): 用户按下发送; content 已自动 trim, 已经替换 @mention.
 *   - onTyping(isTyping): 给上层 useRoom 通知 typing 状态.
 *   - onAttach(): 调用 v2.0 的 /api/uploads 拿到 URL 后插入 attachments.
 *
 * 行为:
 *   - Enter 发送, Shift+Enter 换行.
 *   - @ 触发 MentionAutocomplete; ↑↓ Enter 选中, Esc 取消.
 *   - 显示未发送的字符数 (校验 20k 上限).
 */

import * as React from "react";
import { Paperclip, Send, X, FileText, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  MentionAutocomplete,
  detectMentionTrigger,
  insertMentionAtCursor,
  type MentionTriggerState,
} from "@/components/rooms/MentionAutocomplete";
import type { MentionOffset, RoomAttachment, RoomMember } from "@/lib/api-rooms";

const MAX_LEN = 20_000;

interface MessageComposerProps {
  members: RoomMember[];
  onSend: (content: string, attachments: RoomAttachment[]) => Promise<void> | void;
  onTyping?: (isTyping: boolean) => void;
  onAttach?: () => Promise<RoomAttachment | null>;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  parentId?: string;
}

export function MessageComposer({
  members,
  onSend,
  onTyping,
  onAttach,
  placeholder,
  disabled,
  className,
  parentId,
}: MessageComposerProps) {
  const [content, setContent] = React.useState("");
  const [attachments, setAttachments] = React.useState<RoomAttachment[]>([]);
  const [trigger, setTrigger] = React.useState<MentionTriggerState>({
    active: false, query: "", start: -1, end: -1,
  });
  const [activeMentionId, setActiveMentionId] = React.useState<string | null>(null);
  const [activeIdx, setActiveIdx] = React.useState(0);
  const [sending, setSending] = React.useState(false);
  const [attaching, setAttaching] = React.useState(false);
  const taRef = React.useRef<HTMLTextAreaElement>(null);

  const filteredMembers = React.useMemo(() => {
    const q = trigger.query.trim().toLowerCase();
    let xs = members;
    if (q) xs = xs.filter((m) => m.user_id.toLowerCase().includes(q));
    return xs.slice(0, 8);
  }, [members, trigger.query]);

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value;
    const cursor = e.target.selectionStart ?? value.length;
    setContent(value);
    const t = detectMentionTrigger(value, cursor);
    setTrigger(t);
    if (t.active) {
      onTyping?.(true);
    }
    if (!t.active) {
      // 检测不到 trigger 时也要通知上层 (typing 状态)
      onTyping?.(true);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (trigger.active && filteredMembers.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => (i + 1) % filteredMembers.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => (i - 1 + filteredMembers.length) % filteredMembers.length);
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const chosen = filteredMembers[activeIdx];
        if (chosen) applyMention(chosen.user_id);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setTrigger({ active: false, query: "", start: -1, end: -1 });
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  }

  function applyMention(userId: string) {
    const ta = taRef.current;
    if (!ta) return;
    const cursor = ta.selectionStart ?? content.length;
    const { newContent, newCursor } = insertMentionAtCursor(content, cursor, userId);
    setContent(newContent);
    setTrigger({ active: false, query: "", start: -1, end: -1 });
    setActiveMentionId(userId);
    setActiveIdx(0);
    requestAnimationFrame(() => {
      ta.focus();
      ta.setSelectionRange(newCursor, newCursor);
    });
  }

  async function submit() {
    if (sending || !content.trim()) return;
    setSending(true);
    try {
      await onSend(content.trim(), attachments);
      setContent("");
      setAttachments([]);
      setActiveMentionId(null);
      onTyping?.(false);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("[composer] send failed", err);
    } finally {
      setSending(false);
    }
  }

  async function handleAttach() {
    if (!onAttach) return;
    setAttaching(true);
    try {
      const att = await onAttach();
      if (att) {
        setAttachments((xs) => [...xs, att]);
      }
    } finally {
      setAttaching(false);
    }
  }

  function removeAttachment(idx: number) {
    setAttachments((xs) => xs.filter((_, i) => i !== idx));
  }

  const leftover = MAX_LEN - content.length;
  const tooLong = leftover < 0;

  return (
    <div className={cn("flex flex-col gap-2 border-t bg-background px-3 py-3", className)}>
      {attachments.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {attachments.map((a, i) => (
            <li
              key={i}
              className="flex items-center gap-1.5 rounded-full bg-muted pl-2 pr-1 py-1 text-xs"
            >
              <FileText className="h-3 w-3" />
              <span className="max-w-[180px] truncate">{a.name}</span>
              <button
                type="button"
                onClick={() => removeAttachment(i)}
                className="ml-1 rounded-full p-0.5 hover:bg-background/60"
                aria-label="删除附件"
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="relative">
        <Textarea
          ref={taRef}
          rows={parentId ? 2 : 3}
          value={content}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || (parentId ? "回复线程..." : "说点什么... 使用 @ 提及同事")}
          disabled={disabled || sending}
          className="resize-none pr-24 min-h-[60px]"
          data-testid="room-composer"
        />
        <MentionAutocomplete
          open={trigger.active}
          members={filteredMembers}
          query={trigger.query}
          activeId={activeMentionId || (filteredMembers[activeIdx]?.user_id ?? null)}
          onActiveChange={(id) => setActiveMentionId(id)}
          onSelect={(uid) => applyMention(uid)}
          className="left-2 bottom-full mb-1"
        />

        <div className="absolute bottom-2 right-2 flex items-center gap-1">
          {onAttach && (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={handleAttach}
              disabled={attaching || disabled}
              aria-label="附件 (调 v2.0 /api/uploads)"
            >
              {attaching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
            </Button>
          )}
          <Button
            type="button"
            size="icon"
            onClick={submit}
            disabled={disabled || sending || !content.trim() || tooLong}
            aria-label="发送"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>Enter 发送 · Shift+Enter 换行 · @ 提及</span>
        <span className={cn(tooLong && "text-rose-500")}>
          {content.length} / {MAX_LEN}
        </span>
      </div>
    </div>
  );
}

/** 把 messages composer 内容里已经包含的 @UUID 全量替换为 mention_offsets 后端入参. */
export function buildMentionOffsets(content: string): MentionOffset[] {
  const re = /@([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/g;
  const out: MentionOffset[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(content)) !== null) {
    out.push({ user_id: m[1], start: m.index, end: m.index + m[0].length });
  }
  // 去重 (多次提到同一个 user)
  const seen = new Set<string>();
  return out.filter((o) => {
    const k = `${o.user_id}:${o.start}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

/**
 * Rooms API client (T608).
 *
 * Wraps the FastAPI collaboration-room endpoints exposed by
 * `backend/api/rooms.py`:
 *   GET    /api/rooms                              → 我参与的房间列表
 *   POST   /api/rooms                              → 创建
 *   GET    /api/rooms/{id}                         → 详情 (含 members + unread + pins)
 *   PATCH  /api/rooms/{id}                         → 修改/归档
 *   POST   /api/rooms/{id}/members                 → 邀请
 *   DELETE /api/rooms/{id}/members/{user_id}       → 主动离开 / 踢人
 *   GET    /api/rooms/{id}/messages?cursor=&limit= → 主对话流
 *   POST   /api/rooms/{id}/messages                → 发消息
 *   PATCH  /api/rooms/{id}/messages/{msg_id}       → 编辑
 *   DELETE /api/rooms/{id}/messages/{msg_id}       → 删除
 *   POST   /api/rooms/{id}/messages/{msg_id}/reactions → 切换 emoji
 *   POST   /api/rooms/{id}/read                    → 标记已读
 *
 * 辅助:
 *   POST   /api/rooms/{id}/pin, /unpin
 *   GET    /api/rooms/{id}/threads/{parent_id}
 *   GET    /api/rooms/{id}/search?q=...
 *   GET    /api/rooms/me/mentions
 *
 * Shapes below mirror the dataclasses in `services/collaboration_room.py`.
 */

import { createClient } from "@/lib/supabase";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Constants — keep in lock-step with collaboration_room.py
// ---------------------------------------------------------------------------

export const ROOM_TYPES = ["direct", "group", "topic", "project"] as const;
export type RoomType = (typeof ROOM_TYPES)[number];

export const ROOM_MEMBER_ROLES = ["owner", "admin", "member", "guest"] as const;
export type RoomMemberRole = (typeof ROOM_MEMBER_ROLES)[number];

export const MESSAGE_TYPES = ["text", "markdown", "file", "system"] as const;
export type MessageType = (typeof MESSAGE_TYPES)[number];

export const ROOM_TYPE_LABEL: Record<RoomType, string> = {
  direct: "私聊",
  group: "群聊",
  topic: "话题",
  project: "项目",
};

export const ROLE_LABEL: Record<RoomMemberRole, string> = {
  owner: "创建者",
  admin: "管理员",
  member: "成员",
  guest: "访客",
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RoomMember {
  room_id: string;
  user_id: string;
  role: RoomMemberRole;
  joined_at: string;
  left_at: string | null;
  last_read_at: string | null;
  muted: boolean;
  invitation_pending?: boolean;
}

export interface Room {
  id: string;
  organisation_id: string | null;
  name: string;
  type: RoomType;
  created_by: string | null;
  created_at: string;
  last_message_at: string | null;
  archived: boolean;
  metadata: Record<string, unknown>;
  member_count: number;
}

export interface RoomWithExtras extends Room {
  members: RoomMember[];
  pins: { message: RoomMessage; pinned_by: string | null; pinned_at: string }[];
  unread_count: number;
  last_read_at?: string | null;
}

export interface MentionOffset {
  user_id: string;
  start: number;
  end: number;
}

export interface RoomAttachment {
  url: string;
  name: string;
  mime?: string;
  size?: number;
}

export interface RoomMessage {
  id: string;
  room_id: string;
  sender_id: string;
  content: string;
  message_type: MessageType;
  parent_id: string | null;
  mentions: string[];
  mention_offsets: MentionOffset[];
  attachments: RoomAttachment[];
  edited_at: string | null;
  deleted_at: string | null;
  created_at: string;
  thread_root_id: string | null;
}

export interface RoomMessageWithReactions extends RoomMessage {
  reactions?: RoomReaction[];
  thread_count?: number;
  thread_last_reply_at?: string | null;
}

export interface RoomReaction {
  message_id: string;
  user_id: string;
  emoji: string;
  created_at: string;
}

export interface MessageListResponse {
  messages: RoomMessage[];
  next_cursor: string | null;
}

export interface RoomListResponse {
  rooms: (Room & {
    last_read_at: string | null;
    unread_count: number;
  })[];
  total_unread: number;
}

export interface MentionRow {
  id: string;
  user_id: string;
  room_id: string;
  message_id: string;
  read_at: string | null;
  created_at: string;
  room_messages?: {
    sender_id?: string;
    content?: string;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface ApiError extends Error {
  status: number;
  body?: unknown;
}

async function getAuthToken(): Promise<string | null> {
  try {
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    return session?.access_token ?? null;
  } catch {
    return null;
  }
}

async function call<T>(
  path: string,
  init: RequestInit & { json?: unknown; raw?: boolean } = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const token = await getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, {
    ...init,
    headers,
    body,
  });
  if (!res.ok) {
    let parsed: unknown;
    try { parsed = await res.json(); } catch { parsed = await res.text().catch(() => null); }
    const err: ApiError = Object.assign(new Error(`API error: ${res.status}`), {
      status: res.status,
      body: parsed,
    });
    throw err;
  }
  if (init.raw) return undefined as unknown as T;
  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Rooms CRUD
// ---------------------------------------------------------------------------

export const roomsApi = {
  listRooms(opts: { archived?: boolean } = {}): Promise<RoomListResponse> {
    const q = opts.archived ? "?archived=true" : "";
    return call(`/api/rooms${q}`);
  },

  createRoom(body: {
    name: string;
    type?: RoomType;
    organisation_id?: string | null;
    members?: string[];
    metadata?: Record<string, unknown>;
  }): Promise<RoomWithExtras> {
    return call(`/api/rooms`, { method: "POST", json: body });
  },

  getRoom(id: string): Promise<RoomWithExtras> {
    return call(`/api/rooms/${encodeURIComponent(id)}`);
  },

  patchRoom(
    id: string,
    body: { name?: string; metadata?: Record<string, unknown>; archived?: boolean }
  ): Promise<Room> {
    return call(`/api/rooms/${encodeURIComponent(id)}`, { method: "PATCH", json: body });
  },

  archiveRoom(id: string): Promise<Room> {
    return this.patchRoom(id, { archived: true });
  },

  // ---- Members ----

  inviteMember(roomId: string, userId: string, role: RoomMemberRole = "member"): Promise<RoomMember> {
    return call(`/api/rooms/${encodeURIComponent(roomId)}/members`, {
      method: "POST",
      json: { user_id: userId, role },
    });
  },

  removeMember(roomId: string, userId: string): Promise<void> {
    return call(`/api/rooms/${encodeURIComponent(roomId)}/members/${encodeURIComponent(userId)}`, {
      method: "DELETE",
      raw: true,
    });
  },

  leaveRoom(roomId: string): Promise<void> {
    // Same endpoint, target = self handled by backend
    return call(`/api/rooms/${encodeURIComponent(roomId)}/members/me`, {
      method: "DELETE",
      raw: true,
    });
  },

  // ---- Messages ----

  listMessages(
    roomId: string,
    opts: { cursor?: string; limit?: number; thread_root_id?: string; include_thread?: boolean } = {}
  ): Promise<MessageListResponse> {
    const params = new URLSearchParams();
    if (opts.cursor) params.set("cursor", opts.cursor);
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.thread_root_id) params.set("thread_root_id", opts.thread_root_id);
    if (opts.include_thread) params.set("include_thread", "true");
    const q = params.toString();
    return call(`/api/rooms/${encodeURIComponent(roomId)}/messages${q ? "?" + q : ""}`);
  },

  postMessage(
    roomId: string,
    body: {
      content: string;
      message_type?: MessageType;
      parent_id?: string;
      mentions?: string[];
      mention_offsets?: MentionOffset[];
      attachments?: RoomAttachment[];
    }
  ): Promise<RoomMessage> {
    return call(`/api/rooms/${encodeURIComponent(roomId)}/messages`, { method: "POST", json: body });
  },

  editMessage(roomId: string, messageId: string, content: string): Promise<RoomMessage> {
    return call(
      `/api/rooms/${encodeURIComponent(roomId)}/messages/${encodeURIComponent(messageId)}`,
      { method: "PATCH", json: { content } }
    );
  },

  deleteMessage(roomId: string, messageId: string): Promise<void> {
    return call(
      `/api/rooms/${encodeURIComponent(roomId)}/messages/${encodeURIComponent(messageId)}`,
      { method: "DELETE", raw: true }
    );
  },

  // ---- Reactions ----

  toggleReaction(
    roomId: string,
    messageId: string,
    emoji: string
  ): Promise<{ active: boolean; emoji: string; message_id: string; user_id: string }> {
    return call(
      `/api/rooms/${encodeURIComponent(roomId)}/messages/${encodeURIComponent(messageId)}/reactions`,
      { method: "POST", json: { emoji } }
    );
  },

  // ---- Read state ----

  markRead(roomId: string, at?: string): Promise<void> {
    return call(`/api/rooms/${encodeURIComponent(roomId)}/read`, {
      method: "POST",
      json: at ? { at } : {},
      raw: true,
    });
  },

  // ---- Pins / Threads / Search / Mentions ----

  pinMessage(roomId: string, messageId: string): Promise<{ pinned: boolean }> {
    return call(`/api/rooms/${encodeURIComponent(roomId)}/pin`, {
      method: "POST",
      json: { message_id: messageId },
    });
  },

  unpinMessage(roomId: string, messageId: string): Promise<{ pinned: boolean }> {
    return call(`/api/rooms/${encodeURIComponent(roomId)}/unpin`, {
      method: "POST",
      json: { message_id: messageId },
    });
  },

  listThreadReplies(roomId: string, parentId: string): Promise<{ messages: RoomMessage[] }> {
    return call(
      `/api/rooms/${encodeURIComponent(roomId)}/threads/${encodeURIComponent(parentId)}`
    );
  },

  searchMessages(roomId: string, q: string, limit = 50): Promise<{ messages: RoomMessage[] }> {
    return call(
      `/api/rooms/${encodeURIComponent(roomId)}/search?q=${encodeURIComponent(q)}&limit=${limit}`
    );
  },

  listMyMentions(opts: { unread_only?: boolean; limit?: number } = {}): Promise<{ mentions: MentionRow[] }> {
    const params = new URLSearchParams();
    if (opts.unread_only !== false) params.set("unread_only", "true");
    if (opts.limit) params.set("limit", String(opts.limit));
    const q = params.toString();
    return call(`/api/rooms/me/mentions${q ? "?" + q : ""}`);
  },

  markMentionRead(mentionId: string): Promise<void> {
    return call(`/api/rooms/me/mentions/${encodeURIComponent(mentionId)}/read`, {
      method: "POST",
      raw: true,
    });
  },
};

export type RoomsClient = typeof roomsApi;
export { roomsApi as default };

// ---------------------------------------------------------------------------
// Mention parsing helper (client-side highlight rendering)
// ---------------------------------------------------------------------------
const MENTION_RE = /@([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/g;

export interface ParsedSegment {
  type: "text" | "mention";
  text: string;
  user_id?: string;
  start: number;
  end: number;
}

/** 把消息文本切成纯文本片段 + mention 片段. 后端 offset 为权威, 但也可正则解析. */
export function parseMentions(content: string): ParsedSegment[] {
  const out: ParsedSegment[] = [];
  let cursor = 0;
  let m: RegExpExecArray | null;
  // 用 /g 形式
  while ((m = MENTION_RE.exec(content)) !== null) {
    if (m.index > cursor) {
      out.push({ type: "text", text: content.slice(cursor, m.index), start: cursor, end: m.index });
    }
    out.push({
      type: "mention",
      text: m[0],
      user_id: m[1],
      start: m.index,
      end: m.index + m[0].length,
    });
    cursor = m.index + m[0].length;
  }
  if (cursor < content.length) {
    out.push({ type: "text", text: content.slice(cursor), start: cursor, end: content.length });
  }
  return out;
}

/** 把 mention offset 段合并到 splits, 优先使用后端返回的 offsets. */
export function applyMentionOffsets(
  content: string,
  offsets: MentionOffset[]
): ParsedSegment[] {
  if (!offsets || offsets.length === 0) return [{ type: "text", text: content, start: 0, end: content.length }];
  const sorted = [...offsets].sort((a, b) => a.start - b.start);
  const out: ParsedSegment[] = [];
  let cursor = 0;
  for (const off of sorted) {
    if (off.start < cursor) continue;  // 重叠忽略
    if (off.start > cursor) {
      out.push({ type: "text", text: content.slice(cursor, off.start), start: cursor, end: off.start });
    }
    out.push({
      type: "mention",
      text: content.slice(off.start, off.end),
      user_id: off.user_id,
      start: off.start,
      end: off.end,
    });
    cursor = off.end;
  }
  if (cursor < content.length) {
    out.push({ type: "text", text: content.slice(cursor), start: cursor, end: content.length });
  }
  return out;
}

/**
 * T1203 — feature API clients.
 *
 * Each module re-uses the v3.0 backend endpoints; we only translate paths,
 * names and shapes for the mini-program UI.
 */
import { request } from './request';

// -----------------------------------------------------------------------------
// Copilot / chat
// -----------------------------------------------------------------------------

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  updated_at: string;
  turns: ChatTurn[];
}

export async function listSessions() {
  return request<ChatSession[]>('/api/copilot/sessions');
}

export async function createSession(title?: string) {
  return request<ChatSession>('/api/copilot/sessions', {
    method: 'POST',
    body: { title: title || '新对话' },
  });
}

export async function sendMessage(sessionId: string, content: string) {
  return request<{ turn: ChatTurn; session: ChatSession }>(
    `/api/copilot/sessions/${sessionId}/messages`,
    { method: 'POST', body: { content } }
  );
}

// -----------------------------------------------------------------------------
// Profile (画像)
// -----------------------------------------------------------------------------

export interface TalentProfile {
  id: string;
  user_id: string;
  headline: string;
  bio: string;
  skills: string[];
  experience_years: number;
  preferences: Record<string, unknown>;
  updated_at: string;
}

export async function fetchProfile() {
  return request<TalentProfile>('/api/profile/me');
}

export async function updateProfile(patch: Partial<TalentProfile>) {
  return request<TalentProfile>('/api/profile/me', { method: 'PATCH', body: patch });
}

// -----------------------------------------------------------------------------
// Journal (工作日记 + 语音)
// -----------------------------------------------------------------------------

export interface JournalEntry {
  id: string;
  content: string;
  audio_url?: string;
  emotion?: string;
  sentiment_score?: number;
  created_at: string;
}

export async function listJournal(query?: { limit?: number; cursor?: string }) {
  return request<{ items: JournalEntry[]; next_cursor?: string }>('/api/journal', { query });
}

export async function createJournal(body: { content: string; audio_url?: string }) {
  return request<JournalEntry>('/api/journal', { method: 'POST', body });
}

export async function uploadJournalAudio(filePath: string) {
  return new Promise<{ url: string }>((resolve, reject) => {
    uni.uploadFile({
      url: '/api/journal/audio',
      filePath,
      name: 'audio',
      success: (res) => {
        try {
          resolve(JSON.parse(res.data));
        } catch {
          reject(new Error('invalid upload response'));
        }
      },
      fail: reject,
    });
  });
}

// -----------------------------------------------------------------------------
// Career plan
// -----------------------------------------------------------------------------

export interface CareerPlan {
  id: string;
  title: string;
  horizon_months: number;
  milestones: Array<{
    id: string;
    title: string;
    target_date: string;
    status: 'pending' | 'in_progress' | 'done';
  }>;
  updated_at: string;
}

export async function fetchPlan() {
  return request<CareerPlan>('/api/career-plan/me');
}

// -----------------------------------------------------------------------------
// Tickets (工单)
// -----------------------------------------------------------------------------

export interface Ticket {
  id: string;
  title: string;
  description: string;
  status: 'open' | 'in_progress' | 'blocked' | 'closed';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  assignee?: string;
  created_at: string;
  updated_at: string;
}

export async function listMyTickets(query?: { status?: Ticket['status'] }) {
  return request<Ticket[]>('/api/tickets/me', { query });
}

export async function listEmployerTickets(query?: { status?: Ticket['status'] }) {
  return request<Ticket[]>('/api/tickets', { query });
}

export async function advanceTicket(id: string, status: Ticket['status']) {
  return request<Ticket>(`/api/tickets/${id}/status`, {
    method: 'PATCH',
    body: { status },
  });
}

// -----------------------------------------------------------------------------
// Strategy map (战略地图)
// -----------------------------------------------------------------------------

export interface StrategyNode {
  id: string;
  title: string;
  perspective: 'financial' | 'customer' | 'process' | 'learning';
  progress: number;
  children: StrategyNode[];
}

export async function fetchStrategyMap() {
  return request<{ root: StrategyNode }>('/api/strategy/me');
}

// -----------------------------------------------------------------------------
// Collaboration rooms (协同房间)
// -----------------------------------------------------------------------------

export interface Room {
  id: string;
  title: string;
  participant_count: number;
  last_message_at: string;
  unread: number;
}

export async function listRooms() {
  return request<Room[]>('/api/multiparty/rooms');
}
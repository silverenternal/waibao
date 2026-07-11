/**
 * Voice API client (T701).
 *
 * Wraps the /api/voice endpoints:
 *   - POST /api/voice/transcribe         上传音频 + 转写
 *   - POST /api/voice/submit             转写结果 → 提交为日记 + 触发 agents
 *
 * Both go through Next.js fetch with the Supabase bearer token in localStorage
 * (matching the convention used by other api-*.ts clients).
 */

import { createClient } from "@/lib/supabase";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TranscribeResponse {
  success: boolean;
  text: string;
  provider: string;             // whisper | aliyun_stt | mock_stt
  language?: string;
  duration_sec?: number;
  fallback_used?: boolean;
  fallback_reason?: string;
  error?: string;
}

export interface VoiceSubmitResponse {
  success: boolean;
  journal: {
    rating?: string;
    advice?: string;
    warnings?: string[];
    action_items?: string[];
  };
  emotion: {
    valence?: number;
    arousal?: number;
    flags?: string[];
    summary?: string;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function authHeaders(): HeadersInit {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("sb_token") || "";
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function transcribeAudio(
  audio: Blob,
  opts: { language?: string; filename?: string } = {},
): Promise<TranscribeResponse> {
  const fd = new FormData();
  const ext = opts.filename || (audio.type.includes("mp4") ? "voice.m4a" : "voice.webm");
  fd.append("audio", audio, ext);
  if (opts.language) fd.append("language", opts.language);

  const r = await fetch("/api/voice/transcribe", {
    method: "POST",
    headers: authHeaders(),
    body: fd,
  });
  const data = await r.json();
  if (!r.ok) {
    return {
      success: false,
      text: "",
      provider: "none",
      error: data?.detail || data?.error || `HTTP ${r.status}`,
    };
  }
  return data;
}

export async function submitVoiceJournal(
  text: string,
  meta: { mood_score?: number; language?: string; provider?: string; duration_sec?: number } = {},
): Promise<VoiceSubmitResponse> {
  const r = await fetch("/api/voice/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ text, ...meta }),
  });
  const data = await r.json();
  if (!r.ok) {
    return { success: false, journal: {}, emotion: {} };
  }
  return data;
}

// Supabase client export for advanced callers
export { createClient };
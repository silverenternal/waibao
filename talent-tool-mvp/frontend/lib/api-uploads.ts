/**
 * Resume / file upload client.
 *
 * Wraps POST /api/uploads (multipart/form-data) and the signed-url helpers.
 * Mirrors the same auth/FormData conventions used in lib/api.ts so we can
 * share the Supabase session token from createClient().
 */
"use client";

import { createClient } from "@/lib/supabase";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type UploadStage =
  | "idle"
  | "uploading"
  | "ocr_pending"
  | "ocr_running"
  | "ocr_done"
  | "ocr_failed"
  | "done"
  | "error";

export interface UploadResponse {
  success: boolean;
  file_url: string;
  path: string;
  bucket: string;
  mime: string;
  size: number;
  filename: string;
  uploaded_by?: string;
}

export interface SignedUrlResponse {
  file_url: string;
  path: string;
  bucket: string;
  ttl: number;
}

export class UploadError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public body?: unknown,
  ) {
    super(`Upload failed (${status}): ${detail}`);
    this.name = "UploadError";
  }
}

async function getAuthToken(): Promise<string | null> {
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch {
    return null;
  }
}

async function authedFetch(
  path: string,
  init: RequestInit,
  signal?: AbortSignal,
): Promise<Response> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  return fetch(`${API_BASE}${path}`, { ...init, headers, signal });
}

/**
 * Upload a single file (resume / image / PDF) to /api/uploads.
 *
 * Tracks XHR progress when running in the browser so the caller can drive a
 * progress bar. Returns the parsed UploadResponse when the request completes.
 */
export function uploadFile(
  file: File,
  options?: {
    bucket?: string;
    folder?: string;
    signal?: AbortSignal;
    onProgress?: (pct: number) => void;
  },
): Promise<UploadResponse> {
  const { bucket, folder = "resumes", signal, onProgress } = options ?? {};
  const formData = new FormData();
  formData.append("file", file);
  formData.append("folder", folder);

  const query = bucket ? `?bucket=${encodeURIComponent(bucket)}` : "";

  return new Promise<UploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/uploads${query}`, true);

    if (signal) {
      const onAbort = () => xhr.abort();
      signal.addEventListener("abort", onAbort, { once: true });
    }

    getAuthToken()
      .then((token) => {
        if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      })
      .catch(() => undefined)
      .finally(() => {
        xhr.send(formData);
      });

    xhr.upload.addEventListener("progress", (e) => {
      if (!e.lengthComputable || !onProgress) return;
      const pct = Math.round((e.loaded / e.total) * 100);
      onProgress(pct);
    });

    xhr.addEventListener("load", () => {
      try {
        const body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body as UploadResponse);
        } else {
          reject(
            new UploadError(
              xhr.status,
              (body && (body.detail || body.error)) || xhr.statusText,
              body,
            ),
          );
        }
      } catch (e) {
        reject(new UploadError(xhr.status, `Invalid JSON: ${(e as Error).message}`));
      }
    });

    xhr.addEventListener("error", () => {
      reject(new UploadError(0, "Network error"));
    });
    xhr.addEventListener("abort", () => {
      reject(new UploadError(0, "Upload aborted", { aborted: true }));
    });
  });
}

/**
 * Fetch a short-lived signed URL for an already-uploaded object.
 * Used so the OCR preview iframe can render the uploaded PDF/image.
 */
export async function getSignedUrl(
  path: string,
  bucket?: string,
  ttl = 3600,
): Promise<SignedUrlResponse> {
  const params = new URLSearchParams({ path, ttl: String(ttl) });
  if (bucket) params.set("bucket", bucket);
  const res = await authedFetch(
    `/api/uploads/signed-url?${params.toString()}`,
    { method: "GET" },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new UploadError(res.status, body?.detail || res.statusText, body);
  }
  return res.json();
}

/**
 * Delete an uploaded object (best-effort cleanup if the user cancels).
 */
export async function deleteUploadedFile(path: string, bucket?: string): Promise<boolean> {
  const params = new URLSearchParams({ path });
  if (bucket) params.set("bucket", bucket);
  const res = await authedFetch(
    `/api/uploads?${params.toString()}`,
    { method: "DELETE" },
  );
  if (!res.ok) return false;
  const body = await res.json();
  return Boolean(body?.deleted);
}

/** A small file-extension whitelist for the UI dropzone. */
export const RESUME_ACCEPTED_EXT = [".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg"];
export const RESUME_ACCEPTED_MIME = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
];
export const RESUME_MAX_BYTES = 10 * 1024 * 1024; // 10 MB
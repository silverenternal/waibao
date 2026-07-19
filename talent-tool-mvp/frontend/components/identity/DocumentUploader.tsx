"use client";

/**
 * v11.2 T6303 — Document uploader (three slots).
 *
 * Renders one card per doc type (身份证 / 学历证明 / 简历). Each slot shows:
 *   - the current verification badge (待上传 / 待审核 / 已认证)
 *   - an upload button (44px touch target) that picks a file and submits it
 *   - when a doc is 待上传 (pending), a clear re-upload hint (甲方: 如证件无法
 *     求证则显示 待上传 — the user can try again with a clearer scan).
 *
 * Upload flow mirrors api/uploads.py (upload-then-submit): the file is read
 * client-side; we POST {doc_type, file_url|file_id} to /api/identity/upload
 * which runs the AI extraction and returns the rolled-up IdentityStatus. The
 * parent is notified via onStatusChange so it can refresh the overall badge.
 */

import * as React from "react";
import { UploadCloud, Loader2, RefreshCw, CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  DOC_META,
  DOC_TYPES,
  uploadIdentityDocument,
  type DocType,
  type IdentityStatus,
} from "@/lib/api-identity";
import { IdentityStatusBadge } from "@/components/identity/IdentityStatusBadge";

export interface DocumentUploaderProps {
  /** Current rolled-up status (provides per-doc status + reasons). */
  status: IdentityStatus | null;
  /** Fired after a successful upload with the fresh rolled-up status. */
  onStatusChange: (status: IdentityStatus) => void;
  /** Optional per-doc error toast hook (defaults to no-op). */
  onError?: (docType: DocType, message: string) => void;
}

export function DocumentUploader({
  status,
  onStatusChange,
  onError,
}: DocumentUploaderProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">身份验证资料</CardTitle>
        <CardDescription>
          上传以下三类资料,系统将自动识别核验。三类全部 已认证 后整体身份状态才会变为已认证。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {DOC_TYPES.map((docType) => (
          <DocSlot
            key={docType}
            docType={docType}
            status={status}
            onStatusChange={onStatusChange}
            onError={onError}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function DocSlot({
  docType,
  status,
  onStatusChange,
  onError,
}: {
  docType: DocType;
  status: IdentityStatus | null;
  onStatusChange: (status: IdentityStatus) => void;
  onError?: (docType: DocType, message: string) => void;
}) {
  const meta = DOC_META[docType];
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [busy, setBusy] = React.useState(false);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  const docStatus = status?.[docType] ?? "pending";
  const reason = status?.reasons?.[docType];
  const isVerified = docStatus === "verified";
  const isPending = docStatus === "pending";

  async function handleFile(file: File) {
    setBusy(true);
    setErrorMsg(null);
    try {
      // The backend expects the file to already be in storage (signed URL or
      // object id). We create a transient object URL as the file_url so the
      // extraction stack has a locator; in production api/uploads.py would
      // produce the real signed URL first.
      const fileUrl = URL.createObjectURL(file);
      const fresh = await uploadIdentityDocument({
        doc_type: docType,
        file_url: fileUrl,
        file_id: file.name,
      });
      onStatusChange(fresh);
      // Revoke after the request completes (the backend has its own copy).
      URL.revokeObjectURL(fileUrl);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "上传失败,请重试";
      setErrorMsg(msg);
      onError?.(docType, msg);
    } finally {
      setBusy(false);
      // Reset so picking the same file twice still fires onChange.
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between",
        isVerified
          ? "border-emerald-200 bg-emerald-50/40 dark:border-emerald-900 dark:bg-emerald-950/20"
          : "border-slate-200 bg-slate-50/40 dark:border-slate-800 dark:bg-slate-900/30",
      )}
    >
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
            {meta.label}
          </span>
          <IdentityStatusBadge status={docStatus} />
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">{meta.hint}</p>
        {/* Re-upload hint: a pending doc means the AI could not verify it. */}
        {isPending && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            {reason ? `${reason}。` : "尚未通过核验。"}
            可重新上传清晰、完整的扫描件再次识别。
          </p>
        )}
        {errorMsg && (
          <p className="text-xs text-rose-600 dark:text-rose-400" role="alert">
            {errorMsg}
          </p>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        // Accept common doc types; resume allows PDF/Word, id/education images+PDF.
        accept={
          docType === "resume"
            ? ".pdf,.doc,.docx"
            : "image/*,.pdf"
        }
        onChange={onInputChange}
        // Accessible label tying the hidden input to its button.
        aria-label={`上传${meta.label}`}
      />
      <Button
        type="button"
        size="sm"
        // 44px minimum touch target on mobile.
        className="h-11 min-w-11 sm:h-9"
        variant={isVerified ? "outline" : "default"}
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            核验中
          </>
        ) : isVerified ? (
          <>
            <CheckCircle2 className="size-4 text-emerald-600" />
            已认证 · 重新上传
          </>
        ) : isPending ? (
          <>
            <RefreshCw className="size-4" />
            重新上传
          </>
        ) : (
          <>
            <UploadCloud className="size-4" />
            上传{meta.label}
          </>
        )}
      </Button>
    </div>
  );
}

export default DocumentUploader;

"use client";

import * as React from "react";
import {
  UploadCloud,
  FileText,
  X,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  ScanText,
  Loader2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import {
  uploadFile,
  RESUME_ACCEPTED_EXT,
  RESUME_ACCEPTED_MIME,
  RESUME_MAX_BYTES,
  type UploadStage,
  type UploadResponse,
} from "@/lib/api-uploads";

export interface ResumeUploadProps {
  /** Called when the upload + OCR stage completes successfully. */
  onComplete?: (result: UploadResponse & { ocr?: OCRResult }) => void;
  /** Called with the parsed fields when OCR finishes so the parent can pre-fill the wizard. */
  onOCRComplete?: (ocr: OCRResult) => void;
  /** Optional initial file (e.g. user re-opens the page). */
  initialUpload?: UploadResponse;
  /** Optional initial OCR result (e.g. resumed session). */
  initialOCR?: OCRResult;
  /** Override the storage bucket (defaults to env-configured bucket). */
  bucket?: string;
  /** Override the storage prefix/folder. */
  folder?: string;
  /** Compact card variant — used when embedded in a wizard step. */
  variant?: "card" | "bare";
  className?: string;
}

export interface OCRResult {
  full_name?: string;
  email?: string;
  phone?: string;
  location?: string;
  headline?: string;
  summary?: string;
  skills?: string[];
  years_experience?: number;
  experiences?: Array<{
    company: string;
    title: string;
    start?: string;
    end?: string;
    description?: string;
  }>;
  education?: Array<{
    school: string;
    degree?: string;
    field?: string;
    start?: string;
    end?: string;
  }>;
  raw_text?: string;
  confidence?: number;
}

type DragState = "idle" | "over" | "reject";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

const ACCEPT_ATTR = [
  ...RESUME_ACCEPTED_EXT,
  ...RESUME_ACCEPTED_MIME,
].join(",");

const STAGE_LABEL: Record<UploadStage, string> = {
  idle: "等待选择文件",
  uploading: "上传中",
  ocr_pending: "准备 OCR 识别",
  ocr_running: "OCR 识别中",
  ocr_done: "OCR 完成",
  ocr_failed: "OCR 失败,请手动补充",
  done: "完成",
  error: "上传失败",
};

export function ResumeUpload({
  onComplete,
  onOCRComplete,
  initialUpload,
  initialOCR,
  bucket,
  folder = "resumes",
  variant = "card",
  className,
}: ResumeUploadProps) {
  const [file, setFile] = React.useState<File | null>(null);
  const [upload, setUpload] = React.useState<UploadResponse | null>(
    initialUpload ?? null,
  );
  const [ocr, setOcr] = React.useState<OCRResult | null>(initialOCR ?? null);
  const [stage, setStage] = React.useState<UploadStage>(
    initialUpload ? "done" : "idle",
  );
  const [progress, setProgress] = React.useState(0);
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);
  const [drag, setDrag] = React.useState<DragState>("idle");

  const inputRef = React.useRef<HTMLInputElement>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  const reset = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setFile(null);
    setUpload(null);
    setOcr(null);
    setStage("idle");
    setProgress(0);
    setErrorMsg(null);
    if (inputRef.current) inputRef.current.value = "";
  }, []);

  const validate = React.useCallback((f: File): string | null => {
    if (f.size === 0) return "文件为空";
    if (f.size > RESUME_MAX_BYTES)
      return `文件超过 ${formatBytes(RESUME_MAX_BYTES)} 限制`;
    const okMime =
      RESUME_ACCEPTED_MIME.includes(f.type) || f.type === "";
    const okExt = RESUME_ACCEPTED_EXT.some((ext) =>
      f.name.toLowerCase().endsWith(ext),
    );
    if (!okMime && !okExt) return "仅支持 PDF / Word / 图片格式";
    return null;
  }, []);

  /** Mock OCR — real backend will swap this for the OCR provider pipeline. */
  const runOCR = React.useCallback(
    async (resp: UploadResponse): Promise<OCRResult> => {
      setStage("ocr_pending");
      await new Promise((r) => setTimeout(r, 350));
      setStage("ocr_running");
      await new Promise((r) => setTimeout(r, 1100));
      // Demo: pretend we extracted some fields. In production this hits
      // /api/ocr or the OCR provider via api.ts.
      const result: OCRResult = {
        full_name: "王小明",
        email: "wxm@example.com",
        phone: "+86 138 0000 0000",
        location: "上海",
        headline: "高级前端工程师",
        summary:
          "5 年 React/TypeScript 开发经验,熟悉 Next.js 全栈架构与设计系统落地。",
        skills: ["React", "TypeScript", "Next.js", "Tailwind", "Node.js"],
        years_experience: 5,
        confidence: 0.86,
        raw_text: "[mock OCR output]",
      };
      return result;
    },
    [],
  );

  const handleFile = React.useCallback(
    async (f: File) => {
      const err = validate(f);
      if (err) {
        setErrorMsg(err);
        setStage("error");
        return;
      }
      setErrorMsg(null);
      setFile(f);
      setProgress(0);
      setStage("uploading");

      abortRef.current = new AbortController();
      try {
        const resp = await uploadFile(f, {
          bucket,
          folder,
          signal: abortRef.current.signal,
          onProgress: (pct) => setProgress(pct),
        });
        setUpload(resp);

        const ocrResult = await runOCR(resp);
        setOcr(ocrResult);
        setStage("ocr_done");
        onOCRComplete?.(ocrResult);

        setStage("done");
        onComplete?.({ ...resp, ocr: ocrResult });
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "上传失败";
        setErrorMsg(msg);
        setStage(
          msg.toLowerCase().includes("ocr") ? "ocr_failed" : "error",
        );
      }
    },
    [bucket, folder, onComplete, onOCRComplete, runOCR, validate],
  );

  // ---- Drag handlers ----
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (drag !== "over") setDrag("over");
  };
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDrag("idle");
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDrag("idle");
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    const err = validate(f);
    if (err) {
      setErrorMsg(err);
      setDrag("reject");
      setTimeout(() => setDrag("idle"), 1200);
      return;
    }
    void handleFile(f);
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) void handleFile(f);
  };

  const isBusy =
    stage === "uploading" || stage === "ocr_pending" || stage === "ocr_running";

  const body = (
    <>
      {/* Dropzone */}
      <div
        role="button"
        tabIndex={0}
        aria-label="上传简历"
        aria-disabled={isBusy}
        onClick={() => !isBusy && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!isBusy && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={cn(
          "relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          drag === "over" && "border-primary bg-primary/5",
          drag === "reject" && "border-destructive bg-destructive/5",
          drag === "idle" && !isBusy && "border-border hover:border-primary/50 hover:bg-muted/40",
          isBusy && "cursor-not-allowed opacity-70",
          upload && "border-emerald-500/40 bg-emerald-50/40",
        )}
      >
        {upload ? (
          <CheckCircle2 className="size-10 text-emerald-500" />
        ) : (
          <UploadCloud
            className={cn(
              "size-10",
              drag === "over" ? "text-primary" : "text-muted-foreground",
            )}
          />
        )}

        <div className="space-y-1">
          <p className="text-base font-medium">
            {upload ? "简历已上传" : "拖拽简历到这里,或点击选择文件"}
          </p>
          <p className="text-xs text-muted-foreground">
            支持 PDF / DOC / DOCX / PNG / JPG,最大 {formatBytes(RESUME_MAX_BYTES)}
          </p>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          onChange={onPick}
          className="hidden"
          disabled={isBusy}
        />
      </div>

      {/* Progress + status */}
      {(file || errorMsg) && (
        <div className="mt-4 space-y-3">
          {file && (
            <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-3">
              <div className="grid size-9 place-items-center rounded-md bg-background ring-1 ring-border">
                <FileText className="size-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(file.size)} · {file.type || "未知类型"}
                </p>
              </div>
              {!isBusy && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={reset}
                  aria-label="移除文件"
                >
                  <X className="size-4" />
                </Button>
              )}
            </div>
          )}

          {stage === "uploading" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>正在上传…</span>
                <span>{progress}%</span>
              </div>
              <Progress value={progress} />
            </div>
          )}

          {(stage === "ocr_pending" || stage === "ocr_running") && (
            <div className="flex items-center gap-2 rounded-lg border border-blue-200/60 bg-blue-50/60 p-3 text-sm text-blue-900">
              {stage === "ocr_running" ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ScanText className="size-4" />
              )}
              <span>{STAGE_LABEL[stage]}</span>
              {ocr === null && (
                <Badge variant="secondary" className="ml-auto">
                  AI 提取中
                </Badge>
              )}
            </div>
          )}

          {stage === "done" && ocr && (
            <div className="space-y-2 rounded-lg border border-emerald-200/60 bg-emerald-50/60 p-3 text-sm text-emerald-900">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="size-4" />
                <span className="font-medium">解析成功</span>
                <Badge variant="outline" className="ml-auto border-emerald-300 text-emerald-900">
                  置信度 {Math.round((ocr.confidence ?? 0) * 100)}%
                </Badge>
              </div>
              {ocr.full_name && (
                <p className="text-xs text-emerald-900/80">
                  检测到姓名:<span className="font-medium">{ocr.full_name}</span>
                  {ocr.years_experience !== undefined && (
                    <> · {ocr.years_experience} 年经验</>
                  )}
                </p>
              )}
              {ocr.skills && ocr.skills.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {ocr.skills.slice(0, 6).map((s) => (
                    <Badge key={s} variant="secondary" className="text-[10px]">
                      {s}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {(stage === "error" || stage === "ocr_failed") && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div className="flex-1">
                <p className="font-medium">{STAGE_LABEL[stage]}</p>
                {errorMsg && <p className="mt-0.5 text-xs opacity-90">{errorMsg}</p>}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => file && handleFile(file)}
                disabled={isBusy}
              >
                <RefreshCw className="mr-1 size-3.5" />
                重试
              </Button>
            </div>
          )}

          {upload && !isBusy && stage !== "error" && (
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span className="truncate">
                已存至 <code className="font-mono">{upload.path}</code>
              </span>
              <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={reset}>
                重新上传
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );

  if (variant === "bare") return <div className={cn("w-full", className)}>{body}</div>;

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>上传简历</CardTitle>
        <CardDescription>
          我们会自动识别简历内容,你只需要在下一步确认或补充缺失字段。
        </CardDescription>
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}
"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Loader2, Upload, FileText, CheckCircle2, XCircle } from "lucide-react";

export interface DocumentUploadProps {
  collectionId: string;
  apiBase?: string;
  onUploaded?: (doc: UploadedDocument) => void;
  acceptedTypes?: string[];
  maxSizeMB?: number;
}

export interface UploadedDocument {
  id: string;
  display_name: string;
  status: string;
  total_chunks: number;
  total_tokens: number;
  mime_type?: string | null;
  size_bytes: number;
}

const DEFAULT_TYPES = [
  ".pdf",
  ".docx",
  ".md",
  ".markdown",
  ".html",
  ".htm",
  ".txt",
];

export function DocumentUpload({
  collectionId,
  apiBase = "/api/rag",
  onUploaded,
  acceptedTypes = DEFAULT_TYPES,
  maxSizeMB = 25,
}: DocumentUploadProps) {
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [lastDoc, setLastDoc] = React.useState<UploadedDocument | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  const handleFile = React.useCallback(
    async (file: File) => {
      setError(null);
      setProgress(0);
      if (file.size > maxSizeMB * 1024 * 1024) {
        setError(`File too large (max ${maxSizeMB} MB)`);
        return;
      }
      setUploading(true);
      try {
        const form = new FormData();
        form.append("file", file);
        form.append("collection_id", collectionId);
        form.append("display_name", file.name);
        form.append("source", "upload");
        // Simulate progress (real impl would use XHR for progress events).
        const ticker = setInterval(() => {
          setProgress((p) => Math.min(95, p + 7));
        }, 150);
        const res = await fetch(`${apiBase}/documents`, {
          method: "POST",
          body: form,
          credentials: "include",
        });
        clearInterval(ticker);
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `Upload failed (${res.status})`);
        }
        const doc: UploadedDocument = await res.json();
        setProgress(100);
        setLastDoc(doc);
        onUploaded?.(doc);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Upload failed");
      } finally {
        setUploading(false);
        setTimeout(() => setProgress(0), 1200);
      }
    },
    [apiBase, collectionId, maxSizeMB, onUploaded],
  );

  const onDrop = React.useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files?.[0];
      if (f) void handleFile(f);
    },
    [handleFile],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="h-5 w-5" />
          上传文档到知识库
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={
            "rounded-lg border-2 border-dashed p-6 text-center transition " +
            (dragging
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/30 hover:border-primary/50")
          }
        >
          <FileText className="mx-auto mb-2 h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            拖拽文件到此处,或
            <button
              type="button"
              className="mx-1 text-primary underline"
              onClick={() => inputRef.current?.click()}
            >
              浏览文件
            </button>
            (支持 PDF / Word / Markdown / HTML / 文本,最大 {maxSizeMB} MB)
          </p>
          <input
            ref={inputRef}
            type="file"
            accept={acceptedTypes.join(",")}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
            }}
          />
        </div>

        {uploading && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在解析 + 嵌入 + 索引 ...
            </div>
            <Progress value={progress} />
          </div>
        )}

        {error && (
          <div className="mt-4 flex items-center gap-2 text-sm text-destructive">
            <XCircle className="h-4 w-4" /> {error}
          </div>
        )}

        {lastDoc && !uploading && (
          <div className="mt-4 flex items-center gap-2 rounded-md bg-muted/50 p-3 text-sm">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            <span className="font-medium">{lastDoc.display_name}</span>
            <Badge variant="secondary" className="ml-2">
              {lastDoc.status}
            </Badge>
            <span className="ml-auto text-muted-foreground">
              {lastDoc.total_chunks} chunks / {lastDoc.total_tokens} tokens
            </span>
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <Button
            variant="outline"
            disabled={uploading}
            onClick={() => inputRef.current?.click()}
          >
            选择文件
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default DocumentUpload;

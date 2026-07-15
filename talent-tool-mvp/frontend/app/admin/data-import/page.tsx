"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * Admin / Data Import — v11.0 / T6112 批量测试数据导入 UI.
 *
 * 支持两种导入方式:
 *   1. 文件上传:CSV / JSON / JSONL (拖拽或选择),解析后批量灌入后端。
 *   2. 一键种子:调用后端种子端点,生成 1000 求职者 / 10 企业 / 5 岗位 + 匹配。
 *
 * 对应后端:
 *   POST /api/admin/data-import/preview   —— 预览解析结果(前 N 行)
 *   POST /api/admin/data-import/commit    —— 提交批量写入
 *   POST /api/admin/data-import/seed      —— 触发 seed_test_data (演示数据)
 *
 * 仅 admin 角色可访问;FastAPI 层 403 兜底。
 */

import * as React from "react";
import { useRef, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { UploadCloud, Database, FileUp, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";

type DataType = "candidates" | "organisations" | "roles";
type FileKind = "json" | "jsonl" | "csv";

interface ImportResult {
  inserted: number;
  skipped: number;
  errors: { row: number; message: string }[];
}

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) || "";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`HTTP ${r.status}: ${text}`);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

/** 把任意行集合解析成对象数组(客户端预览用;后端最终再校验一次)。 */
function parseFile(text: string, kind: FileKind): Record<string, unknown>[] {
  if (kind === "json") {
    const data = JSON.parse(text);
    return Array.isArray(data) ? data : [data];
  }
  if (kind === "jsonl") {
    return text
      .split(/\r?\n/)
      .filter((l) => l.trim().length > 0)
      .map((l) => JSON.parse(l));
  }
  // csv: 首行表头,逗号分隔(简单实现,不含引号转义——生产用后端解析)
  const [headerLine, ...lines] = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  const headers = headerLine.split(",").map((h) => h.trim());
  return lines.map((line) => {
    const cells = line.split(",");
    const obj: Record<string, unknown> = {};
    headers.forEach((h, i) => (obj[h] = (cells[i] ?? "").trim()));
    return obj;
  });
}

function detectKind(name: string): FileKind | null {
  const lower = name.toLowerCase();
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".jsonl") || lower.endsWith(".ndjson")) return "jsonl";
  if (lower.endsWith(".csv")) return "csv";
  return null;
}

export default function DataImportPage() {
  const [dataType, setDataType] = useState<DataType>("candidates");
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<Record<string, unknown>[] | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"preview" | "commit" | "seed" | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [commitError, setCommitError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setFile(null);
    setParsed(null);
    setParseError(null);
    setResult(null);
    setCommitError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function onFileChosen(f: File | null) {
    reset();
    if (!f) return;
    const kind = detectKind(f.name);
    if (!kind) {
      setParseError("不支持的文件类型。请上传 .json / .jsonl / .csv。");
      return;
    }
    setFile(f);
    setBusy("preview");
    try {
      const text = await f.text();
      const rows = parseFile(text, kind);
      setParsed(rows);
      if (rows.length === 0) setParseError("文件为空或没有可解析的行。");
    } catch (err) {
      setParseError(`解析失败:${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function commit() {
    if (!parsed || parsed.length === 0) return;
    setBusy("commit");
    setCommitError(null);
    setResult(null);
    try {
      const res = await api<ImportResult>("/api/admin/data-import/commit", {
        method: "POST",
        body: JSON.stringify({ data_type: dataType, rows: parsed }),
      });
      setResult(res);
    } catch (err) {
      setCommitError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function seedDemo() {
    setBusy("seed");
    setCommitError(null);
    setResult(null);
    try {
      const res = await api<ImportResult>("/api/admin/data-import/seed", {
        method: "POST",
        body: JSON.stringify({ candidates: 1000, orgs: 10, with_sample_resumes: true }),
      });
      setResult(res);
    } catch (err) {
      setCommitError(
        `${err instanceof Error ? err.message : String(err)}\n(也可在宿主执行: python scripts/seed_test_data.py --with-sample-resumes)`,
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <ErrorBoundary>
      <div className="space-y-6 p-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">批量数据导入</h1>
          <p className="text-sm text-muted-foreground">
            上传 CSV / JSON 批量导入求职者 / 企业 / 岗位,或一键生成演示测试数据。所有数据在本地处理(LLM / OCR 走本地,不出甲方环境)。
          </p>
        </header>

        {/* 一键种子 */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-base">
                <Database className="h-4 w-4" /> 一键生成演示测试数据
              </CardTitle>
              <CardDescription>
                生成 1000 求职者 + 10 企业 + 5 体育用品行业岗位 + 自动匹配结果(等价于
                <code className="mx-1 rounded bg-muted px-1">python scripts/seed_test_data.py</code>)。
              </CardDescription>
            </div>
            <Button onClick={seedDemo} disabled={busy !== null}>
              {busy === "seed" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Database className="mr-2 h-4 w-4" />}
              生成演示数据
            </Button>
          </CardHeader>
        </Card>

        {/* 文件上传 */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileUp className="h-4 w-4" /> 上传文件批量导入
            </CardTitle>
            <CardDescription>支持 .json / .jsonl / .csv。每行一条记录。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <Select value={dataType} onValueChange={(v) => setDataType(v as DataType)}>
                <SelectTrigger className="w-48">
                  <SelectValue placeholder="数据类型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="candidates">求职者 candidates</SelectItem>
                  <SelectItem value="organisations">企业 organisations</SelectItem>
                  <SelectItem value="roles">岗位 roles</SelectItem>
                </SelectContent>
              </Select>
              <Input
                ref={inputRef}
                type="file"
                accept=".json,.jsonl,.ndjson,.csv"
                className="max-w-xs"
                onChange={(e) => onFileChosen(e.target.files?.[0] ?? null)}
              />
              {file && (
                <Badge variant="secondary" className="gap-1">
                  <UploadCloud className="h-3 w-3" /> {file.name}
                </Badge>
              )}
              {parsed && (
                <Button variant="outline" size="sm" onClick={reset}>
                  清除
                </Button>
              )}
            </div>

            {parseError && (
              <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{parseError}</span>
              </div>
            )}

            {parsed && parsed.length > 0 && (
              <div className="space-y-3">
                <div className="text-sm text-muted-foreground">
                  预览:解析到 <strong>{parsed.length}</strong> 条记录(展示前 5 条)。
                </div>
                <div className="overflow-x-auto rounded-md border">
                  <table className="w-full text-xs">
                    <thead className="bg-muted">
                      <tr>
                        {Object.keys(parsed[0]).slice(0, 6).map((h) => (
                          <th key={h} className="px-2 py-1.5 text-left font-medium">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {parsed.slice(0, 5).map((row, i) => (
                        <tr key={i} className="border-t">
                          {Object.keys(parsed[0]).slice(0, 6).map((h) => (
                            <td key={h} className="px-2 py-1.5 align-top">
                              {String(row[h] ?? "").slice(0, 40)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center gap-3">
                  <Button onClick={commit} disabled={busy !== null}>
                    {busy === "commit" ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <UploadCloud className="mr-2 h-4 w-4" />
                    )}
                    提交导入({parsed.length} 条 → {dataType})
                  </Button>
                </div>
              </div>
            )}

            {commitError && (
              <pre className="whitespace-pre-wrap rounded-md border border-rose-300 bg-rose-50 p-3 text-xs text-rose-800">
                {commitError}
              </pre>
            )}

            {result && (
              <div className="flex items-start gap-2 rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-800">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  导入完成:成功 <strong>{result.inserted}</strong> 条,跳过 {result.skipped} 条
                  {result.errors.length > 0 && (
                    <>
                      ,错误 {result.errors.length} 条:
                      <ul className="mt-1 list-disc pl-4 text-xs">
                        {result.errors.slice(0, 5).map((e, i) => (
                          <li key={i}>
                            第 {e.row} 行:{e.message}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </ErrorBoundary>
  );
}

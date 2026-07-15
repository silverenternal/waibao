"use client";

/**
 * T6108 — HR Assistant compare page (client).
 *
 * Two tabs:
 *   1. 简历对比 — pick 2-5 talents from the marketplace talent pool, run a
 *      side-by-side compare, and export the report (PDF/Word/txt).
 *   2. 面试题模板 — pick a role + count, generate 5-10 questions from the
 *      question bank, and export the template as PDF.
 */
import * as React from "react";
import { useCallback, useEffect, useState } from "react";

import { ResumeCompareTable } from "@/components/marketplace/ResumeCompareTable";
import { InterviewQuestionTemplate } from "@/components/marketplace/InterviewQuestionTemplate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import {
  compareResumes,
  exportCompareReport,
  generateInterviewQuestions,
  type CompareResult,
  type InterviewQuestionTemplate as Template,
} from "@/lib/api-hr-assistant";
import {
  fetchTalents,
  type TalentCard,
} from "@/lib/api-talent-market";

const ROLE_OPTIONS = [
  { value: "backend_engineer", label: "后端工程师" },
  { value: "frontend_engineer", label: "前端工程师" },
  { value: "fullstack_engineer", label: "全栈工程师" },
  { value: "mobile_engineer", label: "移动端工程师" },
  { value: "data_engineer", label: "数据工程师" },
  { value: "data_scientist", label: "数据科学家" },
  { value: "product_manager", label: "产品经理" },
  { value: "designer", label: "设计师" },
  { value: "marketing", label: "市场" },
  { value: "sales", label: "销售" },
];

const MIN_SELECT = 2;
const MAX_SELECT = 5;

export function CompareClient() {
  return (
    <div className="container mx-auto max-w-6xl space-y-6 px-4 py-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">HR 助手</h1>
        <p className="text-sm text-muted-foreground">
          简历并排比较 + 比较报告导出 + 面试题模板生成。
        </p>
      </header>

      <Tabs defaultValue="compare" className="w-full">
        <TabsList>
          <TabsTrigger value="compare">简历对比</TabsTrigger>
          <TabsTrigger value="questions">面试题模板</TabsTrigger>
        </TabsList>
        <TabsContent value="compare" className="mt-4">
          <CompareTab />
        </TabsContent>
        <TabsContent value="questions" className="mt-4">
          <QuestionsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ===========================================================================
// Tab 1 — resume compare
// ===========================================================================

function CompareTab() {
  const [talents, setTalents] = useState<TalentCard[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loadingPool, setLoadingPool] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadingPool(true);
    fetchTalents({ page: 1, page_size: 30 })
      .then((res) => {
        if (active) setTalents(res.data ?? []);
      })
      .catch((e) => {
        if (active) setError(errMsg(e, "加载人才池失败"));
      })
      .finally(() => {
        if (active) setLoadingPool(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= MAX_SELECT) return prev;
      return [...prev, id];
    });
  }, []);

  const runCompare = useCallback(async () => {
    if (selected.length < MIN_SELECT) return;
    setComparing(true);
    setError(null);
    try {
      const res = await compareResumes({ candidate_ids: selected });
      setResult(res);
    } catch (e) {
      setError(errMsg(e, "对比失败"));
    } finally {
      setComparing(false);
    }
  }, [selected]);

  const doExport = useCallback(
    async (format: "txt" | "docx" | "pdf") => {
      try {
        const blob = await exportCompareReport("0", format);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `compare_report.${format}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (e) {
        setError(errMsg(e, "导出失败"));
      }
    },
    []
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            选择简历 ({selected.length}/{MAX_SELECT}, 至少 {MIN_SELECT} 份)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {loadingPool ? (
            <p className="text-sm text-muted-foreground">加载人才池…</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {talents.map((t) => {
                const checked = selected.includes(t.id);
                const disabled = !checked && selected.length >= MAX_SELECT;
                return (
                  <label
                    key={t.id}
                    className={`flex cursor-pointer items-center gap-2 rounded-md border p-2 text-sm transition ${
                      checked
                        ? "border-primary bg-primary/5"
                        : disabled
                          ? "cursor-not-allowed opacity-50"
                          : "hover:bg-muted"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggle(t.id)}
                      className="h-4 w-4"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{t.name}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {t.title} · {t.city}
                      </div>
                    </div>
                    <Badge variant="outline" className="shrink-0">
                      {t.match_score}
                    </Badge>
                  </label>
                );
              })}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 pt-2">
            <Button
              onClick={runCompare}
              disabled={selected.length < MIN_SELECT || comparing}
            >
              {comparing ? "对比中…" : "开始对比"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => doExport("pdf")}
              disabled={!result}
            >
              导出 PDF
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => doExport("docx")}
              disabled={!result}
            >
              导出 Word
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => doExport("txt")}
              disabled={!result}
            >
              导出 TXT
            </Button>
            {selected.length > 0 ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelected([])}
              >
                清空选择
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : null}

      {result ? <ResumeCompareTable result={result} /> : null}
    </div>
  );
}

// ===========================================================================
// Tab 2 — interview question template
// ===========================================================================

function QuestionsTab() {
  const [role, setRole] = useState("backend_engineer");
  const [count, setCount] = useState(8);
  const [difficulty, setDifficulty] = useState<string>("mid");
  const [loading, setLoading] = useState(false);
  const [template, setTemplate] = useState<Template | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await generateInterviewQuestions({
        role,
        count,
        difficulty: difficulty || undefined,
      });
      setTemplate(res);
    } catch (e) {
      setError(errMsg(e, "生成面试题失败"));
    } finally {
      setLoading(false);
    }
  }, [role, count, difficulty]);

  const exportPdf = useCallback(async () => {
    if (!template) return;
    // Reuse the HR-assistant compare-report export endpoint shape (PDF)
    // by rendering the template text client-side for download.
    try {
      const text = renderTemplateText(template);
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${role}_interview_template.txt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(errMsg(e, "导出失败"));
    }
  }, [template, role]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">生成面试题模板</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">岗位</label>
              <Select value={role} onValueChange={(v) => setRole(v ?? "")}>
                <SelectTrigger className="w-44" aria-label="岗位">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLE_OPTIONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">题数</label>
              <Select
                value={String(count)}
                onValueChange={(v) => setCount(Number(v))}
              >
                <SelectTrigger className="w-24" aria-label="题数">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[5, 6, 7, 8, 10].map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      {n} 题
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">难度</label>
              <Select value={difficulty} onValueChange={(v) => setDifficulty(v ?? "")}>
                <SelectTrigger className="w-32" aria-label="难度">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="junior">初级</SelectItem>
                  <SelectItem value="mid">中级</SelectItem>
                  <SelectItem value="senior">高级</SelectItem>
                  <SelectItem value="lead">专家</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Button onClick={run} disabled={loading}>
              {loading ? "生成中…" : "生成模板"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={exportPdf}
              disabled={!template}
            >
              导出模板
            </Button>
          </div>
        </CardContent>
      </Card>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {template ? <InterviewQuestionTemplate template={template} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const body = e.body as { detail?: string } | null;
    return body?.detail ?? `${fallback}: ${e.status}`;
  }
  return e instanceof Error ? `${fallback}: ${e.message}` : fallback;
}

function renderTemplateText(t: Template): string {
  const lines: string[] = [
    t.title,
    "=".repeat(40),
    `岗位: ${t.role}  |  题数: ${t.count}  |  预计 ${t.estimated_minutes} 分钟`,
    "",
  ];
  t.questions.forEach((q, idx) => {
    lines.push(`${idx + 1}. ${q.title}  [${q.difficulty}/${q.type}]`);
    lines.push(q.prompt);
    if (q.expected_points.length) {
      lines.push("  期望要点:");
      q.expected_points.forEach((p) => lines.push(`    - ${p}`));
    }
    lines.push("");
  });
  return lines.join("\n");
}

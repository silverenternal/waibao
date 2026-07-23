"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Markdown } from "@/components/shared";

/**
 * 语音日记主页面 (T3607 / v9.1).
 *
 * 流程:
 *   1. 用户点麦克风 → Web Audio 实时波形 + 计时
 *   2. 停止 → 调 /api/voice/transcribe(Whisper,失败降级 aliyun_stt)
 *   3. 转写成功 → 自动用 transcript 提交 /api/voice/submit
 *   4. 触发 Daily Journal Agent + Emotion Agent,展示 AI 评分/建议/警示/行动项
 *
 * 用户也可以改用文本输入兜底(右下文本卡)。
 *
 * 复用:VoiceRecorder(已实现波形/转写),VoiceWaveform(回放峰值);
 * 情绪/文字回退输入 + AI 评价 + 空态/可访问性在本页内组装。
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Lightbulb,
  Loader2,
  Mic,
  PenLine,
  Sparkles,
  Target,
  Volume2,
  Waves,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import VoiceRecorder from "@/components/VoiceRecorder";
import {
  submitVoiceJournal,
  type VoiceSubmitResponse,
} from "@/lib/api-voice";

// ---------------------------------------------------------------------------
// 主题
// ---------------------------------------------------------------------------

const TONES = {
  excellent: "bg-emerald-100 text-emerald-700",
  good: "bg-sky-100 text-sky-700",
  warning: "bg-rose-100 text-rose-700",
} as const;

// ---------------------------------------------------------------------------
// 页面
// ---------------------------------------------------------------------------

export default function VoiceJournalPage() {
  const router = useRouter();

  const [text, setText] = React.useState("");
  const [provider, setProvider] = React.useState<string>("");
  const [language, setLanguage] = React.useState<string>("auto");
  const [transcribeError, setTranscribeError] = React.useState<string | null>(
    null,
  );
  const [submitting, setSubmitting] = React.useState(false);
  const [result, setResult] = React.useState<VoiceSubmitResponse | null>(null);
  const [durationSec, setDurationSec] = React.useState<number | null>(null);

  // --- transcript from VoiceRecorder ---
  async function handleTranscript(transcript: string, usedProvider: string) {
    setTranscribeError(null);
    setText(transcript);
    setProvider(usedProvider);
    if (!transcript.trim()) {
      setTranscribeError("没有识别到内容,请重试或改用文本");
      return;
    }
    await submit(transcript, usedProvider);
  }

  // --- 通用提交(语音转写 或 文本兜底) ---
  async function submit(transcript: string, usedProvider: string) {
    setSubmitting(true);
    setResult(null);
    try {
      const data = await submitVoiceJournal(transcript, {
        provider: usedProvider,
        language: language === "auto" ? undefined : language,
        duration_sec: durationSec ?? undefined,
      });
      setResult(data);
    } catch (e: unknown) {
      setTranscribeError(
        e instanceof Error ? e.message : "提交失败,请稍后再试",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function resetAll() {
    setText("");
    setProvider("");
    setTranscribeError(null);
    setResult(null);
    setDurationSec(null);
  }

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 via-indigo-50/30 to-slate-100/50">
        {/* 顶部导航 */}
        <div className="border-b bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-3 px-6 py-4">
            <div className="flex items-center gap-2">
              <span className="grid size-9 place-items-center rounded-lg bg-gradient-to-br from-rose-500 to-orange-500 text-white shadow-sm">
                <Mic className="size-4" />
              </span>
              <div>
                <h1 className="text-lg font-semibold text-slate-900">
                  语音日记
                </h1>
                <p className="text-xs text-slate-500">
                  说话即可,Whisper 自动转写 · 失败时降级到 aliyun_stt
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push("/jobseeker/journal")}
                className="gap-1"
              >
                <ArrowLeft className="size-3.5" /> 返回日记
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push("/jobseeker/journal/analytics")}
                className="gap-1"
              >
                <Sparkles className="size-3.5" /> 分析
              </Button>
            </div>
          </div>
        </div>
        <main className="mx-auto max-w-2xl space-y-5 px-6 py-6">
          {/* 录音区 */}
          <Card>
            <CardContent className="space-y-3 py-5">
              <header className="flex items-center gap-2">
                <Waves className="size-4 text-rose-500" />
                <p className="text-sm font-medium text-slate-800">开始录音</p>
                <Badge variant="outline" className="ml-auto text-[10px]">
                  <Volume2 className="mr-1 size-3" /> Web Audio · 实时波形
                </Badge>
              </header>
              <p className="text-xs leading-relaxed text-slate-500">
                点击下方「开始录音」按钮,对着麦克风描述今天的工作、心情与下一步计划;
                建议控制在 3 分钟以内,转写和 AI 评价会自动进行。
              </p>

              <VoiceRecorder
                onTranscript={handleTranscript}
                onError={(e) => setTranscribeError(e)}
                language={language}
                maxDurationSec={180}
              />

              {/* 语言选择 */}
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <label
                  htmlFor="voice-lang"
                  className="font-medium text-slate-600"
                >
                  语言
                </label>
                <select
                  id="voice-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                >
                  <option value="auto">自动检测</option>
                  <option value="zh">中文</option>
                  <option value="en">English</option>
                  <option value="ja">日本語</option>
                </select>
                {provider && (
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px]">
                    上次转写 provider: {provider}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* 转写结果 / 文本兜底 */}
          <Card>
            <CardContent className="space-y-3 py-5">
              <header className="flex items-center gap-2">
                <PenLine className="size-4 text-indigo-500" />
                <p className="text-sm font-medium text-slate-800">
                  转写文本
                </p>
                <Badge variant="secondary" className="ml-auto text-[10px]">
                  {text.length} 字
                </Badge>
              </header>
              <textarea
                data-testid="voice-text-fallback"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={6}
                placeholder="语音转写的内容会出现在这里;你也可以直接输入文字作为兜底。"
                aria-label="语音转写文本"
                className="w-full resize-y rounded-lg border border-slate-200 bg-white p-3 text-sm leading-relaxed text-slate-800 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-slate-500">
                  转写后会自动提交,如需修改文字可重新点击提交。
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={resetAll}
                    disabled={!text && !result}
                  >
                    清空
                  </Button>
                  <Button
                    data-testid="voice-submit-text"
                    onClick={() => submit(text, "manual")}
                    disabled={!text.trim() || submitting}
                    size="sm"
                    className="gap-1"
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="size-3.5 animate-spin" /> 提交中…
                      </>
                    ) : (
                      <>
                        提交日记 <ChevronRight className="size-3.5" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 错误提示 */}
          {transcribeError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700"
            >
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              <span>{transcribeError} — 你也可以直接输入文字日记。</span>
            </div>
          )}

          {/* AI 评价 */}
          {result && <AIResult data={result} />}

          {/* 空态:还没录过 */}
          {!result && !transcribeError && !submitting && <FirstTimeHint />}
        </main>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// AI 评价卡
// ---------------------------------------------------------------------------

function AIResult({ data }: { data: VoiceSubmitResponse }) {
  const rating = data.journal?.rating ?? null;
  const tone = TONES[(rating as keyof typeof TONES) ?? "good"] ??
    "bg-slate-100 text-slate-700";
  const emotionFlags = data.emotion?.flags ?? [];
  return (
    <Card
      className="overflow-hidden"
      data-testid="voice-result"
      aria-live="polite"
    >
      <CardContent className="space-y-3 py-5">
        <header className="flex items-center gap-2">
          <Sparkles className="size-4 text-amber-500" />
          <p className="text-sm font-medium text-slate-800">AI 评价</p>
          <span
            className={cn(
              "ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
              tone,
            )}
          >
            <CheckCircle2 className="size-3" />
            {rating || "—"}
          </span>
        </header>

        {data.journal?.advice && (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50/60 px-3 py-2 text-sm text-slate-800">
            <Lightbulb className="mt-0.5 size-4 text-amber-500" />
            <Markdown size="sm">{data.journal.advice}</Markdown>
          </div>
        )}

        {!!data.journal?.warnings?.length && (
          <Section
            title="提醒"
            icon={AlertTriangle}
            iconClass="text-amber-700"
            borderClass="border-amber-200 bg-amber-50/60"
            textClass="text-amber-800"
            items={data.journal.warnings}
          />
        )}

        {!!data.journal?.action_items?.length && (
          <Section
            title="行动项"
            icon={Target}
            iconClass="text-blue-700"
            borderClass="border-blue-200 bg-blue-50/60"
            textClass="text-blue-800"
            items={data.journal.action_items}
          />
        )}

        {(data.emotion?.summary || emotionFlags.length > 0) && (
          <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-700">
            <p className="mb-1 inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-slate-500">
              情绪分析
            </p>
            {data.emotion?.summary && (
              <p className="mb-1 whitespace-pre-wrap leading-relaxed">
                {data.emotion.summary}
              </p>
            )}
            {emotionFlags.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {emotionFlags.map((f, i) => (
                  <Badge
                    key={i}
                    variant="secondary"
                    className="bg-violet-100 text-violet-700 text-[10px]"
                  >
                    {f}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <p className="text-[10px] text-slate-400">
            AI 评价基于今日情绪和日记语义,仅供自我回顾参考。
          </p>
          <a
            href="/jobseeker/journal/analytics"
            className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
          >
            <BookOpen className="size-3.5" /> 查看完整趋势
          </a>
        </div>
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  items,
  icon: Icon,
  iconClass,
  borderClass,
  textClass,
}: {
  title: string;
  items: string[];
  icon: React.ComponentType<{ className?: string }>;
  iconClass: string;
  borderClass: string;
  textClass: string;
}) {
  return (
    <div className={cn("rounded-lg border p-3 text-xs", borderClass, textClass)}>
      <p className="mb-1 inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide opacity-80">
        <Icon className={cn("size-3.5", iconClass)} /> {title}
      </p>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-current opacity-50" />
            <span className="whitespace-pre-wrap leading-relaxed">{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FirstTimeHint() {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
        <span className="grid size-12 place-items-center rounded-full bg-rose-50 text-rose-400 ring-1 ring-rose-100">
          <Mic className="size-5" />
        </span>
        <p className="text-sm font-medium text-slate-700">
          第一次使用?
        </p>
        <p className="max-w-sm text-xs leading-relaxed text-slate-500">
          点击「开始录音」描述今天的工作;转写后会自动调用 Daily Journal Agent +
          Emotion Agent,生成 AI 评分、建议、行动项与情绪标签。
        </p>
        <ul className="mt-1 grid w-full max-w-sm grid-cols-1 gap-1.5 text-left text-[11px] text-slate-500">
          <li className="flex items-start gap-1.5">
            <CheckCircle2 className="mt-0.5 size-3 text-emerald-500" />
            支持中 / 英 / 日,语言可在录音前切换。
          </li>
          <li className="flex items-start gap-1.5">
            <CheckCircle2 className="mt-0.5 size-3 text-emerald-500" />
            麦克风权限被拒时,自动降级到文本输入。
          </li>
          <li className="flex items-start gap-1.5">
            <CheckCircle2 className="mt-0.5 size-3 text-emerald-500" />
            录音数据只在本地处理,转写后立即提交。
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}

"use client";

/**
 * ToneSimulator (v8.1 T3701) — Open WebUI / Linear-style input preview.
 *
 * Two-pane editor: input (left) and live preview (right), with a toolbar for
 * tone switching. The right pane updates as you type — even before any API
 * call — by applying rule-based rephrasings client-side so the HR can see
 * "what would change" instantly. The "去模板化" button triggers the real
 * AI rewriter.
 *
 * Layout is the classic Open WebUI chat-input dual column: param chips on top,
 * the textarea takes 60% width on desktop (stacked on mobile), and the
 * preview is in a bordered card with line-by-line tone annotation.
 */

import * as React from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sparkles,
  Wand2,
  Quote,
  History,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "formal" | "casual" | "data_driven" | "relationship_driven";

const TONE_OPTIONS: {
  value: Tone | "auto";
  label: string;
  emoji: string;
  helper: string;
}[] = [
  { value: "auto", label: "自动", emoji: "🤖", helper: "从历史推断" },
  { value: "formal", label: "正式得体", emoji: "📜", helper: "书面、客气" },
  { value: "casual", label: "亲切口语", emoji: "😊", helper: "对话感、轻松" },
  { value: "data_driven", label: "数据驱动", emoji: "📊", helper: "讲数字、收益" },
  { value: "relationship_driven", label: "关系维护", emoji: "💞", helper: "长期关系感" },
];

// Heuristic client-side rewriters so the preview is responsive even before
// the AI roundtrip. Real AI rewriter replaces these via /api/.../tone/rewrite.
const TONE_TRANSFORMS: Record<Tone, Array<[RegExp, string]>> = {
  formal: [
    [/你/g, "您"],
    [/咱们/g, "我们"],
    [/看下/g, "请过目"],
    [/帮忙/g, "协助"],
    [/谢谢/g, "非常感谢"],
    [/加油/g, "共同努力"],
  ],
  casual: [
    [/您/g, "你"],
    [/非常感谢/g, "谢啦"],
    [/请/g, ""],
    [/协助/g, "帮个忙"],
    [/我们/g, "咱们"],
  ],
  data_driven: [
    [/增长/g, "增长（QoQ +N%）"],
    [/辛苦/g, "辛苦了，本次产出等于团队基线 ×1.4"],
    [/按时/g, "按计划节点"],
  ],
  relationship_driven: [
    [/!/g, "~"],
    [/请/g, ""],
    [/谢谢/g, "很开心和你一起"],
  ],
};

interface ToneProfile {
  primary_tone: Tone;
  tone_scores: Record<Tone, number>;
  sample_count: number;
}

function applyToneLocal(text: string, tone: Tone): string {
  let out = text;
  for (const [pattern, replacement] of TONE_TRANSFORMS[tone]) {
    out = out.replace(pattern, replacement);
  }
  return out;
}

const SAMPLE_HISTORY = [
  "请您按时提交周报,我们一起 review。",
  "Q3 增长 30%,转化率达到 12%,辛苦了。",
  "咱们下周二开战略会,大家加油!",
  "记得先和候选人约沟通时间,别催太紧。",
];

export interface ToneSimulatorProps {
  userId?: string;
  history?: string[];
  className?: string;
}

export function ToneSimulator({ userId, history, className }: ToneSimulatorProps) {
  const sampleHistory = history ?? SAMPLE_HISTORY;
  const [scene, setScene] = React.useState(
    "您好,我们想约您下周二 10 点聊一下 offer 细节。",
  );
  const [manualTone, setManualTone] = React.useState<Tone | "auto">("auto");
  const [profile, setProfile] = React.useState<ToneProfile | null>(null);
  const [aiResult, setAiResult] = React.useState<string>("");
  const [loading, setLoading] = React.useState(false);
  const [tab, setTab] = React.useState<"preview" | "ai">("preview");

  const activeTone: Tone =
    manualTone === "auto" ? profile?.primary_tone ?? "casual" : manualTone;
  const localPreview = React.useMemo(
    () => (scene ? applyToneLocal(scene, activeTone) : ""),
    [scene, activeTone],
  );

  const aggregate = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/tone/aggregate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId || "demo-user",
          history: sampleHistory,
          manual_override: manualTone === "auto" ? null : manualTone,
        }),
      });
      if (r.ok) setProfile(await r.json());
    } finally {
      setLoading(false);
    }
  };

  const rewrite = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/v8_1_p2/tone/rewrite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template: scene,
          user_id: userId || "demo-user",
          history: sampleHistory,
          manual_override: manualTone === "auto" ? null : manualTone,
        }),
      });
      if (r.ok) {
        const data = await r.json();
        setAiResult(data.result || "");
        setTab("ai");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className={cn("w-full overflow-hidden", className)}>
      <CardHeader className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <CardTitle>语气模拟器 · Tone Simulator</CardTitle>
          <Badge variant="secondary">v8.1 T3701</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          双栏边写边看,系统按老板历史语气重写。
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 p-2">
          <Select
            value={manualTone}
            onValueChange={(v) => setManualTone(v as Tone | "auto")}
          >
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TONE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.emoji} {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-xs text-muted-foreground">
            {TONE_OPTIONS.find((o) => o.value === activeTone)?.helper}
          </span>
          <div className="ml-auto flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={aggregate}
              disabled={loading}
              className="gap-1"
            >
              <History className="h-3.5 w-3.5" />
              学习画像
            </Button>
            <Button
              size="sm"
              onClick={rewrite}
              disabled={loading || !scene}
              className="gap-1"
            >
              <Wand2 className="h-3.5 w-3.5" />
              去模板化
            </Button>
          </div>
        </div>

        {/* Editor + preview */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-muted-foreground">输入 (您的话)</span>
              <span className="text-muted-foreground">{scene.length} 字</span>
            </div>
            <Textarea
              value={scene}
              onChange={(e) => setScene(e.target.value)}
              placeholder="例如:请按时提交周报。"
              rows={6}
              className="resize-y"
              aria-label="Tone scenario input"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="inline-flex items-center gap-1 font-medium text-muted-foreground">
                <Sparkles className="h-3 w-3" /> 即时预览 ({TONE_OPTIONS.find((o) => o.value === activeTone)?.label})
              </span>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => setTab(tab === "preview" ? "ai" : "preview")}
              >
                {tab === "preview" ? "看 AI 版本" : "返回本地预览"}
                <ChevronRight className="inline h-3 w-3" />
              </button>
            </div>
            {tab === "preview" ? (
              <div
                role="region"
                aria-label="Live tone preview"
                className="min-h-[140px] rounded-lg border bg-primary/5 p-3 text-sm leading-relaxed"
              >
                {localPreview || (
                  <span className="text-muted-foreground">在上方输入文字预览…</span>
                )}
              </div>
            ) : (
              <div className="min-h-[140px] rounded-lg border bg-emerald-50 dark:bg-emerald-950/30 p-3 text-sm leading-relaxed">
                {aiResult || (
                  <span className="text-muted-foreground">
                    点击 <Wand2 className="inline h-3 w-3" /> 去模板化 等待 AI…
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Profile + history */}
        {profile && (
          <div className="grid gap-3 rounded-lg border bg-muted/30 p-3 text-sm lg:grid-cols-3">
            <div className="lg:col-span-1">
              <div className="text-xs font-medium text-muted-foreground mb-1">
                主语气
              </div>
              <div className="flex items-center gap-2">
                <Badge>
                  {TONE_OPTIONS.find((o) => o.value === profile.primary_tone)?.emoji}{" "}
                  {TONE_OPTIONS.find((o) => o.value === profile.primary_tone)?.label ??
                    profile.primary_tone}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  样本 {profile.sample_count}
                </span>
              </div>
            </div>
            <div className="lg:col-span-2 space-y-1">
              {Object.entries(profile.tone_scores).map(([t, s]) => (
                <ScoreRow key={t} label={t} value={s as number} />
              ))}
            </div>
          </div>
        )}

        <details className="rounded-lg border p-3 text-sm">
          <summary className="flex cursor-pointer items-center gap-1 text-muted-foreground hover:text-foreground">
            <Quote className="h-3 w-3" />
            历史语气样本 ({sampleHistory.length})
          </summary>
          <ul className="mt-2 space-y-1 text-xs">
            {sampleHistory.map((h, i) => (
              <li key={i} className="rounded bg-muted px-2 py-1">
                {h}
              </li>
            ))}
          </ul>
        </details>
      </CardContent>
    </Card>
  );
}

function ScoreRow({ label, value }: { label: string; value: number }) {
  const pct = Math.min(100, Math.max(0, value * 100));
  return (
    <div className="flex items-center gap-2">
      <span className="w-28 shrink-0 text-xs text-muted-foreground">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-background">
        <div
          className="h-full rounded-full bg-primary"
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
        />
      </div>
      <span className="w-12 text-right font-mono text-xs tabular-nums">
        {pct.toFixed(1)}%
      </span>
    </div>
  );
}

export default ToneSimulator;

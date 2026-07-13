"use client";

/**
 * v9.1 Journal 主页面 (T3601 / T3605).
 *
 * 设计要点:
 *  - Notion 风块编辑器(contenteditable + 段落/标题/列表),自适应撑高
 *  - 标签评分:多维标签(心情 / 能量 / 压力)取代单滑块,符合 GTD 心境记录习惯
 *  - 三态行动项:本次提交后弹出的行动项(待办 / 进行中 / 已完成),逐项勾选状态
 *  - 提交触发 /api/journal,展开 AI 评价卡(评分 / 建议 / 警示 / 行动)
 *  - 时间线 / 空态 / 可访问性(aria-live,role,focus 管理)
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Circle,
  CircleDashed,
  CircleDot,
  Lightbulb,
  Loader2,
  Mic,
  PenLine,
  Plus,
  RotateCcw,
  Sparkles,
  Target,
  Trash2,
  Zap,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { journalApi } from "@/lib/api-journal";

// ---------------------------------------------------------------------------
// 类型 & 常量
// ---------------------------------------------------------------------------

import type { JournalRating } from "@/lib/api-journal";

type Rating = JournalRating;

type MoodTag = "calm" | "happy" | "focused" | "tired" | "anxious" | "frustrated";
type EnergyTag = "high" | "medium" | "low";
type StressTag = "calm" | "mild" | "high";

interface JournalEntry {
  id: string;
  journal_date: string;
  content: string;
  mood_score: number | null;
  ai_rating: Rating;
  ai_advice: string | null;
  ai_warnings: string[];
  ai_action_items: string[];
  energy_tag?: string | null;
  stress_tag?: string | null;
  mood_tag?: string | null;
}

type ActionState = "pending" | "in_progress" | "done";

interface LocalActionItem {
  id: string;
  title: string;
  state: ActionState;
}

const MOOD_TAGS: Array<{ key: MoodTag; label: string; emoji: string }> = [
  { key: "happy", label: "愉悦", emoji: "😊" },
  { key: "calm", label: "平静", emoji: "😐" },
  { key: "focused", label: "专注", emoji: "🎯" },
  { key: "tired", label: "疲惫", emoji: "😪" },
  { key: "anxious", label: "焦虑", emoji: "😰" },
  { key: "frustrated", label: "挫败", emoji: "😤" },
];

const ENERGY_TAGS: Array<{ key: EnergyTag; label: string }> = [
  { key: "high", label: "高能量" },
  { key: "medium", label: "中等" },
  { key: "low", label: "低能量" },
];

const STRESS_TAGS: Array<{ key: StressTag; label: string }> = [
  { key: "calm", label: "无压力" },
  { key: "mild", label: "轻度" },
  { key: "high", label: "高压" },
];

const RATING_LABEL: Record<string, { label: string; tone: string; ring: string }> = {
  excellent: {
    label: "极佳",
    tone: "bg-emerald-100 text-emerald-700",
    ring: "ring-emerald-200",
  },
  good: {
    label: "稳定",
    tone: "bg-sky-100 text-sky-700",
    ring: "ring-sky-200",
  },
  warning: {
    label: "需关注",
    tone: "bg-rose-100 text-rose-700",
    ring: "ring-rose-200",
  },
};

const ACTION_STATES: Array<{
  key: ActionState;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  className: string;
}> = [
  { key: "pending", label: "待办", icon: Circle, className: "text-slate-500" },
  {
    key: "in_progress",
    label: "进行中",
    icon: CircleDot,
    className: "text-blue-600",
  },
  {
    key: "done",
    label: "已完成",
    icon: CheckCircle2,
    className: "text-emerald-600",
  },
];

function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

// ---------------------------------------------------------------------------
// Notion 风块编辑器
// ---------------------------------------------------------------------------

interface Block {
  id: string;
  type: "h1" | "h2" | "p" | "list";
  text: string;
}

function blocksToMarkdown(blocks: Block[]): string {
  return blocks
    .map((b) => {
      const t = b.text.trim();
      if (!t) return "";
      if (b.type === "h1") return `# ${t}`;
      if (b.type === "h2") return `## ${t}`;
      if (b.type === "list") return `- ${t}`;
      return t;
    })
    .filter(Boolean)
    .join("\n\n");
}

function NotebookEditor({
  value,
  onChange,
  disabled,
}: {
  value: Block[];
  onChange: (b: Block[]) => void;
  disabled?: boolean;
}) {
  const editorRef = React.useRef<HTMLDivElement | null>(null);
  const focusIdRef = React.useRef<string | null>(null);
  const lastHtmlRef = React.useRef<string>("");
  const [activeId, setActiveId] = React.useState<string | null>(
    value[0]?.id ?? null,
  );
  const activeType = value.find((b) => b.id === activeId)?.type ?? "p";

  // 从 blocks 渲染成 HTML
  const renderHtml = React.useCallback((blocks: Block[]) => {
    return blocks
      .map((b) => {
        const safe = escapeHtml(b.text || "");
        if (b.type === "h1")
          return `<h1 data-block-id="${b.id}" data-type="h1" class="nb-h1">${safe || "<br/>"}</h1>`;
        if (b.type === "h2")
          return `<h2 data-block-id="${b.id}" data-type="h2" class="nb-h2">${safe || "<br/>"}</h2>`;
        if (b.type === "list")
          return `<p data-block-id="${b.id}" data-type="list" class="nb-li"><span class="nb-bullet">•</span><span class="nb-li-text">${safe || "<br/>"}</span></p>`;
        return `<p data-block-id="${b.id}" data-type="p" class="nb-p">${safe || "<br/>"}</p>`;
      })
      .join("");
  }, []);

  // 初始化 + 外部 value 变化时同步
  React.useEffect(() => {
    const el = editorRef.current;
    if (!el) return;
    const html = renderHtml(value);
    if (el.innerHTML !== html) {
      el.innerHTML = html;
      lastHtmlRef.current = html;
    }
  }, [value, renderHtml]);

  // 编辑器内 input 事件 → 同步 blocks
  const handleInput = React.useCallback(() => {
    const el = editorRef.current;
    if (!el) return;
    const els = Array.from(
      el.querySelectorAll<HTMLElement>("[data-block-id]"),
    );
    const map = new Map(value.map((b) => [b.id, b]));
    const next: Block[] = els.map((node) => {
      const id = node.getAttribute("data-block-id") || uid();
      const type = (node.getAttribute("data-type") as Block["type"]) || "p";
      // 提取 .nb-li-text 的内容;否则取整段
      const liSpan = node.querySelector<HTMLElement>(".nb-li-text");
      const text = (liSpan ? liSpan.textContent : node.textContent) ?? "";
      return { id, type, text };
    });
    // 保留未在 dom 中但被外部保留的块?(删除了就丢弃)
    onChange(
      next.map((b) => ({
        ...b,
        // 防御:map 中存的是默认值
        type: map.get(b.id)?.type ?? b.type,
      })),
    );
  }, [onChange, value]);

  // 切换块类型
  const setBlockType = (id: string, type: Block["type"]) => {
    onChange(value.map((b) => (b.id === id ? { ...b, type } : b)));
    focusIdRef.current = id;
  };

  // 插入新块
  const insertBlock = (afterId: string | null, type: Block["type"] = "p") => {
    const newBlock: Block = { id: uid(), type, text: "" };
    if (afterId === null) {
      onChange([...value, newBlock]);
    } else {
      const idx = value.findIndex((b) => b.id === afterId);
      if (idx < 0) onChange([...value, newBlock]);
      else onChange([...value.slice(0, idx + 1), newBlock, ...value.slice(idx + 1)]);
    }
    focusIdRef.current = newBlock.id;
  };

  // 监听 keydown:Enter / Backspace / Tab
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const anchor = sel.anchorNode;
    const el = (anchor?.nodeType === 1
      ? (anchor as HTMLElement)
      : (anchor?.parentElement as HTMLElement | null)) as HTMLElement | null;
    const blockEl = el?.closest<HTMLElement>("[data-block-id]");
    if (!blockEl) return;
    const id = blockEl.getAttribute("data-block-id") || "";
    const cur = value.find((b) => b.id === id);

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (cur?.type === "list") {
        // 空 list → 退出列表
        if (!cur.text.trim()) {
          setBlockType(id, "p");
        } else {
          insertBlock(id, "list");
        }
      } else {
        insertBlock(id, cur?.type === "h1" || cur?.type === "h2" ? "p" : "p");
      }
    } else if (e.key === "Backspace") {
      const text = (cur?.text ?? "").trim();
      if (!text) {
        // 空块,删掉并 focus 上一个
        if (value.length > 1) {
          e.preventDefault();
          const idx = value.findIndex((b) => b.id === id);
          const prev = value[idx - 1];
          onChange(value.filter((b) => b.id !== id));
          if (prev) focusIdRef.current = prev.id;
        } else {
          // 唯一一块,转为 p
          e.preventDefault();
          setBlockType(id, "p");
        }
      }
    } else if (e.key === "Tab") {
      e.preventDefault();
      const types: Block["type"][] = ["p", "h1", "h2", "list"];
      const idx = types.indexOf(cur?.type ?? "p");
      const nextType = types[(idx + (e.shiftKey ? -1 : 1) + types.length) % types.length];
      setBlockType(id, nextType);
    }
  };

  // 焦点处理
  React.useEffect(() => {
    const el = editorRef.current;
    if (!el || !focusIdRef.current) return;
    const target = el.querySelector<HTMLElement>(
      `[data-block-id="${focusIdRef.current}"]`,
    );
    if (target) {
      target.focus();
      // 把光标移到末尾
      const range = document.createRange();
      range.selectNodeContents(target);
      range.collapse(false);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      focusIdRef.current = null;
    }
  });

  return (
    <div
      className={cn(
        "group relative rounded-xl border border-slate-200 bg-white shadow-sm transition focus-within:border-blue-300 focus-within:ring-2 focus-within:ring-blue-100",
        disabled && "opacity-60",
      )}
    >
      <div className="flex items-center gap-1 border-b border-slate-100 px-2 py-1.5 text-xs text-slate-500">
        <ToolbarButton
          label="正文"
          active={activeType === "p"}
          onClick={() => activeId && setBlockType(activeId, "p")}
        />
        <ToolbarButton
          label="标题 1"
          active={activeType === "h1"}
          onClick={() => activeId && setBlockType(activeId, "h1")}
        />
        <ToolbarButton
          label="标题 2"
          active={activeType === "h2"}
          onClick={() => activeId && setBlockType(activeId, "h2")}
        />
        <ToolbarButton
          label="• 列表"
          active={activeType === "list"}
          onClick={() => activeId && setBlockType(activeId, "list")}
        />
        <span className="ml-auto text-[10px] text-slate-400">
          Enter 新建 · Shift+Enter 换行 · Tab 切换类型
        </span>
      </div>
      <div
        ref={editorRef}
        role="textbox"
        aria-multiline
        aria-label="日记正文"
        contentEditable={!disabled}
        suppressContentEditableWarning
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        onFocus={(e) => {
          const el = e.currentTarget
            .querySelector<HTMLElement>(
              `[data-block-id]:focus,[data-block-id]:focus-within`,
            )
            ?.closest<HTMLElement>("[data-block-id]");
          const id = el?.getAttribute("data-block-id");
          if (id) setActiveId(id);
        }}
        onKeyUp={() => {
          const id = getActiveIdFromSelection();
          if (id && id !== activeId) setActiveId(id);
        }}
        onClick={() => {
          const id = getActiveIdFromSelection();
          if (id && id !== activeId) setActiveId(id);
        }}
        className="nb-editor min-h-[220px] px-4 py-3 text-sm leading-relaxed text-slate-800 focus:outline-none"
      />
      {value.every((b) => !b.text.trim()) && (
        <p
          aria-hidden
          className="pointer-events-none absolute left-[60px] top-[44px] text-sm text-slate-400"
        >
          写下今天发生了什么 · 什么做得好 · 哪些需要改进…
        </p>
      )}
    </div>
  );
}

function ToolbarButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={cn(
        "rounded px-2 py-0.5 text-[11px] font-medium transition",
        active
          ? "bg-slate-900 text-white"
          : "text-slate-600 hover:bg-slate-100",
      )}
    >
      {label}
    </button>
  );
}

function getActiveIdFromSelection(): string | null {
  if (typeof window === "undefined") return null;
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return null;
  const anchor = sel.anchorNode;
  if (!anchor) return null;
  const el = (anchor.nodeType === 1
    ? (anchor as HTMLElement)
    : (anchor.parentElement as HTMLElement | null)) as HTMLElement | null;
  return el?.closest<HTMLElement>("[data-block-id]")?.getAttribute("data-block-id") ?? null;
}

function escapeHtml(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ---------------------------------------------------------------------------
// 标签评分 + 行动项
// ---------------------------------------------------------------------------

function TagChips<T extends string>({
  options,
  value,
  onChange,
  icon: Icon,
  ariaLabel,
}: {
  options: ReadonlyArray<{ key: T; label: string; emoji?: string }>;
  value: T | null;
  onChange: (v: T) => void;
  icon: React.ComponentType<{ className?: string }>;
  ariaLabel: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label={ariaLabel}>
      <span className="inline-flex items-center gap-1 text-xs text-slate-500">
        <Icon className="size-3.5" />
        {ariaLabel}
      </span>
      {options.map((opt) => {
        const active = value === opt.key;
        return (
          <button
            key={opt.key}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.key)}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs transition",
              active
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50",
            )}
          >
            {opt.emoji && <span aria-hidden>{opt.emoji}</span>}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function ActionItemRow({
  item,
  onCycle,
  onRemove,
}: {
  item: LocalActionItem;
  onCycle: () => void;
  onRemove: () => void;
}) {
  const def =
    ACTION_STATES.find((s) => s.key === item.state) ?? ACTION_STATES[0];
  const Icon = def.icon;
  return (
    <li className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm">
      <button
        type="button"
        onClick={onCycle}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs transition hover:bg-slate-50",
          def.className,
        )}
        aria-label={`切换状态:当前 ${def.label},点击循环到下一个`}
        title={`点击循环状态 (当前: ${def.label})`}
      >
        <Icon className="size-3.5" />
        <span className="font-medium">{def.label}</span>
        <ArrowRight className="size-3 opacity-50" />
      </button>
      <span
        className={cn(
          "flex-1 truncate",
          item.state === "done" && "text-slate-400 line-through",
        )}
      >
        {item.title}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-1 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
        aria-label="删除该行动项"
      >
        <Trash2 className="size-3.5" />
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export default function JournalPage() {
  const [blocks, setBlocks] = React.useState<Block[]>([
    { id: uid(), type: "h1", text: "" },
    { id: uid(), type: "p", text: "" },
  ]);
  const [mood, setMood] = React.useState<MoodTag | null>(null);
  const [energy, setEnergy] = React.useState<EnergyTag | null>(null);
  const [stress, setStress] = React.useState<StressTag | null>(null);
  const [actions, setActions] = React.useState<LocalActionItem[]>([]);
  const [newAction, setNewAction] = React.useState("");

  const [submitting, setSubmitting] = React.useState(false);
  const [latestAI, setLatestAI] = React.useState<{
    rating?: JournalRating;
    advice?: string;
    warnings?: string[];
    action_items?: string[];
    mood_score?: number;
  } | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const [timeline, setTimeline] = React.useState<JournalEntry[]>([]);
  const [loadingTimeline, setLoadingTimeline] = React.useState(true);

  const content = React.useMemo(() => blocksToMarkdown(blocks), [blocks]);
  const canSubmit =
    !submitting && content.trim().length > 0 && (mood || energy || stress);

  const loadTimeline = React.useCallback(async () => {
    setLoadingTimeline(true);
    try {
      const resp = await journalApi.timeline({ days: 30 });
      setTimeline((resp.data ?? []) as JournalEntry[]);
    } catch {
      // 静默失败:展示空态即可
      setTimeline([]);
    } finally {
      setLoadingTimeline(false);
    }
  }, []);

  React.useEffect(() => {
    void loadTimeline();
  }, [loadTimeline]);

  function addAction() {
    const t = newAction.trim();
    if (!t) return;
    setActions((prev) => [
      ...prev,
      { id: uid(), title: t, state: "pending" },
    ]);
    setNewAction("");
  }

  function cycleAction(id: string) {
    setActions((prev) =>
      prev.map((a) => {
        if (a.id !== id) return a;
        const idx = ACTION_STATES.findIndex((s) => s.key === a.state);
        const next = ACTION_STATES[(idx + 1) % ACTION_STATES.length].key;
        return { ...a, state: next };
      }),
    );
  }

  function removeAction(id: string) {
    setActions((prev) => prev.filter((a) => a.id !== id));
  }

  function reset() {
    setBlocks([
      { id: uid(), type: "h1", text: "" },
      { id: uid(), type: "p", text: "" },
    ]);
    setMood(null);
    setEnergy(null);
    setStress(null);
    setActions([]);
    setNewAction("");
    setLatestAI(null);
    setError(null);
  }

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    setLatestAI(null);
    try {
      // mood_score 由标签合成(-1..1),传给后端做归一化
      const moodScore = computeMoodScore(mood, energy, stress);
      const resp = await journalApi.submit({
        content,
        mood_score: moodScore,
      });
      setLatestAI(resp.artifacts ?? {});
      await loadTimeline();
      // 提交后清空内容(保留行动项列表供用户继续调整)
      setBlocks([
        { id: uid(), type: "h1", text: "" },
        { id: uid(), type: "p", text: "" },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100/40">
      <div className="border-b bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="grid size-9 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-blue-500 text-white shadow-sm">
              <BookOpen className="size-4" />
            </span>
            <div>
              <h1 className="text-lg font-semibold text-slate-900">
                工作日记
              </h1>
              <p className="text-xs text-slate-500">
                写下来,智能体会给你更具体的建议
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                (window.location.href = "/jobseeker/journal/voice")
              }
              className="gap-1"
            >
              <Mic className="size-3.5" /> 语音
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                (window.location.href = "/jobseeker/journal/analytics")
              }
              className="gap-1"
            >
              <Sparkles className="size-3.5" /> 分析
            </Button>
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-3xl space-y-5 px-6 py-6">
        {/* 撰写区 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <PenLine className="size-4 text-indigo-500" />
              今日记录
              <Badge variant="outline" className="ml-auto text-[10px]">
                {new Date().toLocaleDateString("zh-CN", {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                  weekday: "short",
                })}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <NotebookEditor
              value={blocks}
              onChange={setBlocks}
              disabled={submitting}
            />

            {/* 标签评分 */}
            <div className="space-y-2 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-3">
              <p className="text-xs font-medium text-slate-600">
                给今天的状态打个标签(选 1-3 个,可选)
              </p>
              <TagChips<MoodTag>
                icon={Zap}
                ariaLabel="心情"
                options={MOOD_TAGS}
                value={mood}
                onChange={setMood}
              />
              <TagChips<EnergyTag>
                icon={CircleDashed}
                ariaLabel="能量"
                options={ENERGY_TAGS}
                value={energy}
                onChange={setEnergy}
              />
              <TagChips<StressTag>
                icon={AlertTriangle}
                ariaLabel="压力"
                options={STRESS_TAGS}
                value={stress}
                onChange={setStress}
              />
            </div>

            {/* 三态行动项 */}
            <div className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="mb-2 flex items-center gap-2">
                <Target className="size-4 text-blue-500" />
                <p className="text-sm font-medium text-slate-700">
                  本次行动项
                </p>
                <Badge variant="secondary" className="ml-auto text-[10px]">
                  {actions.length} 项 · 三态循环
                </Badge>
              </div>
              <ul className="mb-2 space-y-1.5" aria-label="行动项列表">
                {actions.map((a) => (
                  <ActionItemRow
                    key={a.id}
                    item={a}
                    onCycle={() => cycleAction(a.id)}
                    onRemove={() => removeAction(a.id)}
                  />
                ))}
                {actions.length === 0 && (
                  <li className="rounded-lg border border-dashed border-slate-200 px-2.5 py-2 text-center text-xs text-slate-400">
                    先在脑子里列出今天要推进的事,点击行可循环切换 待办 → 进行中 → 已完成
                  </li>
                )}
              </ul>
              <div className="flex gap-1.5">
                <input
                  value={newAction}
                  onChange={(e) => setNewAction(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addAction();
                    }
                  }}
                  placeholder="例如:明早 10 点前完成匹配实验回看"
                  aria-label="新增行动项"
                  className="flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={addAction}
                  disabled={!newAction.trim()}
                  className="gap-1"
                >
                  <Plus className="size-3.5" /> 添加
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <p className="text-xs text-slate-500">
                {content.length} 字 · 至少 1 个标签 + 正文即可提交
              </p>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={reset}>
                  <RotateCcw className="size-3.5" /> 清空
                </Button>
                <Button
                  size="sm"
                  onClick={submit}
                  disabled={!canSubmit}
                  className="gap-1"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="size-3.5 animate-spin" /> AI 思考中…
                    </>
                  ) : (
                    <>
                      <Sparkles className="size-3.5" /> 提交并获取建议
                    </>
                  )}
                </Button>
              </div>
            </div>

            {error && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700"
              >
                <AlertTriangle className="size-3.5" /> {error}
              </div>
            )}
          </CardContent>
        </Card>

        {/* AI 评价 */}
        {latestAI && (
          <AIArtifactCard
            rating={latestAI.rating ?? null}
            advice={latestAI.advice ?? null}
            warnings={latestAI.warnings ?? []}
            actionItems={latestAI.action_items ?? []}
          />
        )}

        {/* 时间线 */}
        <section aria-label="历史日记时间线">
          <header className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-800">
              <BookOpen className="size-4 text-indigo-500" /> 最近 30 天
              <Badge variant="outline" className="text-[10px]">
                {timeline.length} 篇
              </Badge>
            </h2>
          </header>

          {loadingTimeline ? (
            <Card>
              <CardContent className="flex items-center gap-2 py-8 text-sm text-slate-500">
                <Loader2 className="size-4 animate-spin" /> 加载中…
              </CardContent>
            </Card>
          ) : timeline.length === 0 ? (
            <EmptyTimeline />
          ) : (
            <ol className="space-y-3">
              {timeline.map((j) => (
                <TimelineRow key={j.id} entry={j} />
              ))}
            </ol>
          )}
        </section>
      </main>

      {/* Notion-like 块编辑器样式 */}
      <style jsx global>{`
        .nb-editor h1.nb-h1 {
          font-size: 1.5rem;
          font-weight: 600;
          color: #0f172a;
          margin: 4px 0 8px;
          line-height: 1.3;
          outline: none;
        }
        .nb-editor h2.nb-h2 {
          font-size: 1.125rem;
          font-weight: 600;
          color: #1e293b;
          margin: 4px 0 6px;
          line-height: 1.3;
          outline: none;
        }
        .nb-editor p.nb-p {
          margin: 4px 0;
          outline: none;
        }
        .nb-editor p.nb-li {
          display: flex;
          align-items: baseline;
          gap: 6px;
          margin: 2px 0;
        }
        .nb-editor p.nb-li .nb-bullet {
          color: #94a3b8;
        }
        .nb-editor [data-block-id]:empty::before {
          content: "";
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function computeMoodScore(
  mood: MoodTag | null,
  energy: EnergyTag | null,
  stress: StressTag | null,
): number {
  const m: Record<MoodTag, number> = {
    happy: 0.8,
    calm: 0.4,
    focused: 0.5,
    tired: -0.4,
    anxious: -0.6,
    frustrated: -0.7,
  };
  const e: Record<EnergyTag, number> = { high: 0.4, medium: 0, low: -0.3 };
  const s: Record<StressTag, number> = { calm: 0.2, mild: 0, high: -0.4 };
  const arr: number[] = [];
  if (mood) arr.push(m[mood]);
  if (energy) arr.push(e[energy]);
  if (stress) arr.push(s[stress]);
  if (arr.length === 0) return 0;
  return Math.max(-1, Math.min(1, arr.reduce((a, b) => a + b, 0) / arr.length));
}

function AIArtifactCard({
  rating,
  advice,
  warnings,
  actionItems,
}: {
  rating: JournalRating;
  advice: string | null;
  warnings: string[];
  actionItems: string[];
}) {
  const def = RATING_LABEL[rating ?? ""] ?? {
    label: rating || "—",
    tone: "bg-slate-100 text-slate-700",
    ring: "ring-slate-200",
  };
  return (
    <Card
      className={cn("ring-1", def.ring)}
      aria-live="polite"
      aria-label="AI 评价"
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4 text-amber-500" />
          智能体评价
          <span
            className={cn(
              "ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs",
              def.tone,
            )}
          >
            {def.label}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {advice ? (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50/60 px-3 py-2 text-slate-800">
            <Lightbulb className="mt-0.5 size-4 text-amber-500" />
            <p className="whitespace-pre-wrap leading-relaxed">{advice}</p>
          </div>
        ) : (
          <p className="text-xs text-slate-400">智能体没有给出具体建议。</p>
        )}
        {warnings.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium text-rose-700">⚠ 警示</p>
            <ul className="space-y-1 rounded-lg border border-rose-200 bg-rose-50/60 p-2 text-xs text-rose-700">
              {warnings.map((w, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  <span className="whitespace-pre-wrap">{w}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {actionItems.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium text-blue-700">
              🎯 建议行动项
            </p>
            <ul className="space-y-1 rounded-lg border border-blue-200 bg-blue-50/60 p-2 text-xs text-blue-700">
              {actionItems.map((a, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <Target className="mt-0.5 size-3.5 shrink-0" />
                  <span className="whitespace-pre-wrap">{a}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TimelineRow({ entry }: { entry: JournalEntry }) {
  const rating = RATING_LABEL[entry.ai_rating ?? ""] ?? null;
  return (
    <li>
      <Card className="transition hover:shadow-md">
        <CardContent className="space-y-2 py-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <time
              dateTime={entry.journal_date}
              className="font-medium tabular-nums text-slate-700"
            >
              {entry.journal_date}
            </time>
            {entry.mood_score != null && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5">
                {entry.mood_score > 0.3
                  ? "😊"
                  : entry.mood_score < -0.3
                    ? "😔"
                    : "😐"}{" "}
                {entry.mood_score.toFixed(1)}
              </span>
            )}
            {rating && (
              <span
                className={cn(
                  "rounded-full px-2 py-0.5",
                  rating.tone,
                )}
              >
                {rating.label}
              </span>
            )}
          </div>
          <p className="whitespace-pre-wrap text-sm text-slate-800">
            {entry.content}
          </p>
          {entry.ai_advice && (
            <div className="rounded-md border-t border-slate-100 bg-slate-50/60 px-2 py-1.5 text-xs text-slate-600">
              <span className="font-medium text-slate-700">智能体: </span>
              {entry.ai_advice}
            </div>
          )}
        </CardContent>
      </Card>
    </li>
  );
}

function EmptyTimeline() {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
        <span className="grid size-12 place-items-center rounded-full bg-slate-100 text-slate-400">
          <BookOpen className="size-5" />
        </span>
        <p className="text-sm font-medium text-slate-700">
          还没有日记记录
        </p>
        <p className="max-w-sm text-xs text-slate-500">
          写第一篇日记,智能体会从下一次开始给你连贯的反馈和行动建议。
        </p>
      </CardContent>
    </Card>
  );
}

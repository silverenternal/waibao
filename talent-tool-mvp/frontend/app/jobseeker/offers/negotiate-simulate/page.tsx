"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Markdown } from "@/components/shared";

/**
 * v9.1 — /jobseeker/offers/negotiate-simulate — Open WebUI 风谈判模拟
 *
 * 三段式:
 *  1. 顶部 PersonaSelector:选 HR 人格(友好 / 数据 / 强硬)
 *  2. 中间主面板:Open WebUI 风格聊天区
 *     - 左侧:会话侧栏(人格档案 / 场景信息 / 建议论点)
 *     - 中部:消息流(HR 头像 + 气泡 + 时间 + 操作)
 *     - 底部:输入框 + 一键示例 + 场景 chip
 *  3. 模拟 LLM 推理:根据人格 / 场景 / 用户输入生成 HR 回复
 *
 * 可访问:
 *  - 消息区 role="log" aria-live="polite"
 *  - 所有按钮 aria-label,input aria-label
 *  - 焦点环 / 键盘可达
 */

import Link from "next/link";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  Check,
  ChevronRight,
  Copy,
  Hand,
  Lightbulb,
  RefreshCcw,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  User as UserIcon,
  Wand2,
} from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

// ---------- 埋点 ----------
function track(event: string, props?: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  try {
    (window as unknown as { dataLayer: unknown[] }).dataLayer =
      (window as unknown as { dataLayer: unknown[] }).dataLayer || [];
    (window as unknown as { dataLayer: unknown[] }).dataLayer.push({
      event,
      ts: Date.now(),
      ...(props || {}),
    });
    fetch("/api/signals/track", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("sb_token") || ""}`,
      },
      body: JSON.stringify({ event, props: props || {} }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // 静默
  }
}

// ---------- 类型 ----------
interface Persona {
  id: string;
  label: string;
  emoji: string;
  emoji2: string;
  desc: string;
  voice: "温柔" | "专业" | "强势";
  color: string;
  ring: string;
  systemPrompt: string;
  opening: string[];
  reactions: { trigger: RegExp; reply: string }[];
  tips: string[];
}

interface Msg {
  id: string;
  role: "hr" | "you" | "system";
  content: string;
  ts: number;
  persona?: string;
}

// ---------- 常量 ----------
const PERSONAS: Persona[] = [
  {
    id: "warm",
    label: "友好型 HR",
    emoji: "🌸",
    emoji2: "AW",
    desc: "以关系维护为主,常用「我们更希望留住你」",
    voice: "温柔",
    color: "from-rose-100 to-amber-50 border-rose-300",
    ring: "ring-rose-300",
    systemPrompt: "你是一位注重候选人体验的 HR,语气温暖、节奏慢、愿意倾听。",
    opening: [
      "嗨,先恭喜你拿到 offer 啦~我这边是想跟你对齐下细节,有什么顾虑都可以先说。",
      "Hi,我叫 Amy,后续就由我来负责你的整体体验,你有什么想法都可以直接告诉我。",
    ],
    reactions: [
      {
        trigger: /(签字费|signing|签字)/i,
        reply:
          "签字费这块我们能聊,但需要你给我一个具体数,以及为什么这个数是合理的?我得跟 CFO 报一下。",
      },
      {
        trigger: /(股权|equity|vesting|期权)/i,
        reply:
          "股权我是支持的,公司也是希望核心同事长期绑定。要不你先说下你期望的 refresh 节奏?我们一起想办法。",
      },
      {
        trigger: /(底薪|base|月薪|salary|薪资)/i,
        reply:
          "我们给的 base 已经在 band 中上,但我可以再帮你问一下是否可以再 forward 一档,不过得有数据支撑哦。",
      },
    ],
    tips: [
      "用「数据 + 关系」双线表达,对方吃感性也吃理性",
      "多用「我感受到 / 我担心」,少用「你必须」",
    ],
  },
  {
    id: "data",
    label: "数据型 HR",
    emoji: "📊",
    emoji2: "DA",
    desc: "用市场分位 / 职级 band 谈,追求逻辑闭环",
    voice: "专业",
    color: "from-indigo-100 to-blue-50 border-indigo-300",
    ring: "ring-indigo-300",
    systemPrompt: "你是一位严谨的 HR,引用市场数据、band、级别来讨论,拒绝拍脑袋。",
    opening: [
      "你好,我们这边 base 在 p50 附近,bonus 按 20% 算,equity 是 4 年 linear。我先看下你期望的差距来自哪里。",
      "我先给你看下当前 package 在 p50/p75 的位置,再讨论可能调的空间。",
    ],
    reactions: [
      {
        trigger: /(签字费|signing)/i,
        reply:
          "签字费是一次性支出,通常用于弥平对方 offer 差距,我们的上限是 1 个月 base + 现 offer 5%,你 case 的差距是多少?",
      },
      {
        trigger: /(股权|equity|vesting|期权)/i,
        reply:
          "我们 4 年线性、1 年 cliff,如果你能展示市场上同级别 P75 的 equity 数据,我们可以讨论 refresh 时间点。",
      },
      {
        trigger: /(底薪|base|月薪|salary|薪资)/i,
        reply:
          "我可以再 forward 一档,不过需要看你的市场数据(级别 + 城市 + 公司规模),我们一起对一下?",
      },
    ],
    tips: [
      "准备一张表:你的 offer / p50 / p75 / p90,讲数字别讲感受",
      "对方会用 band 限制你,所以问清 band 边界比问数字重要",
    ],
  },
  {
    id: "tough",
    label: "强硬派 HR",
    emoji: "🧱",
    emoji2: "TM",
    desc: "强调预算 / 制度 / 流程,语气直接",
    voice: "强势",
    color: "from-slate-100 to-zinc-50 border-slate-400",
    ring: "ring-slate-400",
    systemPrompt:
      "你是一位强势的 HR,会用公司政策、预算上限、流程时长来拒绝加码,但会给出替代方案。",
    opening: [
      "我们这次的 package 是按 band 定的,没有额外空间。我可以聊聊 non-cash 部分。",
      "我先说下我们的边界:base 不能动,bonus 已锁,equity refresh 要等 12 个月。",
    ],
    reactions: [
      {
        trigger: /(签字费|signing)/i,
        reply:
          "签字费预算今年已经用完,我没法新增。可以考虑的是把 RSU 的第一个 cliff 从 1 年缩到 6 个月,但要 CEO 批。",
      },
      {
        trigger: /(股权|equity|vesting|期权)/i,
        reply:
          "refresh 时间是公司层面定的,我个人没有空间。但是我可以把你放进 H1 review 的优先名单,前提是你入职后表现达到 4+。",
      },
      {
        trigger: /(底薪|base|月薪|salary|薪资)/i,
        reply:
          "我们 base 已经到 band 顶端,任何加码都会影响内部公平性。我能给你的是:title 升级、签字费折中、或者更快的 onboarding bonus。",
      },
    ],
    tips: [
      "不要硬碰硬:把请求拆成多个「低成本让步」让对方点头",
      "如果对方拒绝,立刻问「那在你的边界内,你能给我的是什么?」",
    ],
  },
];

const SCENARIOS = [
  { id: "scenario_a_below_p50", label: "p50 以下", emoji: "📉" },
  { id: "scenario_b_competing_offer", label: "竞争 offer", emoji: "🤝" },
  { id: "scenario_c_signing_bonus", label: "争取签字费", emoji: "💵" },
  { id: "scenario_d_equity_vesting", label: "调整股权", emoji: "📈" },
  { id: "scenario_e_walkaway", label: "走人底线", emoji: "🚪" },
];

const QUICK_REPLIES = [
  "感谢安排时间,我想先确认下 base 还有 forward 空间吗?",
  "我手上有另一家在 p75,愿意出 signing bonus 1.5 个月,你们怎么看?",
  "签字费目前没有,我能接受调整 equity vesting 节奏吗?",
  "如果 base 不动,签字费能加 1 个月吗?",
  "请问在你们边界内,能给我的是什么?",
];

// ---------- 主组件 ----------
function SimulatePageInner() {
  const params = useSearchParams();
  const offerId = params?.get("id") || "";

  const [persona, setPersona] = useState<Persona>(PERSONAS[0]);
  const [scenario, setScenario] = useState<string>(SCENARIOS[0].id);
  const [turns, setTurns] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [hrTyping, setHrTyping] = useState(false);
  const [liked, setLiked] = useState<Record<string, "up" | "down" | undefined>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  // 加载 offer 信息(轻量)
  const [offer, setOffer] = useState<{
    title?: string;
    company?: string;
    currency?: string;
    base_salary?: number;
  } | null>(null);
  useEffect(() => {
    if (!offerId) return;
    track("simulate_page_view", { offer_id: offerId });
    const token = localStorage.getItem("sb_token") || "";
    fetch(`/api/offers/${offerId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setOffer(d.offer))
      .catch(() => undefined);
  }, [offerId]);

  // 派生 seed(系统提示 + HR 开场) — 跟随 persona / scenario 自动重算
  const seed = useMemo<Msg[]>(() => {
    const sysId = `sys-${persona.id}-${scenario}`;
    const hrId = `hr-${persona.id}-${scenario}`;
    return [
      {
        id: sysId,
        role: "system" as const,
        content: `会话已就绪 · 人格:${persona.label} · 场景:${
          SCENARIOS.find((s) => s.id === scenario)?.label ?? scenario
        }`,
        ts: 0,
      },
      {
        id: hrId,
        role: "hr" as const,
        content: persona.opening[0],
        ts: 1,
        persona: persona.id,
      },
    ];
  }, [persona, scenario]);

  // 清空 turns 由「重新开始」按钮显式触发,不在 effect 里 setState
  const resetConversation = useCallback(() => {
    setTurns([]);
    setLiked({});
    setInput("");
    track("simulate_reset", { persona: persona.id, scenario });
  }, [persona, scenario]);

  const msgs = useMemo<Msg[]>(() => [...seed, ...turns], [seed, turns]);

  // 滚动到底部
  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [msgs, hrTyping]);

  // 模拟 LLM 推理
  const hrReply = useCallback(
    (userText: string, p: Persona): string => {
      const trimmed = userText.trim();
      if (!trimmed) return "请说点什么吧~";

      // 关键词匹配
      for (const r of p.reactions) {
        if (r.trigger.test(trimmed)) return r.reply;
      }

      // 走人 / 终止
      if (/(走|不接|拒|walk|reject|放弃)/i.test(trimmed)) {
        return p.id === "tough"
          ? "OK,我尊重你的决定。我们会留 record,如果你之后改变主意欢迎再联系。"
          : p.id === "data"
            ? "完全理解。这是一份 offer,不存在必须接受的压力。如果 48h 内需要再聊,我都在。"
            : "听到你说要放弃,我有点遗憾。要不我再帮你过一遍 package,看看有没有我们没聊到的点?";
      }

      // 默认回复
      const defaults: Record<string, string[]> = {
        warm: [
          "我懂你的意思,要不我们一项一项过?你觉得哪个点对你最关键?",
          "我们这边其实挺希望你加入的,愿不愿意告诉我你的具体期望数字?",
        ],
        data: [
          "可以,但需要你提供 benchmark 源(level / 城市 / 同期样本数),我们用同口径对一下。",
          "合理的诉求我可以带回 compensation committee,但需要 1 周内给你回复。",
        ],
        tough: [
          "在我们政策范围内,这个暂时没有空间。如果一定要动 base,我需要你给一个 explicit 理由。",
          "我明白你的诉求,但内部公平性是硬约束,我们可以谈 title / refresh 时间点。",
        ],
      };
      const list = defaults[p.id] || defaults.warm;
      return list[Math.floor(Math.random() * list.length)];
    },
    []
  );

  const send = useCallback(
    (text?: string) => {
      const value = (text ?? input).trim();
      if (!value) return;
      const youMsg: Msg = {
        id: `you-${Date.now()}`,
        role: "you",
        content: value,
        ts: Date.now(),
      };
      setTurns((m) => [...m, youMsg]);
      setInput("");
      setHrTyping(true);
      track("simulate_user_send", {
        persona: persona.id,
        scenario,
        length: value.length,
      });
      // 模拟思考 + 打字
      const think = 600 + Math.random() * 700;
      setTimeout(() => {
        const reply = hrReply(value, persona);
        const hrMsg: Msg = {
          id: `hr-${Date.now()}`,
          role: "hr",
          content: reply,
          ts: Date.now(),
          persona: persona.id,
        };
        setTurns((m) => [...m, hrMsg]);
        setHrTyping(false);
        track("simulate_hr_reply", { persona: persona.id, scenario });
      }, think);
    },
    [hrReply, input, persona, scenario]
  );

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    },
    [send]
  );

  const copyMsg = useCallback(async (m: Msg) => {
    try {
      await navigator.clipboard.writeText(m.content);
      setCopiedId(m.id);
      setTimeout(() => setCopiedId(null), 1200);
    } catch {
      // ignore
    }
  }, []);

  const regenerate = useCallback(() => {
    // 从 turns 中找到最近一对 you+hr,移除 hr 让它重新生成
    const idx = [...turns].reverse().findIndex((m) => m.role === "hr");
    if (idx === -1) return;
    const realIdx = turns.length - 1 - idx;
    const you = turns[realIdx - 1];
    if (!you || you.role !== "you") return;
    const newSlice = turns.slice(0, realIdx);
    setTurns(newSlice);
    setHrTyping(true);
    setTimeout(() => {
      const reply = hrReply(you.content, persona);
      setTurns((m) => [
        ...m,
        {
          id: `hr-${Date.now()}`,
          role: "hr",
          content: reply,
          ts: Date.now(),
          persona: persona.id,
        },
      ]);
      setHrTyping(false);
    }, 700);
  }, [turns, hrReply, persona]);

  const meta = useMemo(() => {
    return {
      totalTurns: msgs.filter((m) => m.role === "you").length,
      lastTopic: msgs.filter((m) => m.role === "hr").slice(-1)[0]?.content.slice(0, 40),
    };
  }, [msgs]);

  return (
    <div className="flex h-screen flex-col bg-gradient-to-b from-slate-50 via-white to-sky-50/30">
      <a
        href="#chat-input"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:rounded focus:bg-sky-600 focus:px-3 focus:py-1.5 focus:text-white"
      >
        跳到输入框
      </a>

      {/* 顶栏 */}
      <header className="border-b border-slate-200 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon-sm" asChild aria-label="返回谈判脚本">
              <Link href={`/jobseeker/offers/negotiate${offerId ? `?id=${offerId}` : ""}`}>
                <ArrowLeft className="size-4" />
              </Link>
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-base font-semibold text-slate-900">
                <Wand2 className="size-4 text-sky-600" aria-hidden /> 谈判模拟器
                <Badge variant="secondary" className="rounded-full text-[10px]">
                  v9.1
                </Badge>
              </h1>
              <p className="text-[11px] text-slate-500">
                PersonaSelector + Open WebUI 风聊天 · 模拟 LLM 推理
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="rounded-full bg-slate-100 px-2 py-0.5">
              已对话 {meta.totalTurns} 轮
            </span>
            {offer && (
              <span className="hidden rounded-full bg-sky-50 px-2 py-0.5 text-sky-700 sm:inline">
                {offer.title} · {offer.currency}
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={resetConversation}
              data-testid="reset-conversation"
              aria-label="重新开始对话"
            >
              <RefreshCcw className="mr-1.5 size-3.5" /> 重新开始
            </Button>
          </div>
        </div>
      </header>

      {/* PersonaSelector */}
      <section
        aria-label="HR 人格选择"
        className="border-b border-slate-200 bg-white/60 px-4 py-3 sm:px-6"
      >
        <div className="mx-auto flex max-w-7xl flex-col gap-3">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 text-sky-500" aria-hidden />
            <h2 className="text-xs font-semibold tracking-wider text-slate-600 uppercase">
              PersonaSelector · 选一位 HR 开始
            </h2>
          </div>
          <div
            className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3"
            role="radiogroup"
            aria-label="HR 人格"
          >
            {PERSONAS.map((p) => {
              const active = persona.id === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => {
                    setPersona(p);
                    track("simulate_persona_change", { persona: p.id });
                  }}
                  data-testid={`persona-${p.id}`}
                  className={cn(
                    "rounded-2xl border-2 bg-gradient-to-br p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400",
                    p.color,
                    active && `ring-2 ring-offset-2 ${p.ring}`
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-2xl" aria-hidden>
                      {p.emoji}
                    </span>
                    <div className="font-semibold text-slate-800">{p.label}</div>
                    <Badge variant="secondary" className="ml-auto rounded-full text-[10px]">
                      {p.voice}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">{p.desc}</p>
                </button>
              );
            })}
          </div>

          {/* 场景选择 */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">谈判场景:</span>
            <div
              className="flex flex-wrap gap-1.5"
              role="radiogroup"
              aria-label="谈判场景"
            >
              {SCENARIOS.map((s) => {
                const active = scenario === s.id;
                return (
                  <button
                    key={s.id}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => {
                      setScenario(s.id);
                      track("simulate_scenario_change", { scenario: s.id });
                    }}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-[11px] transition",
                      active
                        ? "border-sky-500 bg-sky-50 text-sky-700"
                        : "border-slate-200 bg-white text-slate-500 hover:border-slate-400"
                    )}
                  >
                    <span className="mr-1" aria-hidden>
                      {s.emoji}
                    </span>
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* 主区:Open WebUI 风 2 栏 */}
      <div className="mx-auto grid w-full max-w-7xl flex-1 gap-0 overflow-hidden lg:grid-cols-[280px_1fr]">
        {/* 侧栏 */}
        <aside
          aria-label="会话详情"
          className="hidden overflow-y-auto border-r border-slate-200 bg-white/60 p-4 lg:block"
        >
          <Card className="mb-3 overflow-hidden">
            <div
              className={cn(
                "border-b bg-gradient-to-br p-4",
                persona.color
              )}
            >
              <div className="flex items-center gap-3">
                <Avatar className="size-12 ring-2 ring-white">
                  <AvatarFallback className="bg-white text-base font-semibold text-slate-700">
                    {persona.emoji2}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <div className="text-sm font-semibold text-slate-800">
                    {persona.label}
                  </div>
                  <div className="text-[11px] text-slate-600">
                    语气:{persona.voice}
                  </div>
                </div>
              </div>
            </div>
            <CardContent className="space-y-2 p-3 text-xs text-slate-600">
              <p>{persona.desc}</p>
              <div className="rounded-lg bg-slate-50 p-2 text-[11px] leading-relaxed text-slate-500">
                <span className="font-medium text-slate-600">系统提示:</span>
                {persona.systemPrompt}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-2 p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                <Lightbulb className="size-3.5 text-amber-500" /> 谈判建议
              </div>
              <ul className="space-y-1.5 text-xs text-slate-600">
                {persona.tips.map((t, i) => (
                  <li key={i} className="flex gap-1.5">
                    <ChevronRight className="mt-0.5 size-3 shrink-0 text-slate-400" />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card className="mt-3">
            <CardContent className="space-y-2 p-3 text-xs">
              <div className="flex items-center gap-1.5 font-semibold text-slate-700">
                <Hand className="size-3.5 text-sky-500" /> 一键示例
              </div>
              <div className="space-y-1.5">
                {QUICK_REPLIES.map((q, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => send(q)}
                    className="block w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-left text-[11px] text-slate-600 transition hover:border-sky-300 hover:bg-sky-50 hover:text-sky-700"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </aside>

        {/* 聊天主区 */}
        <section className="flex h-full min-h-0 flex-col">
          <div
            ref={listRef}
            role="log"
            aria-live="polite"
            aria-label="对话消息"
            className="flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-8"
          >
            {msgs.map((m) => (
              <MessageBubble
                key={m.id}
                msg={m}
                persona={persona}
                liked={liked[m.id]}
                copied={copiedId === m.id}
                onCopy={() => copyMsg(m)}
                onLike={(v) => {
                  setLiked((s) => ({ ...s, [m.id]: v }));
                  track("simulate_msg_react", {
                    msg_id: m.id,
                    reaction: v,
                    persona: persona.id,
                  });
                }}
                onRegenerate={
                  m.role === "hr" && m === msgs[msgs.length - 1]
                    ? regenerate
                    : undefined
                }
              />
            ))}
            {hrTyping && (
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <Avatar className="size-6">
                  <AvatarFallback className="bg-slate-200 text-[10px] text-slate-600">
                    {persona.emoji2}
                  </AvatarFallback>
                </Avatar>
                <div className="flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1.5">
                  <Dot delay="0s" />
                  <Dot delay="0.15s" />
                  <Dot delay="0.3s" />
                  <span className="ml-1">{persona.label} 正在输入…</span>
                </div>
              </div>
            )}
          </div>

          {/* 输入区 */}
          <div
            id="chat-input"
            className="border-t border-slate-200 bg-white/85 px-4 py-3 backdrop-blur sm:px-8"
          >
            <div className="mx-auto flex max-w-3xl flex-col gap-2">
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>
                  你正在和
                  <span className="mx-1 font-medium text-slate-700">
                    {persona.label}
                  </span>
                  沟通 ·{" "}
                  <span className="text-slate-500">
                    场景 {SCENARIOS.find((s) => s.id === scenario)?.label}
                  </span>
                </span>
                <span className="hidden sm:inline">Enter 发送 · Shift+Enter 换行</span>
              </div>
              <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm focus-within:border-sky-400 focus-within:ring-2 focus-within:ring-sky-100">
                <Textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={1}
                  aria-label="你的回复"
                  placeholder="输入你想对 HR 说的话,例如:我想再聊一下签字费…"
                  className="min-h-9 flex-1 resize-none border-0 bg-transparent px-2 py-1.5 text-sm shadow-none focus-visible:ring-0"
                />
                <Button
                  size="sm"
                  onClick={() => send()}
                  disabled={!input.trim() || hrTyping}
                  data-testid="send-btn"
                  aria-label="发送"
                  className="rounded-xl"
                >
                  <Send className="mr-1.5 size-3.5" /> 发送
                </Button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

// ---------- 消息气泡(Open WebUI 风格) ----------
function MessageBubble({
  msg,
  persona,
  liked,
  copied,
  onCopy,
  onLike,
  onRegenerate,
}: {
  msg: Msg;
  persona: Persona;
  liked?: "up" | "down";
  copied?: boolean;
  onCopy: () => void;
  onLike: (v: "up" | "down") => void;
  onRegenerate?: () => void;
}) {
  if (msg.role === "system") {
    return (
      <div
        className="mx-auto max-w-md rounded-full bg-slate-100 px-3 py-1 text-center text-[11px] text-slate-500"
        role="status"
      >
        {msg.content}
      </div>
    );
  }
  const isYou = msg.role === "you";
  const time = new Date(msg.ts).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <article
      className={cn("group flex gap-3", isYou && "flex-row-reverse")}
      aria-label={isYou ? "你的消息" : "HR 回复"}
    >
      <Avatar className="size-9 shrink-0 ring-2 ring-white">
        <AvatarFallback
          className={cn(
            "text-xs font-semibold",
            isYou ? "bg-sky-100 text-sky-700" : "bg-slate-200 text-slate-700"
          )}
        >
          {isYou ? <UserIcon className="size-4" /> : persona.emoji2}
        </AvatarFallback>
      </Avatar>
      <div
        className={cn(
          "flex max-w-[85%] flex-col",
          isYou ? "items-end" : "items-start"
        )}
      >
        <div className="mb-0.5 flex items-center gap-1.5 text-[10px] text-slate-400">
          <span className="font-medium text-slate-600">
            {isYou ? "你" : persona.label}
          </span>
          {!isYou && (
            <Badge variant="secondary" className="rounded-full px-1.5 py-0 text-[9px]">
              <Bot className="mr-0.5 size-2.5" /> AI
            </Badge>
          )}
          <time>{time}</time>
        </div>
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm",
            isYou
              ? "rounded-tr-sm bg-sky-600 text-white"
              : "rounded-tl-sm border border-slate-200 bg-white text-slate-800"
          )}
        >
          {isYou ? msg.content : <Markdown size="sm">{msg.content}</Markdown>}
        </div>
        {!isYou && (
          <div
            className="mt-1 flex items-center gap-0.5 opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100"
            role="toolbar"
            aria-label="消息操作"
          >
            <Button
              size="icon-xs"
              variant="ghost"
              aria-label="复制"
              onClick={onCopy}
            >
              {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
            </Button>
            <Button
              size="icon-xs"
              variant={liked === "up" ? "secondary" : "ghost"}
              aria-label="点赞"
              aria-pressed={liked === "up"}
              onClick={() => onLike("up")}
            >
              <ThumbsUp className="size-3" />
            </Button>
            <Button
              size="icon-xs"
              variant={liked === "down" ? "secondary" : "ghost"}
              aria-label="点踩"
              aria-pressed={liked === "down"}
              onClick={() => onLike("down")}
            >
              <ThumbsDown className="size-3" />
            </Button>
            {onRegenerate && (
              <Button
                size="icon-xs"
                variant="ghost"
                aria-label="重新生成"
                onClick={onRegenerate}
              >
                <RefreshCcw className="size-3" />
              </Button>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="inline-block size-1.5 animate-bounce rounded-full bg-slate-400"
      style={{ animationDelay: delay }}
      aria-hidden
    />
  );
}

// ---------- Suspense 包裹 ----------
export default function NegotiateSimulatePage() {
  return (
    <ErrorBoundary>(<Suspense fallback={<div className="p-8 text-slate-400">加载中…</div>}>
        <SimulatePageInner />
      </Suspense>)</ErrorBoundary>
  );
}

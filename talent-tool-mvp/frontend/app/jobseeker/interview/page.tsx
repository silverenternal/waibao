"use client";

/**
 * /jobseeker/interview — v9.1 面试中心
 *
 * 单一入口整合:
 *   - 安排中的面试(in_progress / 未开始的 LiveKit 房间)
 *   - 历史面试(已完成,带报告)
 *   - 角色练习入口(跳到 /jobseeker/interview-prep/[role_id])
 *   - 一键开启新的 AI 模拟面试(人格 + 岗位 + 难度)
 *
 * 数据来源:localStorage(本地保存用户开启的 interview 列表与报告),
 * 兼容 Supabase 持久化但前端不强制依赖。
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import InterviewPersonaPicker from "@/components/interview/InterviewPersonaPicker";

type Status = "scheduled" | "in_progress" | "finished" | "abandoned";

interface StoredInterview {
  id: string;
  role: string;
  role_label: string;
  difficulty: string;
  persona_id: string;
  persona_label: string;
  status: Status;
  started_at: string;
  finished_at?: string;
  scheduled_for?: string;
  total_questions?: number;
  answered_count?: number;
  overall_score?: number;
  recommendation?: string;
  report?: {
    overall_score: number;
    recommendation: string;
    summary: string;
    radar: Record<string, number>;
  };
  has_livekit?: boolean;
}

const STORAGE_KEY = "waibao_interviews_v1";

const ROLE_OPTIONS = [
  { value: "backend_engineer", label: "后端工程师", icon: "🛠" },
  { value: "frontend_engineer", label: "前端工程师", icon: "🎨" },
  { value: "fullstack_engineer", label: "全栈工程师", icon: "🧱" },
  { value: "mobile_engineer", label: "移动端工程师", icon: "📱" },
  { value: "data_engineer", label: "数据工程师", icon: "🗄" },
  { value: "data_scientist", label: "数据科学家", icon: "📊" },
  { value: "product_manager", label: "产品经理", icon: "🧭" },
  { value: "designer", label: "设计师", icon: "✏️" },
  { value: "marketing", label: "市场", icon: "📣" },
  { value: "sales", label: "销售", icon: "🤝" },
];

const DIFFICULTY = [
  { value: "junior", label: "初中级" },
  { value: "mid", label: "中级" },
  { value: "senior", label: "高级" },
  { value: "lead", label: "资深/Lead" },
];

const STATUS_META: Record<Status, { label: string; tone: string }> = {
  scheduled: { label: "已安排", tone: "bg-sky-100 text-sky-700" },
  in_progress: { label: "进行中", tone: "bg-amber-100 text-amber-700" },
  finished: { label: "已完成", tone: "bg-emerald-100 text-emerald-700" },
  abandoned: { label: "已退出", tone: "bg-slate-200 text-slate-600" },
};

const RECOMMENDATION_LABEL: Record<string, string> = {
  strong_yes: "强烈推荐",
  yes: "推荐",
  consider: "待定",
  no: "不推荐",
};

type Tab = "scheduled" | "history" | "practice";

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function loadInterviews(): StoredInterview[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function saveInterviews(items: StoredInterview[]) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* ignore quota errors */
  }
}

function scheduleDemo(): StoredInterview[] {
  // 首次访问写入 1 条"已安排"演示数据,让 UI 立即有内容可看
  const now = new Date();
  const future = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  return [
    {
      id: "iv_demo_001",
      role: "backend_engineer",
      role_label: "后端工程师",
      difficulty: "senior",
      persona_id: "rigorous_strict",
      persona_label: "严谨 · 学术派",
      status: "scheduled",
      started_at: now.toISOString(),
      scheduled_for: future.toISOString(),
      total_questions: 12,
      answered_count: 0,
      has_livekit: true,
    },
  ];
}

export default function InterviewHubPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("scheduled");
  const [items, setItems] = useState<StoredInterview[]>([]);
  const [hydrated, setHydrated] = useState(false);

  // 新建面试的折叠态
  const [showNew, setShowNew] = useState(false);
  const [role, setRole] = useState("backend_engineer");
  const [difficulty, setDifficulty] = useState("mid");
  const [personaId, setPersonaId] = useState("friendly_warm");
  const [realtime, setRealtime] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 客户端 hydration + 拉取
  useEffect(() => {
    setHydrated(true);
    let list = loadInterviews();
    if (list.length === 0) {
      list = scheduleDemo();
      saveInterviews(list);
    }
    setItems(list);
  }, []);

  const scheduledItems = useMemo(
    () => items.filter((it) => it.status === "scheduled" || it.status === "in_progress"),
    [items],
  );
  const historyItems = useMemo(
    () =>
      items
        .filter((it) => it.status === "finished" || it.status === "abandoned")
        .sort((a, b) => (b.finished_at || b.started_at).localeCompare(a.finished_at || a.started_at)),
    [items],
  );

  const upsert = useCallback((next: StoredInterview) => {
    setItems((prev) => {
      const idx = prev.findIndex((p) => p.id === next.id);
      const merged = idx >= 0 ? prev.map((p, i) => (i === idx ? { ...p, ...next } : p)) : [next, ...prev];
      saveInterviews(merged);
      return merged;
    });
  }, []);

  async function startInterview() {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("sb_token") || "";
      const r = await fetch("/api/ai-interview-v2/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          role,
          role_label: ROLE_OPTIONS.find((rr) => rr.value === role)?.label || role,
          difficulty,
          persona_id: personaId,
          realtime,
        }),
      });
      if (!r.ok) {
        throw new Error((await r.text()) || `HTTP ${r.status}`);
      }
      const data = await r.json();
      const persona = data.persona || { id: personaId, label: personaId };
      const record: StoredInterview = {
        id: data.id,
        role: data.role || role,
        role_label: data.role_label || role,
        difficulty: data.difficulty || difficulty,
        persona_id: persona.id || personaId,
        persona_label: persona.label || personaId,
        status: "in_progress",
        started_at: new Date().toISOString(),
        total_questions: data.total_questions,
        answered_count: 0,
        has_livekit: !!data.livekit,
      };
      try {
        sessionStorage.setItem(
          `interview_${data.id}`,
          JSON.stringify({
            id: data.id,
            persona,
            role: data.role,
            role_label: data.role_label,
            total_questions: data.total_questions,
            stages: data.stages,
          }),
        );
      } catch {
        /* ignore */
      }
      upsert(record);
      router.push(`/jobseeker/interview/ai/${data.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "启动面试失败,请稍后再试");
    } finally {
      setLoading(false);
    }
  }

  function abandonInterview(id: string) {
    setItems((prev) => {
      const next = prev.map((p) =>
        p.id === id
          ? { ...p, status: "abandoned" as Status, finished_at: new Date().toISOString() }
          : p,
      );
      saveInterviews(next);
      return next;
    });
  }

  function removeInterview(id: string) {
    setItems((prev) => {
      const next = prev.filter((p) => p.id !== id);
      saveInterviews(next);
      return next;
    });
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b">
        <div className="max-w-6xl mx-auto px-6 py-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <span aria-hidden>🎯</span> 面试中心
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              集中查看 AI 模拟面试安排、回顾历史报告、进入岗位准备练习。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/jobseeker/dashboard"
              className="text-sm text-slate-500 hover:text-slate-700"
              aria-label="返回个人中心"
            >
              ← 个人中心
            </Link>
            <button
              onClick={() => setShowNew((v) => !v)}
              className="px-4 py-2 text-sm rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 text-white font-medium shadow-sm hover:shadow"
              data-testid="toggle-new-interview"
              aria-expanded={showNew}
              aria-controls="new-interview-panel"
            >
              {showNew ? "收起新建" : "+ 开始新面试"}
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">
        {/* 新建面试面板 */}
        {showNew && (
          <section
            id="new-interview-panel"
            className="bg-white rounded-2xl shadow-sm p-6 space-y-5"
            aria-label="新建 AI 模拟面试"
          >
            <h2 className="text-base font-semibold text-slate-800">新建一场 AI 模拟面试</h2>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-slate-700">第 1 步 · 选择面试官人格</h3>
              <InterviewPersonaPicker selected={personaId} onSelect={setPersonaId} />
            </div>

            <div className="grid md:grid-cols-2 gap-5">
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-slate-700">第 2 步 · 选择岗位</h3>
                <div className="grid grid-cols-2 gap-2" data-testid="role-grid">
                  {ROLE_OPTIONS.map((r) => (
                    <button
                      key={r.value}
                      type="button"
                      onClick={() => setRole(r.value)}
                      aria-pressed={role === r.value}
                      className={`px-3 py-2 text-sm rounded-lg border text-left transition ${
                        role === r.value
                          ? "border-sky-500 bg-sky-50 text-sky-700"
                          : "border-slate-200 hover:border-slate-400"
                      }`}
                    >
                      <span className="mr-1" aria-hidden>
                        {r.icon}
                      </span>
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <h3 className="text-sm font-medium text-slate-700">第 3 步 · 难度 + 模式</h3>
                <div className="flex gap-2 flex-wrap" data-testid="difficulty-row">
                  {DIFFICULTY.map((d) => (
                    <button
                      key={d.value}
                      type="button"
                      onClick={() => setDifficulty(d.value)}
                      aria-pressed={difficulty === d.value}
                      className={`px-3 py-1.5 text-xs rounded-full border ${
                        difficulty === d.value
                          ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                          : "border-slate-200 hover:border-slate-400"
                      }`}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
                <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={realtime}
                    onChange={(e) => setRealtime(e.target.checked)}
                    className="rounded"
                    data-testid="realtime-toggle"
                  />
                  启用 GPT-4o Realtime 语音对话
                </label>
                <p className="text-xs text-slate-500 leading-relaxed">
                  启用后,候选人可以通过麦克风与 AI 面试官实时对话。文本回答仍可作为兜底。
                </p>
              </div>
            </div>

            {error && (
              <div
                className="bg-rose-50 text-rose-700 text-sm rounded p-3"
                role="alert"
                data-testid="start-error"
              >
                {error}
              </div>
            )}

            <button
              onClick={startInterview}
              disabled={loading}
              data-testid="start-interview"
              className="w-full px-6 py-3 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 text-white font-medium disabled:opacity-50"
            >
              {loading ? "准备面试中…" : "开始面试"}
            </button>
          </section>
        )}

        {/* Tabs */}
        <nav
          className="bg-white rounded-2xl shadow-sm p-1 inline-flex"
          role="tablist"
          aria-label="面试视图切换"
        >
          {([
            { id: "scheduled", label: `待面试 (${scheduledItems.length})` },
            { id: "history", label: `历史回顾 (${historyItems.length})` },
            { id: "practice", label: "角色练习" },
          ] as { id: Tab; label: string }[]).map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm rounded-xl transition ${
                tab === t.id ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div
          id={`panel-${tab}`}
          role="tabpanel"
          aria-labelledby={`tab-${tab}`}
          className="space-y-4"
        >
          {tab === "scheduled" && (
            <>
              {!hydrated && <ListSkeleton count={2} />}
              {hydrated && scheduledItems.length === 0 && (
                <EmptyHint
                  title="还没有待面试"
                  description="点击右上角“开始新面试”,5 分钟内即可开启第一场。"
                />
              )}
              {hydrated &&
                scheduledItems.map((it) => (
                  <ScheduledCard
                    key={it.id}
                    item={it}
                    onEnter={() => router.push(`/jobseeker/interview/ai/${it.id}`)}
                    onAbandon={() => abandonInterview(it.id)}
                  />
                ))}
            </>
          )}

          {tab === "history" && (
            <>
              {!hydrated && <ListSkeleton count={2} />}
              {hydrated && historyItems.length === 0 && (
                <EmptyHint
                  title="还没有历史面试"
                  description="完成第一场 AI 模拟面试后,这里会自动生成报告卡片。"
                />
              )}
              {hydrated &&
                historyItems.map((it) => (
                  <HistoryCard
                    key={it.id}
                    item={it}
                    onEnter={() => router.push(`/jobseeker/interview/ai/${it.id}`)}
                    onRemove={() => removeInterview(it.id)}
                  />
                ))}
            </>
          )}

          {tab === "practice" && (
            <section className="space-y-3">
              <p className="text-sm text-slate-600 leading-relaxed">
                按岗位选择 10 道高频准备题,逐题用文字或语音回答,完成后生成个人反馈报告。
              </p>
              <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {ROLE_OPTIONS.map((r) => (
                  <li key={r.value}>
                    <Link
                      href={`/jobseeker/interview-prep/${r.value}`}
                      className="block bg-white border border-slate-200 rounded-2xl p-4 hover:border-sky-400 hover:shadow-sm transition"
                      data-testid={`prep-${r.value}`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-2xl" aria-hidden>
                          {r.icon}
                        </span>
                        <span className="font-medium text-slate-800">{r.label}</span>
                        <span className="ml-auto text-xs text-sky-600">进入 →</span>
                      </div>
                      <p className="mt-2 text-xs text-slate-500 leading-relaxed">
                        10 题 · 文字 / 语音 / 反馈报告
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 卡片子组件                                                          */
/* ------------------------------------------------------------------ */

function ScheduledCard({
  item,
  onEnter,
  onAbandon,
}: {
  item: StoredInterview;
  onEnter: () => void;
  onAbandon: () => void;
}) {
  return (
    <article
      className="bg-white rounded-2xl shadow-sm p-5 flex flex-wrap items-center gap-4"
      data-testid={`scheduled-card-${item.id}`}
    >
      <div
        className="size-12 rounded-xl bg-sky-100 text-sky-700 flex items-center justify-center text-xl"
        aria-hidden
      >
        🤖
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-semibold text-slate-900 truncate">
            {item.role_label} · {item.persona_label}
          </h3>
          <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_META[item.status].tone}`}>
            {STATUS_META[item.status].label}
          </span>
          {item.has_livekit && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-violet-100 text-violet-700">
              📹 LiveKit
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 mt-1">
          难度 {item.difficulty} · 创建于 {formatDate(item.started_at)}
          {item.scheduled_for && ` · 计划于 ${formatDate(item.scheduled_for)}`}
        </p>
        {typeof item.answered_count === "number" && item.total_questions ? (
          <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-sky-500"
              style={{
                width: `${Math.min(100, (item.answered_count / item.total_questions) * 100)}%`,
              }}
            />
          </div>
        ) : null}
      </div>
      <div className="flex gap-2">
        <button
          onClick={onAbandon}
          className="px-3 py-1.5 text-xs rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200"
          data-testid={`abandon-${item.id}`}
        >
          取消
        </button>
        <button
          onClick={onEnter}
          className="px-4 py-1.5 text-sm rounded-lg bg-sky-600 text-white hover:bg-sky-700"
          data-testid={`enter-${item.id}`}
        >
          {item.status === "in_progress" ? "继续面试" : "进入面试"}
        </button>
      </div>
    </article>
  );
}

function HistoryCard({
  item,
  onEnter,
  onRemove,
}: {
  item: StoredInterview;
  onEnter: () => void;
  onRemove: () => void;
}) {
  const rec = item.report?.recommendation || item.recommendation;
  const score = item.report?.overall_score ?? item.overall_score;
  return (
    <article
      className="bg-white rounded-2xl shadow-sm p-5 flex flex-wrap items-center gap-4"
      data-testid={`history-card-${item.id}`}
    >
      <div
        className="size-12 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center text-xl"
        aria-hidden
      >
        📊
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-semibold text-slate-900 truncate">
            {item.role_label} · {item.persona_label}
          </h3>
          <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_META[item.status].tone}`}>
            {STATUS_META[item.status].label}
          </span>
          {typeof score === "number" && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700">
              综合 {score.toFixed(1)} 分
            </span>
          )}
          {rec && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-sky-50 text-sky-700">
              {RECOMMENDATION_LABEL[rec] || rec}
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 mt-1">
          完成于 {formatDate(item.finished_at || item.started_at)} · 难度 {item.difficulty}
        </p>
        {item.report?.summary && (
          <p className="mt-1 text-xs text-slate-600 line-clamp-2">{item.report.summary}</p>
        )}
      </div>
      <div className="flex gap-2">
        <button
          onClick={onRemove}
          className="px-3 py-1.5 text-xs rounded-lg bg-slate-100 text-slate-500 hover:bg-slate-200"
          aria-label="删除历史"
        >
          删除
        </button>
        <button
          onClick={onEnter}
          className="px-4 py-1.5 text-sm rounded-lg bg-slate-900 text-white hover:bg-slate-700"
          data-testid={`view-report-${item.id}`}
        >
          查看报告
        </button>
      </div>
    </article>
  );
}

function EmptyHint({ title, description }: { title: string; description: string }) {
  return (
    <div className="bg-white border border-dashed border-slate-200 rounded-2xl p-10 text-center">
      <div className="text-3xl mb-2" aria-hidden>
        🗂
      </div>
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      <p className="mt-1 text-xs text-slate-500 max-w-sm mx-auto">{description}</p>
    </div>
  );
}

function ListSkeleton({ count }: { count: number }) {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="h-20 rounded-2xl bg-slate-100 animate-pulse"
          data-testid={`skeleton-${i}`}
        />
      ))}
    </div>
  );
}

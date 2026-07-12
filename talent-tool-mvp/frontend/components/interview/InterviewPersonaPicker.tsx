"use client";

/**
 * InterviewPersonaPicker — T2202.
 *
 * UI for selecting one of 5 personas before starting an interview.
 * Fetches /api/ai-interview-v2/personas to render the list dynamically.
 */

import { useEffect, useState } from "react";

export interface PersonaItem {
  id: string;
  label: string;
  description: string;
  voice: string;
  temperature: number;
  tags: string[];
  weights: Record<string, number>;
}

interface Props {
  selected: string;
  onSelect: (id: string) => void;
}

const PERSONA_ICONS: Record<string, string> = {
  friendly_warm: "🌸",
  rigorous_strict: "📐",
  challenging_pressure: "🔥",
  senior_experienced: "🧭",
  tech_expert: "🧪",
};

const PERSONA_COLOR: Record<string, string> = {
  friendly_warm: "from-rose-100 to-amber-50 border-rose-300",
  rigorous_strict: "from-slate-100 to-zinc-50 border-slate-300",
  challenging_pressure: "from-orange-100 to-red-50 border-orange-300",
  senior_experienced: "from-emerald-100 to-teal-50 border-emerald-300",
  tech_expert: "from-indigo-100 to-blue-50 border-indigo-300",
};

export default function InterviewPersonaPicker({ selected, onSelect }: Props) {
  const [items, setItems] = useState<PersonaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch("/api/ai-interview-v2/personas", {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("sb_token") || ""}`,
      },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((data) => {
        if (alive) {
          setItems(data.items || []);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(typeof e === "string" ? e : "加载人格失败");
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loading) {
    return <div className="text-sm text-slate-500">加载面试官人格中…</div>;
  }
  if (error) {
    return <div className="text-sm text-rose-600">{error}</div>;
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="persona-grid">
      {items.map((p) => {
        const isSel = p.id === selected;
        return (
          <button
            key={p.id}
            type="button"
            onClick={() => onSelect(p.id)}
            aria-pressed={isSel}
            data-testid={`persona-${p.id}`}
            className={`text-left p-4 rounded-2xl border-2 transition shadow-sm bg-gradient-to-br ${
              PERSONA_COLOR[p.id] || "from-slate-50 to-slate-100 border-slate-200"
            } ${isSel ? "ring-2 ring-offset-2 ring-sky-400" : "hover:shadow-md"}`}
          >
            <div className="flex items-center gap-2">
              <span className="text-2xl" aria-hidden>
                {PERSONA_ICONS[p.id] || "🤖"}
              </span>
              <div className="font-semibold text-slate-800">{p.label}</div>
            </div>
            <p className="mt-2 text-sm text-slate-600 leading-relaxed">{p.description}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {(p.tags || []).map((t) => (
                <span
                  key={t}
                  className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/70 text-slate-500 border border-slate-200"
                >
                  {t}
                </span>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-5 gap-1 text-[10px] text-slate-500">
              {(["technical", "communication", "thinking", "potential", "culture"] as const).map(
                (d) => (
                  <div key={d} className="text-center">
                    <div className="font-medium text-slate-700">
                      {Math.round(((p.weights?.[d] ?? 0) * 100) / 5)}
                    </div>
                    <div className="opacity-70">
                      {d === "technical" ? "技" : d === "communication" ? "沟" : d === "thinking" ? "思" : d === "potential" ? "潜" : "文"}
                    </div>
                  </div>
                ),
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

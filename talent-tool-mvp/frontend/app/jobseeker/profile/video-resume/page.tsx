"use client";

/**
 * /jobseeker/profile/video-resume — T2203.
 *
 * 视频简历管理页: 录制 + 已上传视频列表 + AI 评分查看.
 */

import { useEffect, useState } from "react";
import VideoResumeRecorder from "@/components/VideoResumeRecorder";
import VideoResumePlayer, { type VideoResumeAnalysis } from "@/components/VideoResumePlayer";

interface VideoResumeItem {
  id: string;
  video_url: string;
  duration_sec: number;
  created_at: string;
  analysis?: VideoResumeAnalysis | null;
  status: "recording" | "uploaded" | "analyzing" | "analyzed" | "failed";
}

export default function VideoResumePage() {
  const [items, setItems] = useState<VideoResumeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const token = localStorage.getItem("sb_token") || "";
    fetch("/api/video-resume/list", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((data) => {
        if (alive) {
          setItems(data.items || []);
          if (data.items?.[0]) setActiveId(data.items[0].id);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setError(typeof e === "string" ? e : "加载失败");
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  const handleUploaded = async ({
    video_url,
    duration_sec,
  }: {
    video_url: string;
    duration_sec: number;
  }) => {
    const token = localStorage.getItem("sb_token") || "";
    try {
      const r = await fetch("/api/video-resume/create", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ video_url, duration_sec }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = (await r.json()) as { item: VideoResumeItem };
      setItems((prev) => [data.item, ...prev]);
      setActiveId(data.item.id);
    } catch (e) {
      setError(`保存失败:${(e as Error).message}`);
    }
  };

  const handleAnalyze = async (id: string) => {
    const token = localStorage.getItem("sb_token") || "";
    setItems((prev) =>
      prev.map((it) => (it.id === id ? { ...it, status: "analyzing" } : it))
    );
    try {
      const r = await fetch(`/api/video-resume/${id}/analyze`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(await r.text());
      const data = (await r.json()) as { analysis: VideoResumeAnalysis };
      setItems((prev) =>
        prev.map((it) =>
          it.id === id ? { ...it, status: "analyzed", analysis: data.analysis } : it
        )
      );
    } catch (e) {
      setError(`分析失败:${(e as Error).message}`);
      setItems((prev) =>
        prev.map((it) => (it.id === id ? { ...it, status: "failed" } : it))
      );
    }
  };

  const active = items.find((i) => i.id === activeId);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">视频简历</h1>
        <p className="mt-1 text-sm text-slate-500">
          30~60 秒自我介绍视频,AI 自动评估沟通能力 / 表达清晰度 / 专业度 / 自信度 / 亲和力。
        </p>
      </header>

      {error && (
        <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>
      )}

      <VideoResumeRecorder
        onUploaded={handleUploaded}
        authToken={localStorage.getItem("sb_token") || undefined}
      />

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-900">已上传的视频简历</h2>
        {loading ? (
          <div className="text-sm text-slate-500">加载中…</div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
            尚未录制视频简历
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {items.map((it) => (
                <button
                  key={it.id}
                  type="button"
                  onClick={() => setActiveId(it.id)}
                  className={`rounded-lg border px-3 py-1.5 text-xs ${
                    activeId === it.id
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 bg-white text-slate-700"
                  }`}
                >
                  {new Date(it.created_at).toLocaleString()} ·{" "}
                  {Math.round(it.duration_sec)}s · {it.status}
                </button>
              ))}
            </div>

            {active && (
              <div className="space-y-3">
                <VideoResumePlayer
                  videoUrl={active.video_url}
                  analysis={active.analysis}
                />
                {active.status !== "analyzed" && active.status !== "analyzing" && (
                  <button
                    type="button"
                    onClick={() => handleAnalyze(active.id)}
                    className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
                  >
                    运行 AI 评估
                  </button>
                )}
                {active.status === "analyzing" && (
                  <span className="text-sm text-slate-500">AI 评估中…</span>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
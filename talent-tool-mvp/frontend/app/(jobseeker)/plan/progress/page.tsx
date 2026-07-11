"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { PlanProgressTracker } from "@/components/plan/PlanProgressTracker";
import { fetchPlanProgress, type PlanProgress } from "@/lib/api-plan";
import { createClient } from "@/lib/supabase";

export default function ProgressPage() {
  const [userId, setUserId] = useState<string | null>(null);
  const [data, setData] = useState<PlanProgress | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(uid: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchPlanProgress(uid);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function resolveUser() {
      try {
        const supabase = createClient();
        const { data: session } = await supabase.auth.getSession();
        const uid = session?.session?.user?.id;
        if (!cancelled && uid) {
          setUserId(uid);
          await load(uid);
        }
      } catch {
        // ignore — anon user, fall back to dev user id
      }
      if (!cancelled) {
        const devId = localStorage.getItem("dev_user_id") || "demo-user";
        setUserId(devId);
        await load(devId);
      }
    }
    resolveUser();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading && !data) {
    return (
      <div className="p-6 text-sm text-muted-foreground">加载中…</div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">计划进度</h1>
        <p className="text-sm text-muted-foreground">
          追踪你的职业规划执行情况,支持打卡和动态调整
        </p>
      </header>

      {error && (
        <Card className="border-red-300 bg-red-50">
          <CardContent className="p-3 text-sm text-red-700">
            {error}
          </CardContent>
        </Card>
      )}

      {data && userId ? (
        <PlanProgressTracker
          userId={userId}
          data={data}
          onChanged={() => userId && load(userId)}
        />
      ) : (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            正在初始化…
          </CardContent>
        </Card>
      )}
    </div>
  );
}
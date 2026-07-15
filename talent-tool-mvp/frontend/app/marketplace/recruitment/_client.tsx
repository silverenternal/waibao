"use client";

/**
 * T6109 — Recruitment flow kanban (client).
 *
 * Three columns: 联系 → 面试 → 结果. Each candidate is one card placed in the
 * column matching their current funnel stage (derived from their latest
 * contact status + interview status). HR can record a new contact and
 * schedule an interview directly from a card, and move an interview's
 * status forward.
 */
import * as React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import {
  CONTACT_METHOD_LABELS,
  CONTACT_STATUS_LABELS,
  INTERVIEW_FORMAT_LABELS,
  INTERVIEW_STATUS_LABELS,
  fetchKanban,
  recordContact,
  scheduleInterview,
  updateInterviewStatus,
  type ContactMethod,
  type ContactStatus,
  type InterviewFormat,
  type InterviewStatus,
  type KanbanBoard,
  type KanbanCandidate,
} from "@/lib/api-recruitment";

const COLUMNS: { key: KanbanCandidate["stage"]; title: string }[] = [
  { key: "contact", title: "联系" },
  { key: "interview", title: "面试" },
  { key: "result", title: "结果" },
];

export function RecruitmentKanbanClient() {
  const [board, setBoard] = useState<KanbanBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<KanbanCandidate | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const b = await fetchKanban();
      setBoard(b);
    } catch (e) {
      setError(errMsg(e, "加载看板失败"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const grouped = useMemo(() => {
    const map: Record<string, KanbanCandidate[]> = {
      contact: [],
      interview: [],
      result: [],
    };
    for (const c of board?.candidates ?? []) {
      (map[c.stage] ?? (map[c.stage] = [])).push(c);
    }
    return map;
  }, [board]);

  return (
    <div className="container mx-auto max-w-6xl space-y-6 px-4 py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">招聘流程看板</h1>
          <p className="text-sm text-muted-foreground">
            联系记录 + 面试安排，按候选人聚合，三列流转。
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span>已联系 {board?.totals.contacted ?? 0}</span>
          <span>面试中 {board?.totals.interviewing ?? 0}</span>
          <span>已结果 {board?.totals.completed ?? 0}</span>
          <Button variant="outline" size="sm" onClick={reload}>
            刷新
          </Button>
        </div>
      </header>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">加载中…</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {COLUMNS.map((col) => (
            <div key={col.key} className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">{col.title}</h2>
                <Badge variant="secondary">
                  {grouped[col.key]?.length ?? 0}
                </Badge>
              </div>
              <div className="space-y-3">
                {(grouped[col.key] ?? []).map((c) => (
                  <CandidateCard
                    key={c.candidate_id}
                    candidate={c}
                    onClick={() => setActive(c)}
                  />
                ))}
                {(grouped[col.key] ?? []).length === 0 ? (
                  <p className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
                    暂无候选人
                  </p>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}

      <CandidateDetailDialog
        candidate={active}
        onClose={() => setActive(null)}
        onChanged={reload}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// candidate card
// ---------------------------------------------------------------------------

function CandidateCard({
  candidate,
  onClick,
}: {
  candidate: KanbanCandidate;
  onClick: () => void;
}) {
  return (
    <Card className="cursor-pointer transition hover:shadow-md" onClick={onClick}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          {candidate.candidate_name || candidate.candidate_id}
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          {candidate.role_title || "—"}
        </p>
      </CardHeader>
      <CardContent className="space-y-1.5 text-xs">
        {candidate.contact_status ? (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">联系</span>
            <Badge variant="outline">
              {CONTACT_STATUS_LABELS[candidate.contact_status] ??
                candidate.contact_status}
            </Badge>
          </div>
        ) : null}
        {candidate.interview_status ? (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">面试</span>
            <Badge variant="outline">
              {INTERVIEW_STATUS_LABELS[candidate.interview_status] ??
                candidate.interview_status}
            </Badge>
          </div>
        ) : null}
        {candidate.next_interview ? (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">下一场</span>
            <span className="truncate">{candidate.next_interview}</span>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// detail dialog — record contact + schedule interview + move status
// ---------------------------------------------------------------------------

function CandidateDetailDialog({
  candidate,
  onClose,
  onChanged,
}: {
  candidate: KanbanCandidate | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const open = candidate !== null;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {candidate?.candidate_name || candidate?.candidate_id}
          </DialogTitle>
          <DialogDescription>
            {candidate?.role_title || "候选人招聘流程"}
          </DialogDescription>
        </DialogHeader>

        {candidate ? (
          <div className="max-h-[60vh] space-y-4 overflow-y-auto">
            <ContactForm candidate={candidate} onSaved={onChanged} />
            <InterviewSection candidate={candidate} onSaved={onChanged} />
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function ContactForm({
  candidate,
  onSaved,
}: {
  candidate: KanbanCandidate;
  onSaved: () => void;
}) {
  const [method, setMethod] = useState<ContactMethod>("phone");
  const [status, setStatus] = useState<ContactStatus>("reached");
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = useCallback(async () => {
    setSaving(true);
    setErr(null);
    try {
      await recordContact({
        candidate_id: candidate.candidate_id,
        role_id: candidate.role_id || undefined,
        candidate_name: candidate.candidate_name || undefined,
        role_title: candidate.role_title || undefined,
        contact_method: method,
        status,
        contact_date: date,
        notes,
      });
      setNotes("");
      onSaved();
    } catch (e) {
      setErr(errMsg(e, "记录联系失败"));
    } finally {
      setSaving(false);
    }
  }, [candidate, method, status, date, notes, onSaved]);

  return (
    <div className="space-y-3 rounded-md border p-3">
      <h3 className="text-sm font-semibold">记录一次联系</h3>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">方式</Label>
          <Select value={method} onValueChange={(v) => setMethod(v as ContactMethod)}>
            <SelectTrigger className="h-9" aria-label="联系方法">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(CONTACT_METHOD_LABELS).map(([v, l]) => (
                <SelectItem key={v} value={v}>
                  {l}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">结果</Label>
          <Select value={status} onValueChange={(v) => setStatus(v as ContactStatus)}>
            <SelectTrigger className="h-9" aria-label="联系结果">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(CONTACT_STATUS_LABELS).map(([v, l]) => (
                <SelectItem key={v} value={v}>
                  {l}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1">
        <Label className="text-xs">日期</Label>
        <Input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="h-9"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">备注</Label>
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="沟通要点 / 下一步…"
        />
      </div>
      {err ? <p className="text-xs text-destructive">{err}</p> : null}
      <div className="flex justify-end">
        <Button size="sm" onClick={submit} disabled={saving}>
          {saving ? "保存中…" : "记录联系"}
        </Button>
      </div>

      {candidate.contacts.length ? (
        <div className="space-y-1 border-t pt-2">
          <div className="text-xs font-medium text-muted-foreground">
            历史联系 ({candidate.contacts.length})
          </div>
          {candidate.contacts.slice(0, 5).map((c) => (
            <div key={c.id} className="flex items-center justify-between text-xs">
              <span>
                {c.contact_date} ·{" "}
                {CONTACT_METHOD_LABELS[c.contact_method] ?? c.contact_method}
              </span>
              <Badge variant="outline">
                {CONTACT_STATUS_LABELS[c.status] ?? c.status}
              </Badge>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function InterviewSection({
  candidate,
  onSaved,
}: {
  candidate: KanbanCandidate;
  onSaved: () => void;
}) {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [time, setTime] = useState("10:00");
  const [location, setLocation] = useState("");
  const [format, setFormat] = useState<InterviewFormat>("onsite");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = useCallback(async () => {
    setSaving(true);
    setErr(null);
    try {
      await scheduleInterview({
        candidate_id: candidate.candidate_id,
        role_id: candidate.role_id || undefined,
        candidate_name: candidate.candidate_name || undefined,
        role_title: candidate.role_title || undefined,
        date,
        time,
        location,
        format,
      });
      onSaved();
    } catch (e) {
      setErr(errMsg(e, "安排面试失败"));
    } finally {
      setSaving(false);
    }
  }, [candidate, date, time, location, format, onSaved]);

  const move = useCallback(
    async (id: string, status: InterviewStatus) => {
      try {
        await updateInterviewStatus(id, status);
        onSaved();
      } catch (e) {
        setErr(errMsg(e, "更新状态失败"));
      }
    },
    [onSaved]
  );

  return (
    <div className="space-y-3 rounded-md border p-3">
      <h3 className="text-sm font-semibold">安排面试</h3>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">日期</Label>
          <Input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="h-9"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">时间</Label>
          <Input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="h-9"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">形式</Label>
          <Select value={format} onValueChange={(v) => setFormat(v as InterviewFormat)}>
            <SelectTrigger className="h-9" aria-label="面试形式">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(INTERVIEW_FORMAT_LABELS).map(([v, l]) => (
                <SelectItem key={v} value={v}>
                  {l}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">地点 / 会议链接</Label>
          <Input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="3 楼会议室 / 会议链接"
            className="h-9"
          />
        </div>
      </div>
      {err ? <p className="text-xs text-destructive">{err}</p> : null}
      <div className="flex justify-end">
        <Button size="sm" onClick={submit} disabled={saving}>
          {saving ? "保存中…" : "安排面试"}
        </Button>
      </div>

      {candidate.interviews.length ? (
        <div className="space-y-2 border-t pt-2">
          <div className="text-xs font-medium text-muted-foreground">
            已安排面试 ({candidate.interviews.length})
          </div>
          {candidate.interviews.map((iv) => (
            <div key={iv.id} className="space-y-1 rounded border p-2 text-xs">
              <div className="flex items-center justify-between">
                <span>
                  {iv.date} {iv.time} ·{" "}
                  {INTERVIEW_FORMAT_LABELS[iv.format] ?? iv.format}
                </span>
                <Badge variant="outline">
                  {INTERVIEW_STATUS_LABELS[iv.status] ?? iv.status}
                </Badge>
              </div>
              {iv.location ? (
                <div className="text-muted-foreground">{iv.location}</div>
              ) : null}
              {iv.status === "scheduled" ? (
                <div className="flex gap-1 pt-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => move(iv.id, "completed")}
                  >
                    标记完成
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => move(iv.id, "no_show")}
                  >
                    未到面
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 text-xs"
                    onClick={() => move(iv.id, "cancelled")}
                  >
                    取消
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
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

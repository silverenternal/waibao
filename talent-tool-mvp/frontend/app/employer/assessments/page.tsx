"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * /assessments (T1306) — 测评邀请列表 + 手动触发.
 */
import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  ClipboardList,
  Send,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import {
  assessmentApi,
  type AssessmentInvitation,
} from "@/lib/api-assessment";

interface Props {
  searchParams: { candidate_id?: string; job_id?: string };
}

export default function AssessmentsPage({ searchParams }: Props) {
  const [items, setItems] = React.useState<AssessmentInvitation[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // 手动触发表单
  const [candidateId, setCandidateId] = React.useState(
    searchParams.candidate_id || "",
  );
  const [assessmentId, setAssessmentId] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const out = await assessmentApi.list({
        candidate_id: searchParams.candidate_id,
        job_id: searchParams.job_id,
      });
      setItems(out.data || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }, [searchParams.candidate_id, searchParams.job_id]);

  React.useEffect(() => {
    load();
  }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await assessmentApi.invite({
        candidate_id: candidateId,
        assessment_id: assessmentId,
        candidate_email: email || undefined,
        candidate_name: email || undefined,
        job_id: searchParams.job_id,
      });
      setAssessmentId("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invite failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-4xl space-y-4 p-6">
        <div className="flex items-center gap-2">
          <Link href="/" className="text-sm text-gray-500">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-semibold">Assessments</h1>
        </div>
        <Card>
          <CardContent className="p-4">
            <form onSubmit={submit} className="grid gap-3 md:grid-cols-3">
              <Input
                label="Candidate ID"
                value={candidateId}
                onChange={setCandidateId}
                required
              />
              <Input
                label="Assessment ID"
                value={assessmentId}
                onChange={setAssessmentId}
                required
              />
              <Input
                label="Candidate email"
                type="email"
                value={email}
                onChange={setEmail}
                placeholder="optional"
              />
              <div className="flex items-end md:col-span-3">
                <Button type="submit" disabled={submitting}>
                  {submitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="mr-2 h-4 w-4" />
                  )}
                  Send invitation
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="p-3 text-sm text-red-700">
              <AlertCircle className="mr-1 inline h-4 w-4" /> {error}
            </CardContent>
          </Card>
        )}
        <div className="grid gap-3">
          {loading && items.length === 0 ? (
            <div className="flex justify-center p-6 text-gray-400">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : items.length === 0 ? (
            <Card>
              <CardContent className="p-6 text-center text-gray-500">
                <ClipboardList className="mx-auto mb-2 h-8 w-8 text-gray-400" />
                <p>No assessment invitations.</p>
              </CardContent>
            </Card>
          ) : (
            items.map((it) => (
              <Row key={it.id} item={it} />
            ))
          )}
        </div>
      </div>)</ErrorBoundary>
  );
}

function Input({
  label,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="text-sm">
      <span className="mb-1 block font-medium text-gray-700">{label}</span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border px-3 py-2 text-sm"
      />
    </label>
  );
}

function Row({ item }: { item: AssessmentInvitation }) {
  const status = item.status;
  const color =
    status === "scored"
      ? "text-emerald-600"
      : status === "expired"
      ? "text-red-600"
      : "text-amber-600";
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-3">
        <div>
          <p className="text-sm font-medium">{item.invitation_id}</p>
          <p className="text-xs text-gray-500">
            Provider: {item.provider} · Status:{" "}
            <span className={color}>{status}</span>
          </p>
        </div>
        {item.invite_url && (
          <a
            href={item.invite_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline"
          >
            open invite
          </a>
        )}
      </CardContent>
    </Card>
  );
}
